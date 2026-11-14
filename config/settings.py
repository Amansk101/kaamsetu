"""
Django settings for KaamSetu.

Agentic AI job-matching platform for rural youth and small employers.
V1 keeps the AI layer pluggable (heuristic agents) on top of a solid data model.
"""

from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Chhota ``.env`` loader — koi extra dependency nahi chahiye.

    ``BASE_DIR/.env`` me ``KEY=value`` lines likh kar SMTP credentials set kar
    sakte hain. Already-set environment variables ko override nahi karta.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(BASE_DIR / '.env')

def _env_bool(name, default):
    """Environment se boolean padho (``true/1/yes`` = True)."""
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


# --- Security & environment ------------------------------------------------
# Ye values environment (ya project root ki ``.env``) se aati hain. Defaults
# development ke liye safe hain — bina kuch set kiye app chalta rehta hai.
# Production me hamesha KAAMSETU_SECRET_KEY set karo aur KAAMSETU_DEBUG=false.

DEBUG = _env_bool('KAAMSETU_DEBUG', True)

_DEV_FALLBACK_KEY = 'django-insecure-usz7ewudupad^l+9l$-qxr$t^=8l&izf+yfz9#$pq3tow=1@v)'

SECRET_KEY = os.environ.get('KAAMSETU_SECRET_KEY') or (_DEV_FALLBACK_KEY if DEBUG else '')

if not SECRET_KEY:
    raise ImproperlyConfigured(
        'KAAMSETU_SECRET_KEY set karo jab KAAMSETU_DEBUG=false ho.'
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'KAAMSETU_ALLOWED_HOSTS', '*' if DEBUG else ''
    ).split(',')
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # KaamSetu apps
    'core',
    'accounts',
    'workers',
    'employers',
    'jobs',
    'hiring',
    'agents',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core.middleware.LanguageMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.kaamsetu',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# V1 dev ke liye SQLite. Production me Postgres (DATABASE_URL) par switch karein.

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Custom user model (worker / employer roles)

AUTH_USER_MODEL = 'accounts.User'

# Login email + password se hota hai (username ki jagah).
AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    # Enterprise-grade rules: uppercase + lowercase + number + special character.
    {'NAME': 'accounts.validators.StrongPasswordValidator'},
]


# Internationalization

LANGUAGE_CODE = 'en-in'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# Static & media

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Optional S3-compatible media storage (for example Cloudflare R2). Configure
# all KAAMSETU_R2_* variables in the host dashboard; never commit credentials.
R2_BUCKET = os.environ.get('KAAMSETU_R2_BUCKET', '').strip()
if R2_BUCKET:
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
    }
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET
    AWS_S3_ENDPOINT_URL = os.environ.get('KAAMSETU_R2_ENDPOINT', '').strip()
    AWS_S3_REGION_NAME = 'auto'
    AWS_ACCESS_KEY_ID = os.environ.get('KAAMSETU_R2_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('KAAMSETU_R2_SECRET_ACCESS_KEY', '')
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None


# Auth redirects

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:go'
LOGOUT_REDIRECT_URL = 'core:home'


# Email
#
# Asli mail bhejne ke liye project root me ek ``.env`` file banao (ya environment
# variables set karo) — auto-load hoti hai:
#   KAAMSETU_EMAIL_HOST=smtp.gmail.com
#   KAAMSETU_EMAIL_PORT=587
#   KAAMSETU_EMAIL_HOST_USER=you@gmail.com
#   KAAMSETU_EMAIL_HOST_PASSWORD=app-password
#   KAAMSETU_DEFAULT_FROM_EMAIL=KaamSetu <you@gmail.com>
#
# Gmail ke liye: 2-Step Verification on karo -> "App password" banao -> wahi
# password yahan daalo (normal account password kaam nahi karega).
#
# Jab tak SMTP set nahi hai, mail asli me likhi jaati hai aur
# BASE_DIR/'sent_emails' folder me save hoti hai (browser me khol kar dekh sakte hain),
# taaki "email chala gaya" ka pura proof rahe — console me khone ke bajaye.

EMAIL_HOST = os.environ.get('KAAMSETU_EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('KAAMSETU_EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('KAAMSETU_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('KAAMSETU_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('KAAMSETU_EMAIL_USE_TLS', 'true').lower() != 'false'
# Sender address. Agar alag se set na kiya ho to SMTP account hi use hota hai,
# kyunki Gmail/Outlook kisi doosre "From" ko reject kar dete hain.
DEFAULT_FROM_EMAIL = (
    os.environ.get('KAAMSETU_DEFAULT_FROM_EMAIL', '')
    or EMAIL_HOST_USER
    or 'KaamSetu <no-reply@kaamsetu.local>'
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    # Dev fallback: har bheji gayi mail BASE_DIR/'sent_emails' me file ke roop
    # me likhi jaati hai, taaki bhejna asli me hota dikhe (console me khone ke
    # bajaye). SMTP set karte hi automatically asli delivery par switch ho jaata hai.
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'


# KaamSetu agent config (V2 me real providers plug honge)

KAAMSETU = {
    # Jab real LLM keys available ho, 'heuristic' -> 'llm' karein.
    'AGENT_MODE': 'heuristic',
    # Vision AI — uploaded video ko sach me "dekh" kar skill detect karta hai.
    # Key na ho to app chup-chaap filename/heuristic fallback use karta hai.
    # Free key: https://aistudio.google.com/apikey
    # KAAMSETU_GEMINI_API_KEY preferred; common alternates bhi chalti hain.
    'GEMINI_API_KEY': (
        os.environ.get('KAAMSETU_GEMINI_API_KEY')
        or os.environ.get('GEMINI_API_KEY')
        or os.environ.get('GOOGLE_API_KEY')
        or ''
    ),
    'GEMINI_MODEL': os.environ.get('KAAMSETU_GEMINI_MODEL', 'gemini-2.5-flash'),
    # Switcher me jo languages dikhengi wo core.i18n.LANGUAGES se aati hain —
    # poora list ek hi jagah (core/i18n.py) rehta hai.
    'MATCH_MAX_DISTANCE_KM': 25,
    'MATCH_WEIGHTS': {
        'skill': 0.40,
        'distance': 0.25,
        'wage': 0.20,
        'trust': 0.15,
    },
}


# --- Production security ---------------------------------------------------
# Sirf tab lagte hain jab DEBUG=False ho — local development as-is chalta hai.

if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('KAAMSETU_SECURE_SSL', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get('KAAMSETU_CSRF_TRUSTED_ORIGINS', '').split(',')
        if origin.strip()
    ]

# Trust the proxy's forwarded scheme so HTTPS detection works behind Nginx etc.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# --- Logging ---------------------------------------------------------------
# Console + rotating file. API keys / passwords kabhi log nahi hote kyunki
# sirf error messages aur agent summaries log ki jaati hain.

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'kaamsetu.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 3,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'agents': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
