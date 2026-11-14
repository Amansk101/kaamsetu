"""Templates me language switcher + current language available karana."""
from .i18n import DEFAULT_LANGUAGE, LANGUAGES, language_direction


def kaamsetu(request):
    lang = getattr(request, 'KS_LANG', DEFAULT_LANGUAGE)
    return {
        'LANGUAGES': LANGUAGES,
        'CURRENT_LANG': lang,
        'CURRENT_LANG_DIR': language_direction(lang),
    }
