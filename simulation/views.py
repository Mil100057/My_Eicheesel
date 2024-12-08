from datetime import datetime
from decimal import Decimal
from typing import Tuple, List, TypedDict, Optional
import json
import logging
import csv
import io
from django.contrib.auth.decorators import login_required
from django.contrib import messages
#from django.core.checks import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.db.models import  QuerySet
from django.core.exceptions import ValidationError, PermissionDenied
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .forms import SimulationForm, RealDataForm, PortfolioForm, PositionForm, TransactionForm, StockForm, \
    AnnualInflationRateForm, SimulationCSVImportForm
from .models import Simulation, Category, ConsolidatedResult, RealAccountData, Portfolio, Position, Transaction, Stock, \
    AnnualInflationRate

from django.utils.text import slugify

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET", "POST"])
def category(request: HttpRequest) -> HttpResponse:
    """View to manage categories."""
    if request.method == "POST":
        category_name = request.POST.get('category')
        try:
            # Vérifier si la catégorie existe déjà
            if Category.objects.filter(category=category_name).exists():
                messages.warning(request, "Cette catégorie existe déjà.")
            else:
                # Créer la nouvelle catégorie
                Category.objects.create(category=category_name)
                messages.success(request, "Catégorie ajoutée avec succès.")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    "status": "success",
                    "message": "Catégorie ajoutée avec succès."
                })

        except Exception as e:
            logger.error(f"Error creating category: {str(e)}")
            messages.error(request, "Une erreur est survenue lors de la création de la catégorie.")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    "status": "error",
                    "message": "Une erreur est survenue lors de la création de la catégorie."
                }, status=500)

    # Récupérer toutes les catégories existantes, pas seulement celles utilisées dans les simulations
    categories = Category.objects.all().order_by('category')

    return render(request, 'view_category.html', {
        "categories": categories,
        "compte_types": Category.COMPTE_TYPE
    })

@login_required
def name(request: HttpRequest) -> HttpResponse:
    names = Simulation.objects.filter(user=request.user)
    return render(request, 'view_name.html', {"names": names})

def calculate_simulation_results(simulation_instance: Simulation) -> None:
    try:
        if not validate_simulation_inputs(simulation_instance):
            raise ValidationError("Invalid calculation parameters")

        montant_actuel = Decimal(str(simulation_instance.montant_initial))
        taux = Decimal(str(simulation_instance.taux_rentabilite)) / 100
        montant_fixe = Decimal(str(simulation_instance.montant_fixe_annuel))

        with transaction.atomic():
            # Delete existing results for this simulation to avoid duplicates
            ConsolidatedResult.objects.filter(simulation=simulation_instance).delete()

            # Create first year's result with initial amount
            results_to_create = [
                ConsolidatedResult(
                    simulation=simulation_instance,
                    annee=simulation_instance.annee_depart,
                    montant=montant_actuel,
                    nom_compte=simulation_instance.nom_compte
                )
            ]

            # Calculate subsequent years
            for annee in range(
                    simulation_instance.annee_depart + 1,
                    simulation_instance.annee_depart + simulation_instance.periode + 1
            ):
                # First apply return rate to current amount
                montant_actuel = montant_actuel * (1 + taux)
                # Then add the fixed annual contribution
                montant_actuel += montant_fixe

                results_to_create.append(
                    ConsolidatedResult(
                        simulation=simulation_instance,
                        annee=annee,
                        montant=montant_actuel,
                        nom_compte=simulation_instance.nom_compte
                    )
                )

            # Bulk create for better performance
            ConsolidatedResult.objects.bulk_create(results_to_create)

    except (ValueError, TypeError, ValidationError) as e:
        logger.error(f"Error calculating simulation results: {str(e)}")
        raise ValidationError("Invalid calculation parameters")
    except Exception as e:
        logger.error(f"Unexpected error in calculation: {str(e)}", exc_info=True)
        raise ValidationError("Une erreur est survenue lors du calcul")


class ChartDataPoint(TypedDict):
    label: str
    data: List[float]


class ChartData(TypedDict):
    labels: List[str]
    datasets: List[ChartDataPoint]


