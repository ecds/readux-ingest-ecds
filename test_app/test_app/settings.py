"""
Django settings for test_app project.

Generated by 'django-admin startproject' using Django 3.2.21.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

from pathlib import Path
import os
import environ

os.environ["DJANGO_ENV"] = "test"

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = environ.Path(__file__) - 2
FIXTURE_DIR = ROOT_DIR.path("fixtures")

IIIF_MANIFEST_MODEL = "iiif.Manifest"
IIIF_IMAGE_SERVER_MODEL = "iiif.ImageServer"
IIIF_RELATED_LINK_MODEL = "iiif.RelatedLink"
IIIF_CANVAS_MODEL = "iiif.Canvas"
IIIF_COLLECTION_MODEL = "iiif.Collection"
IIIF_OCR_MODEL = "iiif.OCR"
INGEST_TMP_DIR = os.path.join("tmp")
INGEST_PROCESSING_DIR = os.path.join("tmp", "processing")
INGEST_OCR_DIR = os.path.join("tmp", "ocr")
INGEST_TRIGGER_BUCKET = "readux-ingest-ecds-test"
INGEST_BUCKET = "ingest-test"
INGEST_STAGING_PREFIX = "incoming"
INGEST_OCR_PREFIX = "ocr"
READUX_EMAIL_SENDER = "donotreplay@readux.io"
HOSTNAME = "readux.io"

# Readux settings
DATASTREAM_PREFIX = "http://repo.library.emory.edu/fedora/objects/"
DATASTREAM_SUFFIX = "/datastreams/position/content"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-^xwy*n+ucn4vzl7a5rnzl)2st_&fhktx5pmgcgqgx3u-2r66@*"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

AUTH_USER_MODEL = "iiif.User"

CHUNK_SIZE = 2

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django_celery_results",
    "iiif.apps.IiifConfig",
    "readux_ingest_ecds",
    "test_app",
]

LOCAL_APPS = []

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "test_app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "test_app.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "readux_ingest_ecds": {
            "handlers": ["console"],
            "level": "DEBUG",
        }
    },
}
