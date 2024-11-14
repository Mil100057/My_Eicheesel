from django.contrib import admin
from django.urls import path, include
from .views import base

urlpatterns = [
    path('simulation/', include('simulation.urls')),
    #path('signup/', include('accounts.urls')),
    #path('logout/', include('accounts.urls')),
    #path('login/', include('accounts.urls')),
    path('accounts/', include('accounts.urls')),
    path('admin/', admin.site.urls),
    path('', base, name="base"),
]
