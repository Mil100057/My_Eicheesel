from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone


class Category(models.Model):
    COMPTE_TYPE = {
        "Courant": "Courant",
        "Epargne Financière": "Ep.Financière",
        "Assurance Vie": "Assurance Vie",
        "Epargne Entreprise": "Epargne Entreprise",
        "Immobilier": "Immobilier"
    }
    category = models.CharField(max_length=64, choices=COMPTE_TYPE, default='Courant')

    def __str__(self):
        return self.category

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"


class Simulation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='simulations'
    )
    categorie = models.ForeignKey(Category, on_delete=models.CASCADE)
    CURRENCY_TYPE = {
        "€": "Euros €"
    }
    nom_compte = models.CharField(max_length=64)
    montant_initial = models.DecimalField(max_digits=10, decimal_places=2)
    currency= models.CharField(max_length=24, choices=CURRENCY_TYPE, default='€')
    taux_rentabilite = models.FloatField()
    periode = models.IntegerField()
    annee_depart = models.IntegerField(default=2024)
    montant_fixe_annuel = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return self.nom_compte


class ConsolidatedResult(models.Model):
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)
    annee = models.IntegerField()
    montant = models.DecimalField(max_digits=20, decimal_places=2)
    nom_compte = models.CharField(max_length=100)

    def __str__(self):
       return str(self.nom_compte)


class RealAccountData(models.Model):
    """Model to store real account data for comparison with simulations"""
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)
    annee = models.IntegerField()
    montant_reel = models.DecimalField(max_digits=10, decimal_places=2)
    taux_inflation = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0,
        help_text="Taux d'inflation annuel en pourcentage"
    )
    montant_reel_ajuste = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Montant ajusté après inflation"
    )
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('simulation', 'annee')
        ordering = ['annee']
        verbose_name = "Données réelles"
        verbose_name_plural = "Données réelles"

    def save(self, *args, **kwargs):
        # Toujours calculer le montant ajusté
        if self.montant_reel is not None and self.taux_inflation is not None:
            self.montant_reel_ajuste = self.montant_reel / (1 + self.taux_inflation / 100)
        else:
            self.montant_reel_ajuste = self.montant_reel  # Si pas d'inflation, même montant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.simulation.nom_compte} - {self.annee}"

class AnnualInflationRate(models.Model):
    """Model to store annual inflation rates"""
    annee = models.IntegerField(unique=True)
    taux_inflation = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal('-100')),
            MaxValueValidator(Decimal('100'))
        ],
        help_text="Taux d'inflation annuel en pourcentage"
    )
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    commentaire = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-annee']
        verbose_name = "Taux d'inflation annuel"
        verbose_name_plural = "Taux d'inflation annuels"

    def __str__(self):
        return f"{self.annee}: {self.taux_inflation}%"

class Stock(models.Model):
    """Model for individual stocks and ETFs"""
    ASSET_TYPES = [
        ('STOCK', 'Action'),
        ('ETF', 'ETF'),
    ]

    symbol = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    asset_type = models.CharField(max_length=5, choices=ASSET_TYPES)
    description = models.TextField(blank=True)
    sector = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=3, default='EUR')
    current_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_change = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_change_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    volume = models.BigIntegerField(null=True, blank=True)
    last_update = models.DateTimeField(null=True, blank=True)

    def update_market_data(self):
        """Update stock market data from API."""
        from .utils import StockAPIClient

        api_client = StockAPIClient()
        quote_data = api_client.get_stock_quote(self.symbol)

        if quote_data:
            self.current_price = quote_data["price"]
            self.price_change = quote_data["change"]
            self.price_change_percent = quote_data["change_percent"]
            self.volume = quote_data["volume"]
            self.last_update = timezone.now()
            self.save()
            return True
        return False

    def needs_update(self, max_age_minutes: int = 15) -> bool:
        """Check if market data needs update."""
        if not self.last_update:
            return True

        age = timezone.now() - self.last_update
        return age.total_seconds() / 60 > max_age_minutes

    @property
    def market_value(self) -> str:
        """Format current price with currency."""
        if self.current_price:
            return f"{self.current_price} {self.currency}"
        return "N/A"

    @property
    def price_change_formatted(self) -> str:
        """Format price change with sign and currency."""
        if self.price_change:
            sign = "+" if self.price_change >= 0 else ""
            return f"{sign}{self.price_change} {self.currency}"
        return "N/A"

    @property
    def price_change_percent_formatted(self) -> str:
        """Format price change percentage with sign."""
        if self.price_change_percent:
            sign = "+" if self.price_change_percent >= 0 else ""
            return f"{sign}{self.price_change_percent}%"
        return "N/A"

    def __str__(self):
        return f"{self.symbol} - {self.name}"

    class Meta:
        verbose_name = "Titre"
        verbose_name_plural = "Titres"
        ordering = ['symbol']


class Portfolio(models.Model):
    """Model for user portfolios"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='portfolios'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"

    class Meta:
        verbose_name = "Portfolio"
        verbose_name_plural = "Portfolios"
        unique_together = ['user', 'name']


class Position(models.Model):
    """Model for positions in a portfolio"""
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=4)
    average_price = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.stock.symbol} ({self.quantity})"

    @property
    def total_cost(self):
        return self.quantity * self.average_price

    class Meta:
        verbose_name = "Position"
        verbose_name_plural = "Positions"
        unique_together = ['portfolio', 'stock']

    @property
    def current_value(self) -> Decimal:
        """Calcule la valeur actuelle de la position."""
        if self.stock.current_price:
            return self.quantity * self.stock.current_price
        return Decimal('0')

    @property
    def gain_loss(self) -> Decimal:
        """Calcule le gain ou la perte sur la position."""
        current_value = self.current_value
        if current_value:
            return current_value - self.total_cost
        return Decimal('0')

    @property
    def gain_loss_percent(self) -> Decimal:
        """Calcule le pourcentage de gain ou perte."""
        if self.total_cost and self.total_cost != 0:
            return (self.gain_loss / self.total_cost) * 100
        return Decimal('0')


class Transaction(models.Model):
    """Model for tracking buy/sell transactions"""
    TRANSACTION_TYPES = [
        ('BUY', 'Achat'),
        ('SELL', 'Vente'),
    ]

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT)
    transaction_type = models.CharField(max_length=4, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=4)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.transaction_type} {self.stock.symbol} ({self.quantity})"

    @property
    def total_amount(self):
        return (self.quantity * self.price) + self.fees

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-date']
