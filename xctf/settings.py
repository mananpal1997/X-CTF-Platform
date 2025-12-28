import os
import sys
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv
from urllib.parse import urlparse
from django.contrib.messages import constants as messages
import sentry_sdk

load_dotenv()

IN_TEST = (
    "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
    or os.environ.get("PYTEST_CURRENT_TEST")
)

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        enable_logs=True,
    )

DISABLE_RATE_LIMITING = os.getenv("DISABLE_RATE_LIMITING", "False").lower() == "true"

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set")

DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS is not set")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "xctf.apps.XctfConfig",
    "user_auth",
    "challenge",
    "admin_panel",
    "main",
    "notifications",
    "tasks",
    "events",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "user_auth.middleware_security.UserStatusMiddleware",
    "user_auth.middleware_security.SecurityHeadersMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "xctf.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "xctf.context_processors.github_repo",
            ],
        },
    },
]

WSGI_APPLICATION = "xctf.wsgi.application"

DB_CONN_MAX_AGE = int(os.getenv("DB_CONN_MAX_AGE", "60"))

sqlalchemy_uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
if sqlalchemy_uri:
    if sqlalchemy_uri.startswith("mysql://") or sqlalchemy_uri.startswith(
        "mysql+pymysql://"
    ):
        uri_for_parsing = sqlalchemy_uri.replace("mysql+pymysql://", "mysql://")
        parsed = urlparse(uri_for_parsing)
        mysql_options: Dict[str, int | str] = {
            "charset": "utf8mb4",
        }
        if IN_TEST:
            mysql_options.update(
                {
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                    "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                }
            )
        else:
            mysql_options.update(
                {
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            )

        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": parsed.path.lstrip("/") or "xctf",
                "USER": parsed.username or "root",
                "PASSWORD": parsed.password or "",
                "HOST": parsed.hostname or "localhost",
                "PORT": parsed.port or "3306",
                "CONN_MAX_AGE": DB_CONN_MAX_AGE,
                "OPTIONS": mysql_options,
            }
        }
    elif sqlalchemy_uri.startswith("postgres://") or sqlalchemy_uri.startswith(
        "postgresql://"
    ):
        parsed = urlparse(sqlalchemy_uri.replace("postgres://", "postgresql://"))
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": parsed.path.lstrip("/") or "xctf",
                "USER": parsed.username or "postgres",
                "PASSWORD": parsed.password or "",
                "HOST": parsed.hostname or "localhost",
                "PORT": parsed.port or "5432",
                "CONN_MAX_AGE": DB_CONN_MAX_AGE,
                "OPTIONS": {
                    "connect_timeout": 10,
                },
            }
        }
    elif sqlalchemy_uri.startswith("sqlite:///"):
        db_path = sqlalchemy_uri.replace("sqlite:///", "")
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": db_path or "db.sqlite3",
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(BASE_DIR / "db.sqlite3"),
            }
        }
else:
    db_name = os.getenv("DB_NAME")
    if db_name:
        db_engine = os.getenv("DB_ENGINE", "mysql").lower()
        if db_engine == "postgresql" or db_engine == "postgres":
            DATABASES = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": db_name,
                    "USER": os.getenv("DB_USER", "postgres"),
                    "PASSWORD": os.getenv("DB_PASSWORD", ""),
                    "HOST": os.getenv("DB_HOST", "localhost"),
                    "PORT": os.getenv("DB_PORT", "5432"),
                    "CONN_MAX_AGE": DB_CONN_MAX_AGE,
                    "OPTIONS": {
                        "connect_timeout": 10,
                    },
                }
            }
        else:
            mysql_options = {
                "charset": "utf8mb4",
            }
            if IN_TEST:
                mysql_options.update(
                    {
                        "connect_timeout": 10,
                        "read_timeout": 30,
                        "write_timeout": 30,
                        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                    }
                )
            else:
                mysql_options.update(
                    {
                        "connect_timeout": 10,
                        "read_timeout": 30,
                        "write_timeout": 30,
                    }
                )

            DATABASES = {
                "default": {
                    "ENGINE": "django.db.backends.mysql",
                    "NAME": db_name,
                    "USER": os.getenv("DB_USER", "root"),
                    "PASSWORD": os.getenv("DB_PASSWORD", ""),
                    "HOST": os.getenv("DB_HOST", "localhost"),
                    "PORT": os.getenv("DB_PORT", "3306"),
                    "CONN_MAX_AGE": DB_CONN_MAX_AGE,
                    "OPTIONS": mysql_options,
                }
            }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(BASE_DIR / "db.sqlite3"),
            }
        }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 6,
        },
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_NAME = "xctf_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
SESSION_COOKIE_AGE = 86400

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
CSRF_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"

LOGIN_URL = "/user/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

MESSAGE_TAGS = {
    messages.DEBUG: "info",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("MAIL_SERVER", "localhost")
EMAIL_PORT = int(os.getenv("MAIL_PORT", "465"))
EMAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "True").lower() == "true"
EMAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "False").lower() == "true"
EMAIL_HOST_USER = os.getenv("MAIL_USERNAME", "")
EMAIL_HOST_PASSWORD = os.getenv("MAIL_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("MAIL_DEFAULT_SENDER", "noreply@xctf.local")
SERVER_NAME = os.getenv("SERVER_NAME", "localhost:8080")

CHALLENGE_CONTAINER_VOLUME_BASE = os.getenv(
    "CHALLENGE_CONTAINER_VOLUME_BASE", "/tmp/xctf_volumes"
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URL = (
    f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    if REDIS_PASSWORD
    else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "xctf_cache",
    }
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

CHALLENGES_DIRECTORY = os.getenv("CHALLENGES_DIRECTORY", "challenges")

GITHUB_REPO = os.getenv("GITHUB_REPO", "mananpal1997/X-CTF-Platform")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(BASE_DIR, "logs", "django.log"),
            "maxBytes": 1024 * 1024 * 15,
            "backupCount": 10,
            "formatter": "verbose",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}

AUTH_USER_MODEL = "user_auth.User"
