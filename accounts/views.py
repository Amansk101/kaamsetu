"""KaamSetu authentication views — role aware email/password login + signup."""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    EmailLoginForm,
    NormalizedPasswordResetForm,
    RegisterForm,
    StrongPasswordChangeForm,
    StrongSetPasswordForm,
)

ROLES = ('worker', 'employer')
BACKEND = 'accounts.backends.EmailBackend'


def _safe_next(request, fallback):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


def login_view(request):
    """Single login page. ``?role=worker|employer`` chune to form, warna chooser."""
    if request.user.is_authenticated:
        return redirect('core:go')

    role = request.GET.get('role') or request.POST.get('role')
    if role not in ROLES:
        return render(request, 'accounts/login.html', {'mode': 'choose'})

    form = EmailLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        if user.role != role and user.role != 'admin':
            form.add_error(
                None,
                f'These details did not match a {role} account. '
                f'Check your details or create a {role} account.',
            )
        else:
            login(request, user, backend=BACKEND)
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            messages.success(request, f'Welcome back, {user.display_name}.')
            return redirect(_safe_next(request, reverse('core:go')))

    return render(request, 'accounts/login.html', {'mode': 'form', 'role': role, 'form': form})


def register_view(request):
    """Single registration page. ``?role=worker|employer`` chune to form, warna chooser."""
    if request.user.is_authenticated:
        return redirect('core:go')

    role = request.GET.get('role') or request.POST.get('role')
    if role not in ROLES:
        return render(request, 'accounts/register.html', {'mode': 'choose'})

    form = RegisterForm(request.POST or None, initial={'role': role})
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend=BACKEND)
        if user.is_worker:
            messages.success(request, 'Your account is ready. Let us complete your profile.')
            return redirect('workers:profile')
        messages.success(request, 'Your business account is ready. Post your first job.')
        return redirect('employers:dashboard')

    return render(request, 'accounts/register.html', {'mode': 'form', 'role': role, 'form': form})


def logout_view(request):
    """Logout (POST) aur landing page par wapas."""
    if request.user.is_authenticated:
        logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('core:landing')


class PasswordResetRequestView(auth_views.PasswordResetView):
    form_class = NormalizedPasswordResetForm
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.txt'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = StrongSetPasswordForm
    template_name = 'accounts/password_reset_confirm.html'


class AccountPasswordChangeView(auth_views.PasswordChangeView):
    form_class = StrongPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')
