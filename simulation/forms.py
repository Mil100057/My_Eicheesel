from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Simulation, Category, RealAccountData, Stock, Portfolio, Position, Transaction, AnnualInflationRate
from decimal import Decimal
import csv
import io
from typing import List, Dict, Any, Optional



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['category']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            })
        }
        labels = {
            'category': 'Catégorie'
        }


class SimulationForm(forms.ModelForm):
    class Meta:
        model = Simulation
        fields = ['categorie', 'nom_compte', 'montant_initial', 'currency',
                  'taux_rentabilite', 'periode', 'annee_depart', 'montant_fixe_annuel']
        widgets = {
            'categorie': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'nom_compte': forms.TextInput(attrs={
                'class': 'form-control',
                'required': True
            }),
            'montant_initial': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'required': True
            }),
            'currency': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'taux_rentabilite': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'required': True
            }),
            'periode': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '50',
                'required': True
            }),
            'annee_depart': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '2020',
                'max': '2074',
                'required': True
            }),
            'montant_fixe_annuel': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'required': True
            }),
        }
        labels = {
            'categorie': 'Catégorie',
            'nom_compte': 'Nom du compte',
            'montant_initial': 'Montant initial',
            'currency': 'Devise',
            'taux_rentabilite': 'Taux de rentabilité (%)',
            'periode': 'Période (années)',
            'annee_depart': 'Année de départ',
            'montant_fixe_annuel': 'Montant fixe annuel'
        }
        help_texts = {
            'taux_rentabilite': 'Entrez le taux en pourcentage (ex: 5 pour 5%)',
            'periode': 'Nombre d\'années de simulation',
            'montant_fixe_annuel': 'Montant ajouté chaque année'
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.user = user  # Store the user instance

        # Get all categories from the COMPTE_TYPE choices
        self.fields['categorie'].queryset = Category.objects.all()
        self.fields['categorie'].empty_label = "Sélectionnez une catégorie"

    def save(self, commit=True):
        instance = super(SimulationForm, self).save(commit=False)
        if self.user:
            instance.user = self.user
        if commit:
            instance.save()
        return instance

class ChoixSimulation(forms.Form):
    choix = forms.ModelChoiceField(queryset=Simulation.objects.all(), label="Sélectionnez un Compte")

class RealDataForm(forms.ModelForm):
    """Form for entering real account data"""
    class Meta:
        model = RealAccountData
        fields = ['annee', 'montant_reel']
        widgets = {
            'annee': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '2000',
                'max': '2100',
                'required': True
            }),
            'montant_reel': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'required': True
            })
        }
        labels = {
            'annee': 'Année',
            'montant_reel': 'Montant réel'
        }


class AnnualInflationRateForm(forms.ModelForm):
    class Meta:
        model = AnnualInflationRate
        fields = ['annee', 'taux_inflation', 'commentaire']
        widgets = {
            'annee': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1900',
                'max': '2100',
            }),
            'taux_inflation': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
            }),
            'commentaire': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Source ou commentaire optionnel'
            })
        }
        labels = {
            'annee': 'Année',
            'taux_inflation': "Taux d'inflation (%)",
            'commentaire': 'Commentaire'
        }

class StockForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['symbol', 'name', 'asset_type', 'description', 'sector', 'currency']
        widgets = {
            'symbol': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'asset_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'sector': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
        }

class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['stock', 'quantity', 'average_price', 'purchase_date', 'notes']
        widgets = {
            'stock': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001'
            }),
            'average_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'purchase_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['stock', 'transaction_type', 'quantity', 'price', 'date', 'fees', 'notes']
        widgets = {
            'stock': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'fees': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SimulationCSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='Fichier CSV',
        help_text='Le fichier doit contenir les colonnes: categorie, nom_compte, montant_initial, currency, taux_rentabilite, periode, annee_depart, montant_fixe_annuel'
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_csv_file(self) -> List[Dict[str, Any]]:
        csv_file = self.cleaned_data['csv_file']

        if not csv_file.name.endswith('.csv'):
            raise ValidationError("Le fichier doit être au format CSV")

        # Read and validate CSV content
        try:
            decoded_file = csv_file.read().decode('utf-8')
            csv_data = csv.DictReader(io.StringIO(decoded_file), delimiter=';')

            required_fields = {
                'categorie', 'nom_compte', 'montant_initial', 'currency',
                'taux_rentabilite', 'periode', 'annee_depart', 'montant_fixe_annuel'
            }

            if not required_fields.issubset(csv_data.fieldnames):
                missing_fields = required_fields - set(csv_data.fieldnames)
                raise ValidationError(f"Colonnes manquantes: {', '.join(missing_fields)}")

            processed_data = []
            for row_num, row in enumerate(csv_data, start=2):  # start=2 because row 1 is headers
                try:
                    # Validate and convert data types
                    processed_row = {
                        'categorie': row['categorie'].strip(),
                        'nom_compte': row['nom_compte'].strip(),
                        'montant_initial': Decimal(row['montant_initial'].replace(',', '.')),
                        'currency': row['currency'].strip(),
                        'taux_rentabilite': float(row['taux_rentabilite'].replace(',', '.')),
                        'periode': int(row['periode']),
                        'annee_depart': int(row['annee_depart']),
                        'montant_fixe_annuel': Decimal(row['montant_fixe_annuel'].replace(',', '.'))
                    }

                    # Validate category exists
                    if not Category.objects.filter(category=processed_row['categorie']).exists():
                        raise ValidationError(f"Catégorie invalide à la ligne {row_num}: {processed_row['categorie']}")

                    # Validate currency
                    if processed_row['currency'] not in dict(Simulation.CURRENCY_TYPE):
                        raise ValidationError(f"Devise invalide à la ligne {row_num}: {processed_row['currency']}")

                    processed_data.append(processed_row)

                except (ValueError, TypeError) as e:
                    raise ValidationError(f"Erreur de format à la ligne {row_num}: {str(e)}")

            return processed_data

        except UnicodeDecodeError:
            raise ValidationError("Le fichier n'est pas encodé en UTF-8")
        except csv.Error as e:
            raise ValidationError(f"Erreur lors de la lecture du CSV: {str(e)}")

    def save(self) -> List[Simulation]:
        """Save the imported simulations to the database."""
        if not self.user:
            raise ValueError("User must be set to save simulations")

        processed_data = self.cleaned_data['csv_file']
        simulations = []

        try:
            with transaction.atomic():
                for row in processed_data:
                    category = Category.objects.get(category=row['categorie'])
                    simulation = Simulation(
                        user=self.user,
                        categorie=category,
                        nom_compte=row['nom_compte'],
                        montant_initial=row['montant_initial'],
                        currency=row['currency'],
                        taux_rentabilite=row['taux_rentabilite'],
                        periode=row['periode'],
                        annee_depart=row['annee_depart'],
                        montant_fixe_annuel=row['montant_fixe_annuel']
                    )
                    simulation.full_clean()  # Validate the model
                    simulations.append(simulation)

                # Bulk create all simulations
                Simulation.objects.bulk_create(simulations)

        except Exception as e:
            raise ValidationError(f"Erreur lors de la sauvegarde des simulations: {str(e)}")

        return simulations