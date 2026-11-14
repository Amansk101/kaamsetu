from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def role_required(role):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            if request.user.role != role:
                messages.error(request, 'This page is not available for your account type.')
                return redirect('core:home')
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


worker_required = role_required('worker')
employer_required = role_required('employer')
