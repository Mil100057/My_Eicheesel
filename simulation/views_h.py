from datetime import datetime
from decimal import Decimal
from typing import (
    Tuple, List, TypedDict, Optional, Dict, Any, Union,
    Sequence, Iterator, cast, TypeVar, Set
)
import json
import logging
import csv
from django.contrib.auth.decorators import login_required
from django.core.checks import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.db.models import QuerySet
from django.core.exceptions import ValidationError, PermissionDenied
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils.text import slugify
from .forms import (
    SimulationForm, RealDataForm, PortfolioForm, PositionForm,
    TransactionForm, StockForm
)
from .models import (
    Simulation, Category, ConsolidatedResult, RealAccountData,
    Portfolio, Position, Transaction, Stock
)

logger = logging.getLogger(__name__)

# Custom type definitions
ChartDataPoint = TypedDict('ChartDataPoint', {
    'label': str,
    'data': List[float],
    'backgroundColor': str,
    'borderColor': str,
    'borderWidth': int,
    'fill': Optional[bool]
})

ChartData = TypedDict('ChartData', {
    'labels': List[str],
    'datasets': List[ChartDataPoint]
})


@login_required
@require_http_methods(["GET", "POST"])
def category(request: HttpRequest) -> HttpResponse:
    """View to manage categories."""
    if request.method == "POST":
        category_name: str = request.POST.get('category', '')
        try:
            exists: bool = Category.objects.filter(category=category_name).exists()

            if exists:
                messages.Warning(request, "Cette catégorie existe déjà.")
            else:
                new_category: Category = Category.objects.create(category=category_name)
                messages.Warning(request, "Catégorie ajoutée avec succès.")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    "status": "success",
                    "message": "Catégorie ajoutée avec succès."
                })

        except Exception as e:
            logger.error(f"Error creating category: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    "status": "error",
                    "message": "Une erreur est survenue lors de la création de la catégorie."
                }, status=500)

    categories: QuerySet[Category] = Category.objects.all().order_by('category')
    return render(request, 'view_category.html', {
        "categories": categories,
        "compte_types": Category.COMPTE_TYPE
    })


@login_required
def name(request: HttpRequest) -> HttpResponse:
    """View to display names."""
    names: QuerySet[Simulation] = Simulation.objects.filter(user=request.user)
    return render(request, 'view_name.html', {"names": names})

def calculate_simulation_results(simulation_instance: Simulation) -> None:
    """Calculate and store simulation results for a simulation."""
    try:
        if not validate_simulation_inputs(simulation_instance):
            raise ValidationError("Invalid calculation parameters")

        montant_actuel: Decimal = Decimal(str(simulation_instance.montant_initial))
        taux: Decimal = Decimal(str(simulation_instance.taux_rentabilite)) / 100
        montant_fixe: Decimal = Decimal(str(simulation_instance.montant_fixe_annuel))

        with transaction.atomic():
            # Delete existing results
            ConsolidatedResult.objects.filter(simulation=simulation_instance).delete()

            results_to_create: List[ConsolidatedResult] = [
                ConsolidatedResult(
                    simulation=simulation_instance,
                    annee=simulation_instance.annee_depart,
                    montant=montant_actuel,
                    nom_compte=simulation_instance.nom_compte
                )
            ]

            for annee in range(
                    simulation_instance.annee_depart + 1,
                    simulation_instance.annee_depart + simulation_instance.periode + 1
            ):
                montant_actuel = montant_actuel * (1 + taux)
                montant_actuel += montant_fixe

                results_to_create.append(
                    ConsolidatedResult(
                        simulation=simulation_instance,
                        annee=annee,
                        montant=montant_actuel,
                        nom_compte=simulation_instance.nom_compte
                    )
                )

            ConsolidatedResult.objects.bulk_create(results_to_create)

    except (ValueError, TypeError, ValidationError) as e:
        logger.error(f"Error calculating simulation results: {str(e)}")
        raise ValidationError("Invalid calculation parameters")
    except Exception as e:
        logger.error(f"Unexpected error in calculation: {str(e)}", exc_info=True)
        raise ValidationError("Une erreur est survenue lors du calcul")

