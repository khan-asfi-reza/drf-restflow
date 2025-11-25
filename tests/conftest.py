import os

import dj_database_url
import django
from django.core import management


def pytest_addoption(parser):
    parser.addoption(
        "--staticfiles",
        action="store_true",
        default=False,
        help="Run tests with static files collection, using manifest "
        "staticfiles storage. Used for testing the distribution.",
    )


def pytest_configure(config):
    from django.conf import settings # noqa

    databases = {
        "default": dj_database_url.config(
            env="POSTGRES_DB_URL",
            default="sqlite://:memory:",
            conn_max_age=600
        )
    }

    settings.configure(
        DEBUG_PROPAGATE_EXCEPTIONS=True,
        DATABASES=databases,
        SITE_ID=1,
        SECRET_KEY="not very secret in tests",
        USE_I18N=True,
        STATIC_URL="/static/",
        ROOT_URLCONF="tests.urls",
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "APP_DIRS": True,
                "OPTIONS": {
                    "debug": True,  # We want template errors to raise
                },
            },
        ],
        MIDDLEWARE=(
            "django.middleware.common.CommonMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ),
        INSTALLED_APPS=(
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.sites",
            "django.contrib.staticfiles",
            "rest_framework",
            "rest_framework.authtoken",
            "tests",
        ),
        PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",),
    )

    # guardian is optional
    try:
        import guardian  # NOQA
    except ImportError:
        pass
    else:
        settings.ANONYMOUS_USER_ID = -1
        settings.AUTHENTICATION_BACKENDS = (
            "django.contrib.auth.backends.ModelBackend",
            "guardian.backends.ObjectPermissionBackend",
        )
        settings.INSTALLED_APPS += ("guardian",)

    # Manifest storage will raise an exception if static files are not present (ie, a packaging failure).
    if config.getoption("--staticfiles"):
        import restflow

        settings.STATIC_ROOT = os.path.join(os.path.dirname(restflow.__file__), "static-root") #noqa
        backend = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        settings.STORAGES["staticfiles"]["BACKEND"] = backend

    django.setup()
    # Create test database tables
    management.call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
    if config.getoption("--staticfiles"):
        management.call_command("collectstatic", verbosity=0, interactive=False)