def prepare_chart_data_base(
        consolidated_results: QuerySet[ConsolidatedResult],
        cumulative: bool = False,
        group_by_field: str = 'category'
) -> Tuple[List[str], List[ChartDataPoint]]:

    if not consolidated_results.exists():
        return [], []

    # Chart.js default colors
    colors = [
        {'backgroundColor': 'rgba(54, 162, 235, 0.2)', 'borderColor': 'rgb(54, 162, 235)'},  # blue
        {'backgroundColor': 'rgba(255, 99, 132, 0.2)', 'borderColor': 'rgb(255, 99, 132)'},  # red
        {'backgroundColor': 'rgba(255, 206, 86, 0.2)', 'borderColor': 'rgb(255, 206, 86)'},  # yellow
        {'backgroundColor': 'rgba(75, 192, 192, 0.2)', 'borderColor': 'rgb(75, 192, 192)'},  # green
        {'backgroundColor': 'rgba(153, 102, 255, 0.2)', 'borderColor': 'rgb(153, 102, 255)'},  # purple
        {'backgroundColor': 'rgba(255, 159, 64, 0.2)', 'borderColor': 'rgb(255, 159, 64)'},  # orange
    ]

    # Get all unique years across all simulations
    years = sorted(set(result.annee for result in consolidated_results))
    chart_labels = [str(year) for year in years]

    if cumulative:
        # Initialize data structures
        data_by_simulation = {}
        yearly_totals = {str(year): 0 for year in years}

        # First pass: Collect all values by simulation
        for result in consolidated_results:
            sim_id = result.simulation.id
            group_key = (
                result.simulation.categorie.category if group_by_field == 'category'
                else result.simulation.nom_compte
            )

            if sim_id not in data_by_simulation:
                data_by_simulation[sim_id] = {
                    'group': group_key,
                    'values': {str(year): 0 for year in years}
                }

            # Store the actual value for this year
            year_str = str(result.annee)
            data_by_simulation[sim_id]['values'][year_str] = float(result.montant)

        # Second pass: Apply running totals for each simulation
        for sim_data in data_by_simulation.values():
            running_total = 0
            for year in years:
                year_str = str(year)
                current_value = sim_data['values'][year_str]

                if current_value > 0:
                    # Update running total if we have a value
                    running_total = current_value
                else:
                    # Keep previous running total if no value
                    sim_data['values'][year_str] = running_total

                # Add to yearly totals
                yearly_totals[year_str] += sim_data['values'][year_str]

        # Create single dataset for cumulative view
        label = 'Total tous comptes' if group_by_field == 'account' else 'Total toutes catégories'
        chart_data = [{
            'label': label,
            'data': [yearly_totals[str(year)] for year in years],
            **colors[0],
            'borderWidth': 2,
            'fill': True
        }]

    else:
        # Non-cumulative view - show individual lines
        data_by_group = {}

        # Calculate totals for each group and year
        for result in consolidated_results:
            if group_by_field == 'category':
                group_key = result.simulation.categorie.category
            else:
                group_key = result.simulation.nom_compte

            if group_key not in data_by_group:
                data_by_group[group_key] = {str(year): 0 for year in years}

            year_str = str(result.annee)
            data_by_group[group_key][year_str] += float(result.montant)

        # Create datasets for detailed view
        chart_data = []
        for idx, (group_key, values) in enumerate(sorted(data_by_group.items())):
            color_idx = idx % len(colors)
            dataset = {
                'label': group_key,
                'data': [values[str(year)] for year in years],
                **colors[color_idx],
                'borderWidth': 2
            }
            chart_data.append(dataset)

    return chart_labels, chart_data


def prepare_chart_data_by_category(
        consolidated_results: QuerySet[ConsolidatedResult],
        cumulative: bool = False
) -> Tuple[List[str], List[ChartDataPoint]]:

    return prepare_chart_data_base(consolidated_results, cumulative, 'category')


def prepare_chart_data_by_account(
        consolidated_results: QuerySet[ConsolidatedResult],
        cumulative: bool = False
) -> Tuple[List[str], List[ChartDataPoint]]:

    return prepare_chart_data_base(consolidated_results, cumulative, 'account')

@login_required
def simulation(request: HttpRequest) -> HttpResponse:

    if request.method != 'POST':
        form = SimulationForm(user=request.user)
        return render(request, 'simulation.html', {'form': form})

    try:
        form = SimulationForm(request.POST, user=request.user)

        if not form.is_valid():
            return render(request, 'simulation.html', {'form': form})

        with transaction.atomic():
            # Save the simulation instance
            simulation_instance = form.save(commit=False)
            simulation_instance.user = request.user

            # Validate simulation parameters
            if not validate_simulation_inputs(simulation_instance):
                form.add_error(None, "Les paramètres de simulation sont invalides")
                return render(request, 'simulation.html', {'form': form})

            # Save the simulation to the database
            simulation_instance.save()

            try:
                # Calculate and save results
                calculate_simulation_results(simulation_instance)

                # Fetch results for display
                consolidated_results = ConsolidatedResult.objects.filter(
                    simulation=simulation_instance
                ).order_by('annee')

                # Prepare chart data
                chart_labels, chart_data = prepare_chart_data_base(consolidated_results)

                # Show success message
                messages.success(request, "Simulation créée avec succès")

                return render(request, 'resultats.html', {
                    'consolidated_results': consolidated_results,
                    'simulation_instance': simulation_instance,
                    'chart_labels': json.dumps(chart_labels),
                    'chart_data': json.dumps(chart_data)
                })

            except ValidationError as e:
                # If calculation fails, delete the simulation
                simulation_instance.delete()
                form.add_error(None, str(e))
                return render(request, 'simulation.html', {'form': form})

    except Exception as e:
        logger.error(
            f"Unexpected error in simulation view for user {request.user.id}: {str(e)}",
            exc_info=True
        )
        form.add_error(None, "Une erreur inattendue est survenue")
        return render(request, 'simulation.html', {'form': form})

    #return render(request, 'simulation.html', {'form': form})


def validate_simulation_inputs(simulation: Simulation) -> bool:

    try:
        # Ensure positive values
        #if simulation.montant_initial < 0 or simulation.montant_fixe_annuel < 0:
        #    return False

        # Ensure reasonable rate range (-100% to +100%)
        if not -100 <= simulation.taux_rentabilite <= 100:
            return False

        # Ensure reasonable period (e.g., 1-50 years)
        if not 1 <= simulation.periode <= 50:
            return False

        # Ensure start year is reasonable (e.g., within last 5 years)
        current_year = datetime.now().year
        if not current_year - 5 <= simulation.annee_depart <= current_year + 1:
            return False

        return True

    except Exception as e:
        logger.error(f"Error validating simulation inputs: {str(e)}")
        return False