def validate_simulation_inputs(simulation: Simulation) -> bool:
    """Validate simulation input parameters."""
    try:
        if simulation.montant_initial < 0 or simulation.montant_fixe_annuel < 0:
            return False

        if not -100 <= simulation.taux_rentabilite <= 100:
            return False

        if not 1 <= simulation.periode <= 50:
            return False

        current_year: int = datetime.now().year
        if not current_year - 5 <= simulation.annee_depart <= current_year + 1:
            return False

        return True

    except Exception as e:
        logger.error(f"Error validating simulation inputs: {str(e)}")
        return False

@login_required
def simulation(request: HttpRequest) -> HttpResponse:
    """Handle simulation creation and display."""
    if request.method != 'POST':
        form: SimulationForm = SimulationForm(user=request.user)
        return render(request, 'simulation.html', {'form': form})

    try:
        form: SimulationForm = SimulationForm(request.POST, user=request.user)

        if not form.is_valid():
            return render(request, 'simulation.html', {'form': form})

        with transaction.atomic():
            simulation_instance: Simulation = form.save(commit=False)
            simulation_instance.user = request.user

            if not validate_simulation_inputs(simulation_instance):
                form.add_error(None, "Les paramètres de simulation sont invalides")
                return render(request, 'simulation.html', {'form': form})

            simulation_instance.save()

            try:
                calculate_simulation_results(simulation_instance)

                consolidated_results: QuerySet[ConsolidatedResult] = ConsolidatedResult.objects.filter(
                    simulation=simulation_instance
                ).order_by('annee')

                chart_labels: List[str]
                chart_data: List[ChartDataPoint]
                chart_labels, chart_data = prepare_chart_data_base(consolidated_results)

                messages.Warning(request, "Simulation créée avec succès")

                return render(request, 'resultats.html', {
                    'consolidated_results': consolidated_results,
                    'simulation_instance': simulation_instance,
                    'chart_labels': json.dumps(chart_labels),
                    'chart_data': json.dumps(chart_data)
                })

            except ValidationError as e:
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

def prepare_chart_data_base(
    consolidated_results: QuerySet[ConsolidatedResult],
    cumulative: bool = False,
    group_by_field: str = 'category'
) -> Tuple[List[str], List[ChartDataPoint]]:
    """Prepare base chart data."""
    if not consolidated_results.exists():
        return [], []

    colors: List[Dict[str, str]] = [
        {'backgroundColor': 'rgba(54, 162, 235, 0.2)', 'borderColor': 'rgb(54, 162, 235)'},
        {'backgroundColor': 'rgba(255, 99, 132, 0.2)', 'borderColor': 'rgb(255, 99, 132)'},
        {'backgroundColor': 'rgba(255, 206, 86, 0.2)', 'borderColor': 'rgb(255, 206, 86)'},
        {'backgroundColor': 'rgba(75, 192, 192, 0.2)', 'borderColor': 'rgb(75, 192, 192)'},
        {'backgroundColor': 'rgba(153, 102, 255, 0.2)', 'borderColor': 'rgb(153, 102, 255)'},
        {'backgroundColor': 'rgba(255, 159, 64, 0.2)', 'borderColor': 'rgb(255, 159, 64)'},
    ]

    years: List[int] = sorted(set(result.annee for result in consolidated_results))
    chart_labels: List[str] = [str(year) for year in years]

    if cumulative:
        data_by_simulation: Dict[int, Dict[str, Union[str, Dict[str, float]]]] = {}
        yearly_totals: Dict[str, float] = {str(year): 0.0 for year in years}

        for result in consolidated_results:
            sim_id: int = result.simulation.id
            group_key: str = (
                result.simulation.categorie.category if group_by_field == 'category'
                else result.simulation.nom_compte
            )

            if sim_id not in data_by_simulation:
                data_by_simulation[sim_id] = {
                    'group': group_key,
                    'values': {str(year): 0.0 for year in years}
                }

            year_str: str = str(result.annee)
            data_by_simulation[sim_id]['values'][year_str] = float(result.montant)

        for sim_data in data_by_simulation.values():
            running_total: float = 0.0
            for year in years:
                year_str = str(year)
                values_dict = cast(Dict[str, Dict[str, float]], sim_data)
                current_value: float = values_dict['values'][year_str]

                if current_value > 0:
                    running_total = current_value
                else:
                    values_dict['values'][year_str] = running_total

                yearly_totals[year_str] += values_dict['values'][year_str]

        label: str = 'Total tous comptes' if group_by_field == 'account' else 'Total toutes catégories'
        chart_data: List[ChartDataPoint] = [{
            'label': label,
            'data': [yearly_totals[str(year)] for year in years],
            **colors[0],
            'borderWidth': 2,
            'fill': True
        }]

    else:
        data_by_group: Dict[str, Dict[str, float]] = {}

        for result in consolidated_results:
            group_key: str = (
                result.simulation.categorie.category if group_by_field == 'category'
                else result.simulation.nom_compte
            )

            if group_key not in data_by_group:
                data_by_group[group_key] = {str(year): 0.0 for year in years}

            year_str: str = str(result.annee)
            data_by_group[group_key][year_str] += float(result.montant)

        chart_data = []
        for idx, (group_key, values) in enumerate(sorted(data_by_group.items())):
            color_idx: int = idx % len(colors)
            dataset: ChartDataPoint = {
                'label': group_key,
                'data': [values[str(year)] for year in years],
                **colors[color_idx],
                'borderWidth': 2,
                'fill': None
            }
            chart_data.append(dataset)

    return chart_labels, chart_data

