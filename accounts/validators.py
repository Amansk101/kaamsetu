"""KaamSetu reusable field validators.

Ye rules signup, profile aur kisi bhi jagah ek hi tarah apply hote hain —
frontend JS inhi rules ko mirror karta hai, par final authority hamesha
backend (server-side) hi rehti hai.
"""
import re
import unicodedata

from django.core.exceptions import ValidationError

# Indian mobile: bilkul 10 digit aur pehla digit 6/7/8/9.
MOBILE_RE = re.compile(r'^[6-9]\d{9}$')


def validate_name(value):
    """Accept names in Indian scripts and common Latin punctuation."""
    name = value or ''
    if not name:
        raise ValidationError('Please enter your name.')
    if name != name.strip():
        raise ValidationError('Name cannot start or end with a space.')
    allowed_separators = {' ', '-', "'", '\u2019', '.'}
    has_letter = False
    after_separator = False
    valid = True
    for character in name:
        category = unicodedata.category(character)
        if category.startswith('L'):
            has_letter = True
            after_separator = False
        elif category.startswith('M') and has_letter and not after_separator:
            continue
        elif character in allowed_separators and has_letter and not after_separator:
            after_separator = True
        else:
            valid = False
            break
    if not valid or not has_letter or after_separator:
        raise ValidationError(
            'Use letters, single spaces, apostrophes, hyphens or periods in your name.'
        )


def validate_indian_mobile(value):
    """Indian mobile number — exactly 10 digits, 6/7/8/9 se shuru."""
    # Whitespace is invalid input; never normalize it into a valid number.
    mobile = value or ''
    if not mobile:
        raise ValidationError('Please enter your mobile number.')
    if not MOBILE_RE.match(mobile):
        raise ValidationError(
            'Enter a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9.'
        )


def validate_indian_pincode(value):
    if value and not re.fullmatch(r'[1-9]\d{5}', value):
        raise ValidationError('Enter a valid 6-digit Indian PIN code.')


def validate_not_future_date(value):
    from django.utils import timezone

    if value and value > timezone.localdate():
        raise ValidationError('Date of birth cannot be in the future.')


class StrongPasswordValidator:
    """Password policy: 8+ chars with upper, lower, number aur special character.

    Login par ye lagu nahi hota (purane valid accounts block nahi hone chahiye) —
    sirf naya password set/change karne par.
    """

    def validate(self, password, user=None):
        # Length check Django ke MinimumLengthValidator (min_length=8) se aata hai,
        # isliye yahan sirf character-class rules dikhate hain (duplicate message se bachne ke liye).
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append('Include at least one uppercase letter (A-Z).')
        if not re.search(r'[a-z]', password):
            errors.append('Include at least one lowercase letter (a-z).')
        if not re.search(r'\d', password):
            errors.append('Include at least one number (0-9).')
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append('Include at least one special character (e.g. @ # $ %).')
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            'Use at least 8 characters with one uppercase letter, one lowercase letter, '
            'one number and one special character.'
        )
