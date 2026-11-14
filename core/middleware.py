"""Request ke saath current language resolve karne wala middleware."""
from .i18n import DEFAULT_LANGUAGE, LANGUAGE_CODES, set_current_language

SESSION_KEY = 'ks_language'


class LanguageMiddleware:
    """Session/cookie se language padho, default English."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = (
            request.session.get(SESSION_KEY)
            or request.COOKIES.get(SESSION_KEY)
            or DEFAULT_LANGUAGE
        )
        if lang not in LANGUAGE_CODES:
            lang = DEFAULT_LANGUAGE
        request.KS_LANG = lang
        set_current_language(lang)

        response = self.get_response(request)

        chosen = request.session.get(SESSION_KEY)
        if chosen:
            response.set_cookie(
                SESSION_KEY, chosen, max_age=365 * 24 * 3600, samesite='Lax'
            )
        return response