def prepare_chart_data_by_category(
    consolidated_results: QuerySet[ConsolidatedResult],
    cumulative: bool = False
) -> Tuple[List[str], List[ChartDataPoint]]:
    """Prepare chart data grouped by category."""
    return prepare_chart_data_base(consolidated_results, cumulative, 'category')

def prepare_chart_data_by_account(
    consolidated_results: QuerySet[ConsolidatedResult],
    cumulative: bool = False
) -> Tuple[List[str], List[ChartDataPoint]]:
    """Prepare chart data grouped by account."""
    return prepare_chart_data_base(consolidated_results, cumulative, 'account')

@login_required
def results_list_by_cat(request: HttpRequest) -> HttpResponse:
    """Display results grouped by category."""
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
            simulations: QuerySet[Simulation] = Simulation.objects.filter(user=request.user)
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
        messages.Warning(request, "Une erreur est survenue lors du traitement des données")

    return render(request, 'results_list_by_cat.html', {
        'categories': categories,
        'consolidated_results': consolidated_results,
        'chart_data': json.dumps(chart_data),
        'chart_labels': json.dumps(chart_labels),
        'selected_category': selected_category,
        'cumulative': cumulative,
    })

def export_results_to_csv(
    results: QuerySet[ConsolidatedResult],
    filename_prefix: str
) -> HttpResponse:
    """Export results to CSV file."""
    response: HttpResponse = HttpResponse(content_type='text/csv')
    timestamp: str = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="{filename_prefix}_{timestamp}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Année', 'Catégorie', 'Nom du compte', 'Montant', 'Devise'])

    for result in results:
        writer.writerow([
            result.annee,
            result.simulation.categorie.category,
            result.simulation.nom_compte,
            int(result.montant),
            '€'
        ])

    return response

@login_required
def export_results_by_cat(request: HttpRequest) -> HttpResponse:
    """Export results by category to CSV."""
    try:
        selected_category: Optional[str] = request.GET.get('category')

        if selected_category == "all":
            simulations: QuerySet[Simulation] = Simulation.objects.filter(user=request.user)
            filename_prefix: str = "toutes_categories"
        else:
            simulations = Simulation.objects.filter(
                categorie__category=selected_category,
                user=request.user
            )
            filename_prefix = f"categorie_{slugify(selected_category)}"

        results: QuerySet[ConsolidatedResult] = ConsolidatedResult.objects.filter(
            simulation__in=simulations
        ).select_related(
            'simulation',
            'simulation__categorie'
        ).order_by('annee', 'simulation__categorie__category', 'simulation__nom_compte')

        return export_results_to_csv(results, filename_prefix)

    except Exception as e:
        logger.error(f"Error exporting category results: {str(e)}", exc_info=True)
        messages.Warning(request, "Une erreur est survenue lors de l'export")
        return redirect('results_list_by_cat')

@login_required
def export_results_by_name(request: HttpRequest) -> HttpResponse:
    """Export results by name to CSV."""
    try:
        selected_name: Optional[str] = request.GET.get('account_name')

        if selected_name == "all":
            simulations: QuerySet[Simulation] = Simulation.objects.filter(user=request.user)
            filename_prefix: str = "tous_comptes"
        else:
            simulations = Simulation.objects.filter(
                nom_compte=selected_name,
                user=request.user
            )
            filename_prefix = f"compte_{slugify(selected_name)}"

        results: QuerySet[ConsolidatedResult] = ConsolidatedResult.objects.filter(
            simulation__in=simulations
        ).select_related(
            'simulation',
            'simulation__categorie'
        ).order_by('annee', 'simulation__nom_compte')

        return export_results_to_csv(results, filename_prefix)

    except Exception as e:
        logger.error(f"Error exporting account results: {str(e)}", exc_info=True)
        messages.Warning(request, "Une erreur est survenue lors de l'export")
        return redirect('results_list_by_name')