@login_required
def results_list_by_cat(request: HttpRequest) -> HttpResponse:

    categories: QuerySet[str] = Category.objects.filter(
        simulation__user=request.user
    ).values_list('category', flat=True).distinct()

    selected_category: Optional[str] = request.GET.get('categories')
    cumulative: bool = request.GET.get('cumulative') == 'true'
    chart_data: List[ChartDataPoint] = []
    chart_labels: List[str] = []
    consolidated_results: QuerySet[ConsolidatedResult] = ConsolidatedResult.objects.none()

    try:
        if selected_category == "all":
            simulations = Simulation.objects.filter(user=request.user)
            consolidated_results = ConsolidatedResult.objects.filter(
                simulation__in=simulations
            ).select_related('simulation', 'simulation__categorie')

            chart_labels, chart_data = prepare_chart_data_by_category(consolidated_results, cumulative)

        elif selected_category:
            simulations = Simulation.objects.filter(
                categorie__category=selected_category,
                user=request.user
            )
            if simulations.exists():
                consolidated_results = ConsolidatedResult.objects.filter(
                    simulation__in=simulations
                ).select_related('simulation')

                chart_labels, chart_data = prepare_chart_data_by_category(consolidated_results, cumulative)

    except Exception as e:
        logger.error(f"Error in results_list_by_cat for user {request.user.id}: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur est survenue lors du traitement des données")

    context = {
        'categories': categories,
        'consolidated_results': consolidated_results,
        'chart_data': json.dumps(chart_data),
        'chart_labels': json.dumps(chart_labels),
        'selected_category': selected_category,
        'cumulative': cumulative,
    }

    return render(request, 'results_list_by_cat.html', context)

@login_required
def results_list_by_name(request: HttpRequest) -> HttpResponse:

    account_names: QuerySet[str] = Simulation.objects.filter(
        user=request.user
    ).values_list('nom_compte', flat=True).distinct()

    selected_name: Optional[str] = request.GET.get('account_name')
    cumulative: bool = request.GET.get('cumulative') == 'true'
    chart_data: List[ChartDataPoint] = []
    chart_labels: List[str] = []
    consolidated_results: QuerySet[ConsolidatedResult] = ConsolidatedResult.objects.none()

    try:
        if selected_name == "all":
            simulations = Simulation.objects.filter(user=request.user)
            consolidated_results = ConsolidatedResult.objects.filter(
                simulation__in=simulations
            ).select_related('simulation')

            chart_labels, chart_data = prepare_chart_data_by_account(consolidated_results, cumulative)

        elif selected_name:
            simulations = Simulation.objects.filter(
                nom_compte=selected_name,
                user=request.user
            )
            if simulations.exists():
                consolidated_results = ConsolidatedResult.objects.filter(
                    simulation__in=simulations
                ).select_related('simulation')

                chart_labels, chart_data = prepare_chart_data_by_account(consolidated_results, cumulative)

    except Exception as e:
        logger.error(f"Error in results_list_by_name for user {request.user.id}: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur est survenue lors du traitement des données")

    context = {
        'account_names': account_names,
        'consolidated_results': consolidated_results,
        'chart_data': json.dumps(chart_data),
        'chart_labels': json.dumps(chart_labels),
        'selected_name': selected_name,
        'cumulative': cumulative,
    }

    return render(request, 'results_list_by_name.html', context)


@login_required
@require_http_methods(["POST"])
def delete_simulation(request: HttpRequest, simulation_id: int) -> HttpResponse:

    try:
        with transaction.atomic():
            simulation = get_object_or_404(Simulation, id=simulation_id)

            # Check if user owns this simulation
            if simulation.user != request.user:
                raise PermissionDenied("You don't have permission to delete this simulation")

            # Delete associated results first
            ConsolidatedResult.objects.filter(simulation=simulation).delete()
            #ResultatSimulation.objects.filter(simulation=simulation).delete()

            # Delete the simulation
            simulation.delete()

            messages.success(request, "Simulation supprimée avec succès")
            return JsonResponse({"status": "success", "message": "Simulation supprimée"})

    except PermissionDenied as e:
        logger.error(f"Permission denied for user {request.user.id} deleting simulation {simulation_id}: {str(e)}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=403
        )
    except Exception as e:
        logger.error(f"Error deleting simulation {simulation_id}: {str(e)}", exc_info=True)
        return JsonResponse(
            {"status": "error", "message": "Erreur lors de la suppression de la simulation"},
            status=500
        )


