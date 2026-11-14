"""KaamSetu account forms — email + password based, role aware.

Validation rules (name / mobile / password) ``accounts.validators`` me define
hain, taaki signup, profile aur future password-change flows sab ek hi policy
follow karein. Frontend JS inhi rules ko mirror karta hai; server hamesha
final authority hai.
"""
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password

from .models import User
from .validators import (
    StrongPasswordValidator, validate_indian_mobile, validate_indian_pincode,
    validate_name, validate_not_future_date,
)

# Password rules ka human-readable text (frontend strength meter bhi isi ko dikhata hai).
PASSWORD_HELP = StrongPasswordValidator().get_help_text()


class EmailLoginForm(forms.Form):
    """Login email + password se hota hai (username nahi).

    Yahan signup wali password-complexity apply NAHI hoti — purane valid
    accounts ko login karne se rokna nahi hai.
    """

    email = forms.EmailField(
        label='Email',
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Enter a valid email address, e.g. you@example.com.',
        },
        widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email',
                                       'placeholder': 'you@example.com', 'required': True,
                                       'data-validate': 'email'}),
    )
    password = forms.CharField(
        label='Password',
        error_messages={'required': 'Please enter your password.'},
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password',
                                          'placeholder': 'Enter your password', 'required': True,
                                          'data-validate': 'login-password'}),
    )
    remember_me = forms.BooleanField(required=False, initial=True, label='Remember me')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.user = None

    def clean_email(self):
        raw_email = self.data.get(self.add_prefix('email'), '')
        if any(character.isspace() for character in raw_email):
            raise forms.ValidationError('Email addresses cannot contain spaces.')
        return (self.cleaned_data.get('email') or '').lower()

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email')
        password = cleaned.get('password')
        # Dono valid hone par hi credential check karo, taaki field errors upar dikhein.
        if email and password:
            user = User.objects.filter(email__iexact=email).first()
            if user is None or not user.check_password(password):
                # Generic message — kabhi mat batao ki email exist karta hai ya nahi.
                raise forms.ValidationError(
                    'Wrong email or password. Please check and try again.'
                )
            if not user.is_active:
                raise forms.ValidationError('This account is not active. Contact support.')
            self.user = user
        return cleaned

    def get_user(self):
        return self.user