@login_required
def portfolio_list(request: HttpRequest) -> HttpResponse:
    """Display list of portfolios."""
    portfolios: QuerySet[Portfolio] = Portfolio.objects.filter(user=request.user)

    if request.method == 'POST':
        form: PortfolioForm = PortfolioForm(request.POST)
        if form.is_valid():
            portfolio: Portfolio = form.save(commit=False)
            portfolio.user = request.user
            portfolio.save()
            messages.Warning(request, "Portfolio créé avec succès")
            return redirect('portfolio_detail', portfolio_id=portfolio.id)
    else:
        form = PortfolioForm()

    return render(request, 'portfolio_list.html', {
        'portfolios': portfolios,
        'form': form
    })

@login_required
def portfolio_detail(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """Display portfolio details and positions."""
    portfolio: Portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    positions: QuerySet[Position] = Position.objects.filter(portfolio=portfolio).select_related('stock')
    transactions: QuerySet[Transaction] = Transaction.objects.filter(portfolio=portfolio).select_related('stock')

    for position in positions:
        if position.stock.needs_update():
            position.stock.update_market_data()

    total_market_value: Decimal = sum(
        position.quantity * position.stock.current_price
        for position in positions
        if position.stock.current_price is not None
    )

    total_cost: Decimal = sum(position.total_cost for position in positions)
    total_gain_loss: Optional[Decimal] = total_market_value - total_cost if total_market_value else None

    positions_by_type: Dict[str, QuerySet[Position]] = {
        'STOCK': positions.filter(stock__asset_type='STOCK'),
        'ETF': positions.filter(stock__asset_type='ETF')
    }

    return render(request, 'portfolio_detail.html', {
        'portfolio': portfolio,
        'positions': positions,
        'transactions': transactions,
        'total_market_value': total_market_value,
        'total_cost': total_cost,
        'total_gain_loss': total_gain_loss,
        'positions_by_type': positions_by_type,
    })

@login_required
@require_http_methods(["POST"])
def delete_portfolio(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """Delete a portfolio and all associated data."""
    try:
        portfolio: Portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

        with transaction.atomic():
            portfolio.delete()

        messages.Warning(request, "Portfolio supprimé avec succès")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error deleting portfolio {portfolio_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la suppression du portfolio"
        }, status=500)


@login_required
def add_transaction(request: HttpRequest, portfolio_id: int) -> HttpResponse:
    """View to add a new transaction."""
    portfolio: Portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

    if request.method == 'POST':
        form: TransactionForm = TransactionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    new_transaction: Transaction = form.save(commit=False)
                    new_transaction.portfolio = portfolio
                    new_transaction.save()

                    # Update or create position
                    position: Position
                    created: bool
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
                        total_cost: Decimal = (position.quantity * position.average_price) + (
                                new_transaction.quantity * new_transaction.price)
                        new_quantity: Decimal = position.quantity + new_transaction.quantity
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

                    messages.Warning(request, "Transaction enregistrée avec succès")
                    return redirect('portfolio_detail', portfolio_id=portfolio_id)

            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Error processing transaction: {str(e)}", exc_info=True)
                messages.Warning(request, "Une erreur est survenue lors du traitement de la transaction")
    else:
        form = TransactionForm()

    return render(request, 'add_transaction.html', {
        'form': form,
        'portfolio': portfolio
    })


@login_required
def stock_list(request: HttpRequest) -> HttpResponse:
    """View to manage stocks and ETFs."""
    stocks: QuerySet[Stock] = Stock.objects.all().order_by('symbol')

    if request.method == 'POST':
        form: StockForm = StockForm(request.POST)
        if form.is_valid():
            form.save()
            messages.Warning(request, "Titre ajouté avec succès")
            return redirect('stock_list')
    else:
        form = StockForm()

    return render(request, 'stock_list.html', {
        'stocks': stocks,
        'form': form
    })


@login_required
@require_http_methods(["POST"])
def delete_stock(request: HttpRequest, stock_id: int) -> HttpResponse:
    """Delete a stock/ETF if it has no associated positions."""
    try:
        stock: Stock = get_object_or_404(Stock, id=stock_id)

        if Position.objects.filter(stock=stock).exists():
            return JsonResponse({
                "status": "error",
                "message": "Ce titre ne peut pas être supprimé car il est utilisé dans des positions actives"
            }, status=400)

        stock.delete()
        messages.Warning(request, "Titre supprimé avec succès")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error deleting stock {stock_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Une erreur est survenue lors de la suppression du titre"
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_transaction(request: HttpRequest, transaction_id: int) -> HttpResponse:
    """Delete a transaction and update the related position."""
    try:
        transaction_obj: Transaction = get_object_or_404(Transaction, id=transaction_id)

        if transaction_obj.portfolio.user != request.user:
            raise PermissionDenied("Vous n'avez pas l'autorisation de supprimer cette transaction")

        with transaction.atomic():
            try:
                position: Position = Position.objects.get(
                    portfolio=transaction_obj.portfolio,
                    stock=transaction_obj.stock
                )

                if transaction_obj.transaction_type == 'BUY':
                    new_quantity: Decimal = position.quantity - transaction_obj.quantity
                    if new_quantity < 0:
                        raise ValidationError("La suppression de cette transaction rendrait la quantité négative")

                    if new_quantity > 0:
                        total_cost: Decimal = (position.quantity * position.average_price) - (
                                transaction_obj.quantity * transaction_obj.price)
                        position.average_price = total_cost / new_quantity
                    position.quantity = new_quantity

                else:  # SELL
                    position.quantity += transaction_obj.quantity

                if position.quantity > 0:
                    position.save()
                else:
                    position.delete()

            except Position.DoesNotExist:
                raise ValidationError("Position introuvable pour cette transaction")

            transaction_obj.delete()

        messages.Warning(request, "Transaction supprimée avec succès")
        return JsonResponse({"status": "success"})

    except ValidationError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    except PermissionDenied as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=403)
    except Exception as e:
        logger.error(f"Error deleting transaction {transaction_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": "Erreur lors de la suppression de la transaction"
        }, status=500)