@login_required
@require_http_methods(["POST"])
def delete_account(request: HttpRequest, account_name: str) -> HttpResponse:
    """
    Delete all simulations associated with a specific account name.
    Only deletes if the user owns all simulations for that account.

    """
    try:
        with transaction.atomic():
            # Get all simulations for this account name
            simulations = Simulation.objects.filter(
                nom_compte=account_name
            )

            if not simulations.exists():
                return JsonResponse({
                    "status": "error",
                    "message": "Compte non trouvé"
                }, status=404)

            # Get user's simulations for this account
            user_simulations = simulations.filter(user=request.user)

            if not user_simulations.exists():
                raise PermissionDenied("Vous n'avez pas l'autorisation de supprimer ce compte")

            # Check if all simulations for this account belong to the user
            if simulations.count() != user_simulations.count():
                raise PermissionDenied(
                    "Ce compte contient des simulations d'autres utilisateurs. "
                    "Seules vos simulations peuvent être supprimées."
                )

            # Delete all associated results first
            simulation_ids = user_simulations.values_list('id', flat=True)
            ConsolidatedResult.objects.filter(simulation__in=simulation_ids).delete()
            #ResultatSimulation.objects.filter(simulation__in=simulation_ids).delete()

            # Delete the user's simulations
            count_deleted = user_simulations.delete()[0]

            return JsonResponse({
                "status": "success",
                "message": f"Compte {account_name} supprimé avec succès ({count_deleted} simulation(s) supprimée(s))"
            })

    except PermissionDenied as e:
        logger.error(
            f"Permission denied for user {request.user.id} deleting account {account_name}: {str(e)}"
        )
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=403
        )
    except Exception as e:
        logger.error(f"Error deleting account {account_name}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Erreur lors de la suppression du compte"
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_category(request: HttpRequest, category_name: str) -> HttpResponse:
    """
    Delete a category if it's not being used in any simulations.
    """
    try:
        with transaction.atomic():
            # Get the category
            category = get_object_or_404(Category, category=category_name)

            # Check if the category is being used in any simulations
            if Simulation.objects.filter(categorie=category).exists():
                return JsonResponse({
                    "status": "error",
                    "message": "Cette catégorie ne peut pas être supprimée car elle est utilisée dans des simulations existantes."
                }, status=400)

            # If not used, we can safely delete it
            category.delete()
            return JsonResponse({
                "status": "success",
                "message": f"Catégorie {category_name} supprimée avec succès"
            })

    except Category.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Catégorie non trouvée"
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting category {category_name}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Erreur lors de la suppression de la catégorie"
        }, status=500)


def export_results_to_csv(results: QuerySet[ConsolidatedResult], filename_prefix: str) -> HttpResponse:
    """Export results to CSV file in a format compatible with import."""
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="{filename_prefix}_{timestamp}.csv"'

    writer = csv.writer(response, delimiter=';')

    # Write headers matching import format
    writer.writerow([
        'categorie', 'nom_compte', 'montant_initial', 'currency',
        'taux_rentabilite', 'periode', 'annee_depart', 'montant_fixe_annuel'
    ])

    # Group results by simulation to avoid duplicates
    processed_simulations = set()

    for result in results:
        simulation = result.simulation
        if simulation.id not in processed_simulations:
            writer.writerow([
                simulation.categorie.category,
                simulation.nom_compte,
                str(simulation.montant_initial).replace('.', ','),
                simulation.currency,
                str(simulation.taux_rentabilite).replace('.', ','),
                simulation.periode,
                simulation.annee_depart,
                str(simulation.montant_fixe_annuel).replace('.', ',')
            ])
            processed_simulations.add(simulation.id)

    return response

