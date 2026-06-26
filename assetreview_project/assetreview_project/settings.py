"""
Django Settings for assetreview_project
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-assetreview-demo-secret-key-2024'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'assetreview',
]

# ── Our custom middleware (upload size limiter) goes FIRST ──
MIDDLEWARE = [
    'assetreview.middleware.UploadSizeLimitMiddleware',   # Our custom one
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',          # CSRF protection
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'assetreview_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'assetreview_project.wsgi.application'

# Static files (CSS, JS)
STATIC_URL = '/static/'

# Media files (uploaded CSVs)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Temp folder for JSON preview files (not database!)
TEMP_PREVIEW_DIR = BASE_DIR / 'temp_previews'

# Max upload size = 1 MB (used by our middleware)
MAX_UPLOAD_SIZE_BYTES = 1 * 1024 * 1024   # 1 MB

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