@login_required
def compare_real_data(request: HttpRequest) -> HttpResponse:
    """View to display and manage real account data comparison."""
    accounts: QuerySet[Simulation] = Simulation.objects.filter(
        user=request.user
    ).order_by('nom_compte')

    selected_account: Optional[str] = request.GET.get('account')
    simulation_data: Optional[QuerySet[ConsolidatedResult]] = None
    real_data: Optional[QuerySet[RealAccountData]] = None
    real_data_form: Optional[RealDataForm] = None

    if selected_account:
        try:
            simulation: Simulation = get_object_or_404(
                Simulation,
                id=selected_account,
                user=request.user
            )

            if request.method == 'POST':
                form: RealDataForm = RealDataForm(request.POST)
                if form.is_valid():
                    real_data_entry: RealAccountData = form.save(commit=False)
                    real_data_entry.simulation = simulation

                    RealAccountData.objects.update_or_create(
                        simulation=simulation,
                        annee=form.cleaned_data['annee'],
                        defaults={'montant_reel': form.cleaned_data['montant_reel']}
                    )

                    messages.Warning(request, "Données réelles mises à jour avec succès")
                    return redirect(f'{request.path}?account={selected_account}')

            simulation_data = ConsolidatedResult.objects.filter(
                simulation=simulation
            ).order_by('annee')

            real_data = RealAccountData.objects.filter(
                simulation=simulation
            ).order_by('annee')

            years: List[int] = sorted(set(
                list(simulation_data.values_list('annee', flat=True)) +
                list(real_data.values_list('annee', flat=True))
            ))

            chart_data: Dict[str, Any] = {
                'labels': [str(year) for year in years],
                'datasets': [
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
                        'label': 'Données réelles',
                        'data': [next(
                            (float(r.montant_reel) for r in real_data if r.annee == year),
                            None
                        ) for year in years],
                        'borderColor': 'rgb(255, 99, 132)',
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderWidth': 2
                    }
                ]
            }

            real_data_form = RealDataForm()

            return render(request, 'compare_real_data.html', {
                'accounts': accounts,
                'selected_account': simulation,
                'simulation_data': simulation_data,
                'real_data': real_data,
                'real_data_form': real_data_form,
                'chart_data': json.dumps(chart_data)
            })

        except Simulation.DoesNotExist:
            messages.Warning(request, "Compte non trouvé")

    return render(request, 'compare_real_data.html', {
        'accounts': accounts
    })