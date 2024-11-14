from django.urls import path
from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("logout/", views.logout_user, name="logout"),
    path("login/", views.login_user, name="login"),
    path("profile/", views.profile, name="profile"),
    path('', views.profile, name='profile'),

]