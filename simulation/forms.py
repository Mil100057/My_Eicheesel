from django import forms
from .models import Simulation, Category, RealAccountData, Stock, Portfolio, Position, Transaction, AnnualInflationRate


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