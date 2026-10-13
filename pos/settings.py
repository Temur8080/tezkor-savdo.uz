from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

load_dotenv(os.path.join(BASE_DIR, '.env'))

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,0.0.0.0,189.74.100.71,'
        'tezkor-savdo.uz,www.tezkor-savdo.uz,'
        'galosgadgethubpos.systems,www.galosgadgethubpos.systems,'
        '.azurewebsites.net,'
        'galos-gadget-hub-pos-app-hcgdfqfeduephrej.japanwest-01.azurewebsites.net'
    ).split(',')
    if h.strip()
]

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'http://189.74.100.71,https://189.74.100.71,'
        'http://tezkor-savdo.uz,https://tezkor-savdo.uz,'
        'http://www.tezkor-savdo.uz,https://www.tezkor-savdo.uz,'
        'https://*.azurewebsites.net,'
        'https://galos-gadget-hub-pos-app-hcgdfqfeduephrej.japanwest-01.azurewebsites.net,'
        'https://galosgadgethubpos.systems,https://www.galosgadgethubpos.systems'
    ).split(',')
    if o.strip()
]

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-for-ci-checks')

DEBUG = os.getenv('DEBUG') == 'True'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = os.getenv('EMAIL_PORT', 2525)
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Tezkor <noreply@tezkor.local>')

COMPANY_BRAND = os.getenv('COMPANY_BRAND', 'Tezkor')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Tezkor Savdo')
COMPANY_LOGO_STATIC = 'images/tezkor-logo.jpg'

INSTALLED_APPS = [

    "admin_interface",
    "colorfield",
    'django_q',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts.apps.AccountsConfig',
    'django_filters',
    'django.contrib.humanize'
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.AuditMiddleware'
]

ROOT_URLCONF = 'pos.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.branding',
            ],
            'builtins': [
                'accounts.templatetags.money_tags',
            ],
        },
    },
]

WSGI_APPLICATION = 'pos.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'uz'

LANGUAGES = [
    ('uz', 'O‘zbek'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

Q_CLUSTER = {
    'name': 'Tezkor',
    'workers': 4,
    'recycle': 500,
    'timeout': 60,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'label': 'Fon vazifalari',
    'orm': 'default',
}

if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
