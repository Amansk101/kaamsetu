from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .i18n import DEFAULT_LANGUAGE, LANGUAGE_CODES

SESSION_KEY = 'ks_language'


def landing(request):
    """Landing page — the public marketing home."""
    return render(request, 'core/landing.html')


def select_role(request):
    """Worker ya employer — account type chunne wala page.

    ``?role=worker|employer`` aa jaaye to us card ko highlight karo, taaki
    user ko landing/navbar se aaya hua intent saaf dikhe.
    """
    preselect = request.GET.get('role')
    if preselect not in ('worker', 'employer'):
        preselect = None
    return render(request, 'core/select_role.html', {'preselect': preselect})


def go(request):
    """Login ke baad role ke hisaab se sahi dashboard par bhejo."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    if request.user.is_worker:
        return redirect('workers:dashboard')
    if request.user.is_employer:
        return redirect('employers:dashboard')
    return redirect('core:landing')


def how_it_works(request):
    return render(request, 'core/how_it_works.html')


def about(request):
    return render(request, 'core/about.html')


def privacy(request):
    return render(request, 'core/privacy.html')


def terms(request):
    return render(request, 'core/terms.html')


def not_found(request, exception=None):
    """Custom 404 — reference app's ``NotFound`` page."""
    return render(request, '404.html', status=404)


def bad_request(request, exception=None):
    """Custom 400 — malformed request."""
    return render(request, '400.html', status=400)


def permission_denied(request, exception=None):
    """Custom 403 — access denied."""
    return render(request, '403.html', status=403)


def server_error(request):
    """Custom 500 — unexpected server failure (never leaks the traceback)."""
    return render(request, '500.html', status=500)


def set_language(request):
    """Language switcher — choice session + cookie me save karo, wapas bhejo."""
    lang = request.POST.get('language') or request.GET.get('language') or DEFAULT_LANGUAGE
    if lang in LANGUAGE_CODES:
        request.session[SESSION_KEY] = lang
        request.KS_LANG = lang

    nxt = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    if not nxt or not url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        nxt = reverse('core:landing')
    return HttpResponseRedirect(nxt)
