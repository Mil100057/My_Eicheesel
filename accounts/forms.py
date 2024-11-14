from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator
import re

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'email'
        })
    )

    # Add stronger password requirements
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password'
        }),
        validators=[MinLengthValidator(12)]
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'username'
            })
        }

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            # Check for password complexity
            if not any(char.isdigit() for char in password):
                raise forms.ValidationError('Password must contain at least one number.')
            if not any(char.isupper() for char in password):
                raise forms.ValidationError('Password must contain at least one uppercase letter.')
            if not any(char.islower() for char in password):
                raise forms.ValidationError('Password must contain at least one lowercase letter.')
            if not any(char in '!@#$%^&*()' for char in password):
                raise forms.ValidationError('Password must contain at least one special character (!@#$%^&*()).')
        return password

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Prevent username enumeration by checking format first
            if not re.match(r'^[\w.@+-]+$', username):
                raise forms.ValidationError('Username may only contain letters, numbers, and @/./+/-/_ characters.')
            # Check length
            if len(username) < 3:
                raise forms.ValidationError('Username must be at least 3 characters long.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Case-insensitive email check
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('This email address is already in use.')
        return email.lower()  # Normalize email to lowercase


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'autocomplete': 'current-password'
        })
    )