class RegisterForm(forms.Form):
    """Worker/employer signup — name, email, mobile, role, strong password, terms."""

    ROLE_CHOICES = (('worker', 'Worker'), ('employer', 'Employer'))

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.HiddenInput,
        error_messages={'invalid_choice': 'Please choose whether you are a worker or an employer.'},
    )
    full_name = forms.CharField(
        max_length=120, label='Name', strip=False,
        error_messages={
            'required': 'Please enter your name.',
            'max_length': 'Name is too long (120 characters max).',
        },
        widget=forms.TextInput(attrs={
            'autocomplete': 'name', 'placeholder': 'e.g. Aman Shaikh', 'required': True,
            'data-validate': 'name', 'minlength': '2', 'maxlength': '120',
        }),
    )
    email = forms.EmailField(
        label='Email address',
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Enter a valid email address, e.g. you@example.com.',
        },
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email', 'placeholder': 'you@example.com', 'required': True,
            'data-validate': 'email',
        }),
    )
    mobile = forms.CharField(
        max_length=10, strip=False, label='Mobile number',
        error_messages={
            'required': 'Please enter your mobile number.',
            'max_length': 'Mobile number must be exactly 10 digits.',
            'min_length': 'Mobile number must be exactly 10 digits.',
        },
        widget=forms.TextInput(attrs={
            'autocomplete': 'tel', 'inputmode': 'numeric', 'placeholder': '9876543210',
            'required': True, 'maxlength': '10', 'minlength': '10', 'pattern': '[6-9][0-9]{9}',
            'data-validate': 'mobile',
        }),
        help_text='10-digit Indian mobile number starting with 6, 7, 8 or 9.',
    )
    company_name = forms.CharField(
        max_length=160, required=False, label='Business / organization name',
        error_messages={'max_length': 'Business name is too long (160 characters max).'},
        widget=forms.TextInput(attrs={'autocomplete': 'organization',
                                      'placeholder': 'Your business name'}),
    )
    date_of_birth = forms.DateField(
        required=False, label='Date of birth',
        widget=forms.DateInput(attrs={'type': 'date', 'autocomplete': 'bday'}),
    )
    city = forms.CharField(
        required=False, max_length=120, label='City / town / village',
        widget=forms.TextInput(attrs={'autocomplete': 'address-level2'}),
    )
    state = forms.CharField(
        required=False, max_length=120, label='State',
        widget=forms.TextInput(attrs={'autocomplete': 'address-level1'}),
    )
    pincode = forms.CharField(
        required=False, max_length=6, label='PIN code',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'postal-code', 'maxlength': '6'}),
    )
    password = forms.CharField(
        label='Password',
        error_messages={'required': 'Please choose a password.'},
        help_text=PASSWORD_HELP,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password', 'placeholder': 'At least 8 characters',
            'required': True, 'data-validate': 'password',
        }),
    )
    confirm_password = forms.CharField(
        label='Confirm password',
        error_messages={'required': 'Please re-enter your password.'},
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password', 'placeholder': 'Re-enter your password',
            'required': True, 'data-validate': 'confirm',
        }),
    )
    terms = forms.BooleanField(
        label='I agree to the Terms and Conditions and Privacy Policy',
        error_messages={'required': 'Please accept the Terms and Conditions to continue.'},
    )

    field_order = ['role', 'full_name', 'email', 'mobile', 'company_name',
                   'date_of_birth', 'city', 'state', 'pincode',
                   'password', 'confirm_password', 'terms']

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name') or ''
        validate_name(name)
        if len(name) < 2:
            raise forms.ValidationError('Please enter your name (at least 2 characters).')
        return name.strip()

    def clean_email(self):
        raw_email = self.data.get(self.add_prefix('email'), '')
        if any(character.isspace() for character in raw_email):
            raise forms.ValidationError('Email addresses cannot contain spaces.')
        email = (self.cleaned_data['email'] or '').lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists. Please log in.')
        return email

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile') or ''
        validate_indian_mobile(mobile)
        if User.objects.filter(phone=mobile).exists():
            raise forms.ValidationError('This mobile number is already registered.')
        return mobile

    def clean_date_of_birth(self):
        value = self.cleaned_data.get('date_of_birth')
        validate_not_future_date(value)
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get('pincode') or '').strip()
        validate_indian_pincode(value)
        return value

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            # Django settings ke AUTH_PASSWORD_VALIDATORS chalte hain
            # (min length 8 + uppercase/lowercase/number/special + common password).
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('confirm_password')
        if password and confirm and password != confirm:
            self.add_error('confirm_password', 'Passwords do not match.')
        if cleaned.get('role') == 'employer' and not (cleaned.get('company_name') or '').strip():
            self.add_error('company_name', 'Please add your business or organization name.')
        return cleaned

    def save(self, commit=True):
        data = self.cleaned_data
        role = data['role']
        user = User(
            username=data['email'],
            email=data['email'],
            name=data['full_name'],
            phone=data['mobile'],
            role=User.Role.WORKER if role == 'worker' else User.Role.EMPLOYER,
        )
        user.set_password(data['password'])
        if commit:
            from django.db import transaction

            with transaction.atomic():
                user.save()
                if role == 'worker':
                    from workers.models import WorkerProfile

                    WorkerProfile.objects.create(
                        user=user, full_name=data['full_name'],
                        mobile=data['mobile'], email=data['email'],
                        date_of_birth=data.get('date_of_birth'),
                        village=data.get('city', ''), state=data.get('state', ''),
                        pincode=data.get('pincode', ''),
                    )
                else:
                    from employers.models import EmployerProfile

                    EmployerProfile.objects.create(
                        user=user, business_name=data['company_name'],
                        contact_name=data['full_name'],
                        contact_date_of_birth=data.get('date_of_birth'),
                        city=data.get('city', ''), state=data.get('state', ''),
                        pincode=data.get('pincode', ''),
                    )
        return user


class NormalizedPasswordResetForm(PasswordResetForm):
    """Password-reset request with the same clear email feedback as login."""

    email = forms.EmailField(
        label='Email address',
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Enter a valid email address, e.g. you@example.com.',
        },
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email', 'placeholder': 'you@example.com', 'required': True,
            'data-validate': 'email',
        }),
    )

    def clean_email(self):
        raw_email = self.data.get(self.add_prefix('email'), '')
        if any(character.isspace() for character in raw_email):
            raise forms.ValidationError('Email addresses cannot contain spaces.')
        return (self.cleaned_data.get('email') or '').lower()


class PasswordFieldsMixin:
    """Use the shared frontend affordances for Django's secure password forms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == 'old_password':
                field.widget.attrs.update({
                    'autocomplete': 'current-password', 'placeholder': 'Current password',
                    'data-validate': 'login-password', 'required': True,
                })
            elif field_name == 'new_password1':
                field.widget.attrs.update({
                    'autocomplete': 'new-password', 'placeholder': 'At least 8 characters',
                    'data-validate': 'password', 'required': True,
                })
            elif field_name == 'new_password2':
                field.widget.attrs.update({
                    'autocomplete': 'new-password', 'placeholder': 'Re-enter your password',
                    'data-validate': 'confirm', 'required': True,
                })


class StrongSetPasswordForm(PasswordFieldsMixin, SetPasswordForm):
    pass


class StrongPasswordChangeForm(PasswordFieldsMixin, PasswordChangeForm):
    pass