@login_required
def import_simulations(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = SimulationCSVImportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    simulations = form.save()

                    # Calculate results for each imported simulation
                    for simulation in simulations:
                        try:
                            calculate_simulation_results(simulation)
                        except ValidationError as calc_error:
                            # If calculation fails, rollback entire transaction
                            raise ValidationError(f"Erreur de calcul pour {simulation.nom_compte}: {str(calc_error)}")

                messages.success(request, f"{len(simulations)} simulation(s) importée(s) et calculée(s) avec succès")
                return redirect('simulation')

            except ValidationError as e:
                messages.error(request, str(e))
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = SimulationCSVImportForm()

    return render(request, 'import_simulations.html', {
        'form': form
    })

@login_required
def export_results_by_cat(request: HttpRequest) -> HttpResponse:
    """Export results by category to CSV."""
    try:
        selected_category = request.GET.get('category')

        if selected_category == "all":
            simulations = Simulation.objects.filter(user=request.user)
            filename_prefix = "toutes_categories"
        else:
            simulations = Simulation.objects.filter(
                categorie__category=selected_category,
                user=request.user
            )
            filename_prefix = f"categorie_{slugify(selected_category)}"

        results = ConsolidatedResult.objects.filter(
            simulation__in=simulations
        ).select_related(
            'simulation',
            'simulation__categorie'
        ).order_by('annee', 'simulation__categorie__category', 'simulation__nom_compte')

        return export_results_to_csv(results, filename_prefix)

    except Exception as e:
        logger.error(f"Error exporting category results: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur est survenue lors de l'export")
        return redirect('results_list_by_cat')


@login_required
def export_results_by_name(request: HttpRequest) -> HttpResponse:
    """Export results by account name to CSV."""
    try:
        selected_name = request.GET.get('account_name')

        if selected_name == "all":
            simulations = Simulation.objects.filter(user=request.user)
            filename_prefix = "tous_comptes"
        else:
            simulations = Simulation.objects.filter(
                nom_compte=selected_name,
                user=request.user
            )
            filename_prefix = f"compte_{slugify(selected_name)}"

        results = ConsolidatedResult.objects.filter(
            simulation__in=simulations
        ).select_related(
            'simulation',
            'simulation__categorie'
        ).order_by('annee', 'simulation__nom_compte')

        return export_results_to_csv(results, filename_prefix)

    except Exception as e:
        logger.error(f"Error exporting account results: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur est survenue lors de l'export")
        return redirect('results_list_by_name')


@login_required
def compare_real_data(request: HttpRequest) -> HttpResponse:
    """View to display and manage real account data comparison"""
    accounts = Simulation.objects.filter(user=request.user).order_by('nom_compte')
    selected_account = request.GET.get('account')
    show_inflation = request.GET.get('inflation', 'true') == 'true'
    simulation_data = None
    real_data = None
    real_data_form = None

    if selected_account:
        try:
            simulation = Simulation.objects.get(id=selected_account, user=request.user)

            if request.method == 'POST':
                form = RealDataForm(request.POST)
                if form.is_valid():
                    try:
                        with transaction.atomic():
                            # Récupérer le taux d'inflation global pour l'année
                            inflation_rate = AnnualInflationRate.objects.filter(
                                annee=form.cleaned_data['annee']
                            ).first()

                            # Si pas de taux global, utiliser 0%
                            taux_inflation = inflation_rate.taux_inflation if inflation_rate else Decimal('0')

                            # Mettre à jour ou créer l'entrée
                            real_data_entry, created = RealAccountData.objects.update_or_create(
                                simulation=simulation,
                                annee=form.cleaned_data['annee'],
                                defaults={
                                    'montant_reel': form.cleaned_data['montant_reel'],
                                    'taux_inflation': taux_inflation,
                                    'montant_reel_ajuste': form.cleaned_data['montant_reel'] / (1 + taux_inflation/100)
                                }
                            )

                            action = "créées" if created else "mises à jour"
                            messages.success(request, f"Données réelles {action} avec succès")

                    except Exception as e:
                        logger.error(f"Error saving real data: {str(e)}")
                        messages.error(request, "Une erreur est survenue lors de la sauvegarde des données")

                    return redirect(f'{request.path}?account={selected_account}&inflation={show_inflation}')

            # Get simulation data
            simulation_data = ConsolidatedResult.objects.filter(
                simulation=simulation
            ).order_by('annee')

            # Get real data
            real_data = RealAccountData.objects.filter(
                simulation=simulation
            ).order_by('annee')

            # Get available inflation rates for information
            available_inflation_rates = {
                rate.annee: rate.taux_inflation
                for rate in AnnualInflationRate.objects.all()
            }

            # Prepare comparison data for chart
            years = sorted(set(
                list(simulation_data.values_list('annee', flat=True)) +
                list(real_data.values_list('annee', flat=True))
            ))

            base_datasets = [
                {
                    'label': 'Simulation',
                    'data': [next(
                        (float(r.montant) for r in simulation_data if r.annee == year),
                        None
                    ) for year in years],
                    'borderColor': 'rgb(54, 162, 235)',
                    'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                    'borderWidth': 2
                },
                {
                    'label': 'Données réelles nominales',
                    'data': [next(
                        (float(r.montant_reel) for r in real_data if r.annee == year),
                        None
                    ) for year in years],
                    'borderColor': 'rgb(255, 99, 132)',
                    'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                    'borderWidth': 2
                }
            ]

            if show_inflation:
                # Ajout des données ajustées avec gestion des None
                inflation_data = []
                for year in years:
                    value = next(
                        (r for r in real_data if r.annee == year),
                        None
                    )
                    if value and value.montant_reel_ajuste is not None:
                        inflation_data.append(float(value.montant_reel_ajuste))
                    else:
                        inflation_data.append(None)

                base_datasets.append({
                    'label': 'Données réelles (ajustées inflation)',
                    'data': inflation_data,
                    'borderColor': 'rgb(75, 192, 192)',
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                    'borderWidth': 2,
                    'borderDash': [5, 5]
                })

            chart_data = {
                'labels': [str(year) for year in years],
                'datasets': base_datasets
            }

            # Prepare form for new data entry
            real_data_form = RealDataForm(initial={
                'annee': datetime.now().year
            })

            return render(request, 'compare_real_data.html', {
                'accounts': accounts,
                'selected_account': simulation,
                'simulation_data': simulation_data,
                'real_data': real_data,
                'real_data_form': real_data_form,
                'chart_data': json.dumps(chart_data),
                'show_inflation': show_inflation,
                'available_inflation_rates': available_inflation_rates
            })

        except Simulation.DoesNotExist:
            messages.error(request, "Compte non trouvé")
        except Exception as e:
            logger.error(f"Error in compare_real_data view: {str(e)}", exc_info=True)
            messages.error(request, "Une erreur est survenue")

    return render(request, 'compare_real_data.html', {
        'accounts': accounts,
        'show_inflation': show_inflation
    })


@login_required
def delete_real_data(request: HttpRequest, data_id: int) -> HttpResponse:
    """Delete a real data entry"""
    try:
        data_entry = get_object_or_404(RealAccountData, id=data_id)
        if data_entry.simulation.user != request.user:
            raise PermissionDenied

        data_entry.delete()
        messages.success(request, "Données supprimées avec succès")

        return JsonResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error deleting real data: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def export_real_data_to_csv(request: HttpRequest) -> HttpResponse:
    """Export real data and inflation rates to CSV."""
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="real_data_{timestamp}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['nom_compte', 'annee', 'montant_reel', 'taux_inflation'])

    real_data = RealAccountData.objects.filter(
        simulation__user=request.user
    ).select_related('simulation').order_by('simulation__nom_compte', 'annee')

    for entry in real_data:
        writer.writerow([
            entry.simulation.nom_compte,
            entry.annee,
            str(entry.montant_reel).replace('.', ','),
            str(entry.taux_inflation).replace('.', ',')
        ])

    return response


@login_required
def import_real_data(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        try:
            csv_file = request.FILES['csv_file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, "Le fichier doit être au format CSV")
                return redirect('compare_real_data')

            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded_file), delimiter=';')

            with transaction.atomic():
                for row in reader:
                    try:
                        simulation = Simulation.objects.get(
                            nom_compte=row['nom_compte'],
                            user=request.user
                        )

                        RealAccountData.objects.update_or_create(
                            simulation=simulation,
                            annee=int(row['annee']),
                            defaults={
                                'montant_reel': Decimal(row['montant_reel'].replace(',', '.')),
                                'taux_inflation': Decimal(row['taux_inflation'].replace(',', '.'))
                            }
                        )
                    except Simulation.DoesNotExist:
                        messages.warning(
                            request,
                            f"Compte non trouvé: {row['nom_compte']}"
                        )
                    except (ValueError, KeyError) as e:
                        messages.error(request, f"Erreur de format dans le fichier: {str(e)}")
                        raise

            messages.success(request, "Données réelles importées avec succès")

        except Exception as e:
            messages.error(request, f"Erreur lors de l'import: {str(e)}")

    return redirect('compare_real_data')

@login_required
def summary_comparison(request: HttpRequest) -> HttpResponse:
    """View to display yearly totals comparison across all accounts with inflation"""
    try:
        show_inflation = request.GET.get('inflation', 'true') == 'true'

        # Get all user's simulations
        simulations = Simulation.objects.filter(user=request.user).select_related('categorie')

        # Get all simulation results in one query
        all_simulation_results = ConsolidatedResult.objects.filter(
            simulation__user=request.user
        ).select_related('simulation')

        # Get all real data in one query
        all_real_data = RealAccountData.objects.filter(
            simulation__user=request.user
        ).select_related('simulation')

        # Get unique years from both datasets
        simulation_years = set(all_simulation_results.values_list('annee', flat=True))
        real_data_years = set(all_real_data.values_list('annee', flat=True))
        all_years = sorted(simulation_years.union(real_data_years))

        if not all_years:
            messages.error(request, "Aucune donnée disponible pour la comparaison")
            return render(request, 'summary_comparison.html', {
                'summary_data': [],
                'years': [],
                'yearly_totals': {},
                'chart_data': json.dumps({'labels': [], 'datasets': []}),
                'show_inflation': show_inflation
            })

        # Initialize yearly_totals
        yearly_totals = {str(year): {
            'simulated': Decimal('0'),
            'real': Decimal('0'),
            'real_adjusted': Decimal('0'),
            'difference': Decimal('0'),
            'difference_adjusted': Decimal('0'),
            'difference_percent': Decimal('0'),
            'difference_percent_adjusted': Decimal('0'),
            'inflation_rate': Decimal('0')
        } for year in all_years}

        # Process yearly totals
        for year in all_years:
            year_sim_results = [r for r in all_simulation_results if r.annee == year]
            year_real_results = [r for r in all_real_data if r.annee == year]

            # Calculate simulated total
            simulated_amount = sum(r.montant for r in year_sim_results)

            # Calculate real totals and inflation
            if year_real_results:
                real_amount = sum(r.montant_reel for r in year_real_results)
                # Calculate weighted average inflation rate
                total_real = sum(r.montant_reel for r in year_real_results)
                avg_inflation = sum(
                    r.taux_inflation * r.montant_reel for r in year_real_results
                ) / total_real if total_real else Decimal('0')

                # Calculate inflation-adjusted amount
                real_adjusted = sum(
                    r.montant_reel / (1 + r.taux_inflation / 100)
                    for r in year_real_results
                )
            else:
                real_amount = Decimal('0')
                real_adjusted = Decimal('0')
                avg_inflation = Decimal('0')

            str_year = str(year)
            yearly_totals[str_year].update({
                'simulated': simulated_amount,
                'real': real_amount,
                'real_adjusted': real_adjusted,
                'inflation_rate': avg_inflation,
                'difference': real_amount - simulated_amount,
                'difference_adjusted': real_adjusted - simulated_amount,
            })

            if simulated_amount:
                yearly_totals[str_year].update({
                    'difference_percent': (real_amount - simulated_amount) / simulated_amount * 100,
                    'difference_percent_adjusted': (real_adjusted - simulated_amount) / simulated_amount * 100
                })

        # Prepare summary data for each account
        summary_data = []
        for simulation in simulations:
            account_data = {
                'account_name': simulation.nom_compte,
                'category': simulation.categorie.category,
                'years': {}
            }

            sim_results = {
                str(r.annee): r.montant
                for r in all_simulation_results
                if r.simulation_id == simulation.id
            }

            real_results = {
                str(r.annee): r
                for r in all_real_data
                if r.simulation_id == simulation.id
            }

            for year in all_years:
                str_year = str(year)
                simulated = sim_results.get(str_year, Decimal('0'))
                real_data = real_results.get(str_year)

                year_data = {
                    'simulated': simulated,
                    'has_real_data': bool(real_data),
                    'real': Decimal('0'),
                    'real_adjusted': Decimal('0'),
                    'inflation_rate': Decimal('0'),
                    'difference': Decimal('0'),
                    'difference_adjusted': Decimal('0'),
                    'difference_percent': Decimal('0'),
                    'difference_percent_adjusted': Decimal('0')
                }

                if real_data:
                    real = real_data.montant_reel
                    inflation_rate = real_data.taux_inflation
                    real_adjusted = real / (1 + inflation_rate / 100)

                    year_data.update({
                        'real': real,
                        'real_adjusted': real_adjusted,
                        'inflation_rate': inflation_rate,
                        'difference': real - simulated,
                        'difference_adjusted': real_adjusted - simulated,
                    })

                    if simulated:
                        year_data.update({
                            'difference_percent': (real - simulated) / simulated * 100,
                            'difference_percent_adjusted': (real_adjusted - simulated) / simulated * 100
                        })

                account_data['years'][str_year] = year_data

            summary_data.append(account_data)

        # Prepare chart data with inflation adjustment
        labels = [str(year) for year in all_years]
        datasets = [
            {
                'label': 'Total Simulé',
                'data': [float(yearly_totals[year]['simulated']) for year in labels],
                'borderColor': 'rgb(54, 162, 235)',
                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                'borderWidth': 2
            },
            {
                'label': 'Total Réel Nominal',
                'data': [float(yearly_totals[year]['real']) for year in labels],
                'borderColor': 'rgb(255, 99, 132)',
                'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                'borderWidth': 2
            }
        ]

        if show_inflation:
            datasets.append({
                'label': 'Total Réel (Ajusté Inflation)',
                'data': [float(yearly_totals[year]['real_adjusted']) for year in labels],
                'borderColor': 'rgb(75, 192, 192)',
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'borderWidth': 2,
                'borderDash': [5, 5]
            })

        chart_data = {
            'labels': labels,
            'datasets': datasets
        }

        return render(request, 'summary_comparison.html', {
            'summary_data': summary_data,
            'yearly_totals': yearly_totals,
            'years': all_years,
            'chart_data': json.dumps(chart_data),
            'show_inflation': show_inflation
        })

    except Exception as e:
        logger.error(f"Error in summary comparison view: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur est survenue lors du chargement des données")
        return redirect('simulation')


@login_required
def manage_inflation_rates(request: HttpRequest) -> HttpResponse:
    """View to manage annual inflation rates"""
    if request.method == 'POST':
        form = AnnualInflationRateForm(request.POST)
        if form.is_valid():
            try:
                # Update or create inflation rate
                AnnualInflationRate.objects.update_or_create(
                    annee=form.cleaned_data['annee'],
                    defaults={
                        'taux_inflation': form.cleaned_data['taux_inflation'],
                        'commentaire': form.cleaned_data['commentaire']
                    }
                )
                messages.success(request, "Taux d'inflation mis à jour avec succès")
                return redirect('manage_inflation_rates')
            except Exception as e:
                logger.error(f"Error saving inflation rate: {str(e)}")
                messages.error(request, "Erreur lors de la sauvegarde du taux d'inflation")
    else:
        form = AnnualInflationRateForm()

    # Get all inflation rates
    inflation_rates = AnnualInflationRate.objects.all().order_by('-annee')

    # Prepare chart data
    chart_data = {
        'labels': [str(rate.annee) for rate in inflation_rates],
        'datasets': [{
            'label': "Taux d'inflation (%)",
            'data': [float(rate.taux_inflation) for rate in inflation_rates],
            'borderColor': 'rgb(75, 192, 192)',
            'backgroundColor': 'rgba(75, 192, 192, 0.2)',
            'borderWidth': 2
        }]
    }

    return render(request, 'manage_inflation_rates.html', {
        'form': form,
        'inflation_rates': inflation_rates,
        'chart_data': json.dumps(chart_data)
    })


@login_required
@require_http_methods(["POST"])
def delete_inflation_rate(request: HttpRequest, year: int) -> HttpResponse:
    """Delete an inflation rate entry"""
    try:
        rate = get_object_or_404(AnnualInflationRate, annee=year)
        rate.delete()
        messages.success(request, f"Taux d'inflation pour {year} supprimé")
        return JsonResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error deleting inflation rate: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": "Erreur lors de la suppression du taux"
        }, status=400)


