"""i18n helpers for templates.

- ``{% t "key" %}``  — translate a static string for the current language.
- ``{{ value|tr }}`` — translate a dynamic value (e.g. a job title).
"""
from django import template
from django.utils.safestring import mark_safe

from core.i18n import DEFAULT_LANGUAGE, translate, translate_current

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, key, **kwargs):
    lang = context.get('CURRENT_LANG', DEFAULT_LANGUAGE)
    text = translate(key, lang)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


@register.filter(name='tr')
def tr(value):
    """Translate a runtime value using the request's current language."""
    if value is None:
        return ''
    return translate_current(str(value))


@register.simple_tag
def tl(value):
    """Translate a runtime value (safe tag variant of ``tr``)."""
    return mark_safe(translate_current(str(value)))
