import os

import dj_database_url
import django
import pytest
from django.core import management


@pytest.fixture(autouse=True, scope="session")
def _celery_eager_app():
    """
    Run celery tasks inline so dispatcher='celery' rules don't need a broker.
    Skips silently if celery isn't installed.
    """
    try:
        from celery import Celery
    except ImportError:
        yield None
        return

    app = Celery("restflow_tests")
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    # Importing the bundled task module triggers @shared_task registration.
    import restflow.caching.tasks  # noqa: F401

    app.autodiscover_tasks(packages=["restflow"], force=True)
    yield app


def pytest_collection_modifyitems(config, items):
    optional_deps = {
        "celery": ("celery", "celery not installed"),
        "redis": ("django_redis", "django-redis not installed"),
    }
    for marker_name, (module_name, reason) in optional_deps.items():
        try:
            __import__(module_name)
        except ImportError:
            skip = pytest.mark.skip(reason=reason)
            for item in items:
                if marker_name in item.keywords:
                    item.add_marker(skip)


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
    if (
        databases["default"]["ENGINE"] == "django.db.backends.sqlite3"
        and databases["default"]["NAME"] == ":memory:"
    ):
        databases["default"]["NAME"] = (
            "file:memorydb_default?mode=memory&cache=shared"
        )
        databases["default"].setdefault("OPTIONS", {})
        databases["default"]["TEST"] = {
            "NAME": "file:memorydb_default?mode=memory&cache=shared",
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
                    "debug": True,
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
            "restflow.authentication",
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

    if config.getoption("--staticfiles"):
        import restflow

        settings.STATIC_ROOT = os.path.join(os.path.dirname(restflow.__file__), "static-root") #noqa
        backend = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        settings.STORAGES["staticfiles"]["BACKEND"] = backend

    django.setup()
    management.call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
    if config.getoption("--staticfiles"):
        management.call_command("collectstatic", verbosity=0, interactive=False)
