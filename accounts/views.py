from django.contrib.auth import get_user_model, login, logout, authenticate
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
import time

from accounts.forms import CustomUserCreationForm, CustomAuthenticationForm

User = get_user_model()


@csrf_protect
@never_cache
def signup(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # Add a small delay to prevent timing attacks
            time.sleep(0.1)
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            # Generic error message to prevent user enumeration
            messages.error(request, 'Please check your input and try again.')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/signup.html', {'form': form})


@sensitive_post_parameters()
@csrf_protect
@never_cache
def login_user(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            # Add a small delay to prevent timing attacks
            time.sleep(0.1)
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)

                # Secure redirect handling
                next_url = request.GET.get('next', settings.LOGIN_REDIRECT_URL)
                if not url_has_allowed_host_and_scheme(
                        url=next_url,
                        allowed_hosts={request.get_host()},
                        require_https=request.is_secure()
                ):
                    next_url = settings.LOGIN_REDIRECT_URL
                return HttpResponseRedirect(next_url)

        # Generic error message to prevent user enumeration
        messages.error(request, 'Invalid credentials.')
    else:
        form = CustomAuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
@never_cache
def logout_user(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect(settings.LOGIN_URL)


@login_required
@never_cache
def profile(request):
    return render(request, 'accounts/profile.html')