@login_required
@require_http_methods(["POST"])
def recalculate_real_data(request: HttpRequest, simulation_id: int) -> HttpResponse:
    """Recalculate real data with current inflation rates."""
    try:
        simulation = get_object_or_404(Simulation, id=simulation_id, user=request.user)

        with transaction.atomic():
            # Get all real data entries for this simulation
            real_data_entries = RealAccountData.objects.filter(simulation=simulation)

            # Update each entry with current inflation rates
            for entry in real_data_entries:
                # Get current inflation rate for the year
                inflation_rate = AnnualInflationRate.objects.filter(
                    annee=entry.annee
                ).first()

                # Update with new inflation rate or default to 0
                new_taux_inflation = inflation_rate.taux_inflation if inflation_rate else Decimal('0')

                # Update the entry
                entry.taux_inflation = new_taux_inflation
                entry.montant_reel_ajuste = entry.montant_reel / (1 + new_taux_inflation / 100)
                entry.save()

        messages.success(request, "Calculs mis à jour avec succès")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error recalculating real data: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la mise à jour"
        }, status=500)


@login_required
def portfolio_list(request: HttpRequest) -> HttpResponse:
    """View to display user's portfolios."""
    portfolios = Portfolio.objects.filter(user=request.user)

    if request.method == 'POST':
        form = PortfolioForm(request.POST)
        if form.is_valid():
            portfolio = form.save(commit=False)
            portfolio.user = request.user
            portfolio.save()
            messages.success(request, "Portfolio créé avec succès")
            return redirect('portfolio_detail', portfolio_id=portfolio.id)
    else:
        form = PortfolioForm()

    return render(request, 'portfolio_list.html', {
        'portfolios': portfolios,
        'form': form
    })


