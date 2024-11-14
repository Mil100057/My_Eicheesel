from django.contrib import admin
from .models import Simulation, Category, ConsolidatedResult, RealAccountData

# Enregistre le modèle Simulation dans l'interface d'administration
admin.site.register(Category)
admin.site.register(Simulation)
admin.site.register(ConsolidatedResult)
admin.site.register(RealAccountData)