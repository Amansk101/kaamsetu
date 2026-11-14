from config.settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / '.tmp_kaamsetu_ux' / 'audit.sqlite3'}}
MEDIA_ROOT = BASE_DIR / '.tmp_kaamsetu_ux' / 'media'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