@login_required
# views.py

@login_required
def portfolio_detail(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """View to display portfolio details and positions."""
    portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    positions = Position.objects.filter(portfolio=portfolio).select_related('stock')
    transactions = Transaction.objects.filter(portfolio=portfolio).select_related('stock')

    # Mettre à jour les données de marché si nécessaire
    for position in positions:
        if position.stock.needs_update():
            position.stock.update_market_data()

    # Calculer la valeur actuelle du portfolio
    total_market_value = sum(
        position.quantity * position.stock.current_price
        for position in positions
        if position.stock.current_price is not None
    )

    total_cost = sum(position.total_cost for position in positions)
    total_gain_loss = total_market_value - total_cost if total_market_value else None

    # Grouper les positions par type d'actif
    positions_by_type = {
        'STOCK': positions.filter(stock__asset_type='STOCK'),
        'ETF': positions.filter(stock__asset_type='ETF')
    }

    context = {
        'portfolio': portfolio,
        'positions': positions,
        'transactions': transactions,
        'total_market_value': total_market_value,
        'total_cost': total_cost,
        'total_gain_loss': total_gain_loss,
        'positions_by_type': positions_by_type,
    }

    return render(request, 'portfolio_detail.html', context)


@login_required
@login_required
def add_transaction(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """View to add a new transaction."""
    portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():  # Utilisez django.db.transaction.atomic()
                    # Créer la transaction
                    new_transaction = form.save(commit=False)
                    new_transaction.portfolio = portfolio
                    new_transaction.save()

                    # Update or create position
                    position, created = Position.objects.get_or_create(
                        portfolio=portfolio,
                        stock=new_transaction.stock,
                        defaults={
                            'quantity': 0,
                            'average_price': 0,
                            'purchase_date': new_transaction.date
                        }
                    )

                    if new_transaction.transaction_type == 'BUY':
                        # Calculate new average price and quantity for buy
                        total_cost = (position.quantity * position.average_price) + (
                                    new_transaction.quantity * new_transaction.price)
                        new_quantity = position.quantity + new_transaction.quantity
                        position.average_price = total_cost / new_quantity if new_quantity > 0 else 0
                        position.quantity = new_quantity
                    else:  # SELL
                        if new_transaction.quantity > position.quantity:
                            raise ValidationError("Quantité de vente supérieure à la position détenue")
                        position.quantity -= new_transaction.quantity

                    if position.quantity > 0:
                        position.save()
                    else:
                        position.delete()

                    messages.success(request, "Transaction enregistrée avec succès")
                    return redirect('portfolio_detail', portfolio_id=portfolio_id)

            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Error processing transaction: {str(e)}", exc_info=True)
                messages.error(request, "Une erreur est survenue lors du traitement de la transaction")
    else:
        form = TransactionForm()

    return render(request, 'add_transaction.html', {
        'form': form,
        'portfolio': portfolio
    })


@login_required
def stock_list(request: HttpRequest) -> HttpResponse:
    """View to manage stocks and ETFs."""
    stocks = Stock.objects.all().order_by('symbol')

    if request.method == 'POST':
        form = StockForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Titre ajouté avec succès")
            return redirect('stock_list')
    else:
        form = StockForm()

    return render(request, 'stock_list.html', {
        'stocks': stocks,
        'form': form
    })


@login_required
@require_http_methods(["POST"])
def delete_portfolio(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """Delete a portfolio and all its associated data."""
    try:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

        with transaction.atomic():
            # This will automatically delete all related positions and transactions due to CASCADE
            portfolio.delete()

        messages.success(request, "Portfolio supprimé avec succès")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error deleting portfolio {portfolio_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la suppression du portfolio"
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_stock(request: HttpRequest, stock_id: int) -> HttpResponse:
    """Delete a stock/ETF if it has no associated positions."""
    try:
        stock = get_object_or_404(Stock, id=stock_id)

        # Check if stock is used in any positions
        if Position.objects.filter(stock=stock).exists():
            return JsonResponse({
                "status": "error",
                "message": "Ce titre ne peut pas être supprimé car il est utilisé dans des positions actives"
            }, status=400)

        stock.delete()
        messages.success(request, "Titre supprimé avec succès")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error deleting stock {stock_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la suppression du titre"
        }, status=500)


@login_required
@require_http_methods(["POST"])
@login_required
@require_http_methods(["POST"])
def delete_transaction(request: HttpRequest, transaction_id: int) -> HttpResponse:
    """Delete a transaction and update the related position."""
    try:
        transaction_obj = get_object_or_404(Transaction, id=transaction_id)

        # Check if user owns the portfolio
        if transaction_obj.portfolio.user != request.user:
            raise PermissionDenied("Vous n'avez pas l'autorisation de supprimer cette transaction")

        with transaction.atomic():  # Utilisation de django.db.transaction
            # Get related position
            try:
                position = Position.objects.get(
                    portfolio=transaction_obj.portfolio,
                    stock=transaction_obj.stock
                )

                # Reverse the transaction effect on position
                if transaction_obj.transaction_type == 'BUY':
                    # Remove bought quantity
                    new_quantity = position.quantity - transaction_obj.quantity
                    if new_quantity < 0:
                        raise ValidationError("La suppression de cette transaction rendrait la quantité négative")

                    # Recalculate average price if quantity > 0
                    if new_quantity > 0:
                        total_cost = (position.quantity * position.average_price) - (
                                    transaction_obj.quantity * transaction_obj.price)
                        position.average_price = total_cost / new_quantity
                    position.quantity = new_quantity

                else:  # SELL
                    # Add back sold quantity
                    position.quantity += transaction_obj.quantity

                # Save or delete position based on quantity
                if position.quantity > 0:
                    position.save()
                else:
                    position.delete()

            except Position.DoesNotExist:
                # If no position exists, this is an error state
                raise ValidationError("Position introuvable pour cette transaction")

            # Delete the transaction
            transaction_obj.delete()

        messages.success(request, "Transaction supprimée avec succès")
        return JsonResponse({"status": "success"})

    except ValidationError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    except PermissionDenied as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=403)
    except Exception as e:
        logger.error(f"Error deleting transaction {transaction_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la suppression de la transaction"
        }, status=500)
