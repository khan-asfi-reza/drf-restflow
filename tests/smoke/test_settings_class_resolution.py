import subprocess
import sys
import textwrap

BOOT_SCRIPT = """
import sys

sys.path.insert(0, {tmp!r})

import django
from django.conf import settings

settings.configure(
    DEBUG=True,
    DATABASES={{}},
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "rest_framework",
    ],
    REST_FRAMEWORK={{
        "DEFAULT_AUTHENTICATION_CLASSES": ["app_defaults.Auth"],
        "DEFAULT_PERMISSION_CLASSES": ["app_defaults.Permission"],
        "DEFAULT_THROTTLE_CLASSES": ["app_defaults.Throttle"],
        "DEFAULT_PAGINATION_CLASS": "app_defaults.Pagination",
        "EXCEPTION_HANDLER": "restflow.exceptions.exception_handler",
    }},
    USE_TZ=True,
)
django.setup()

import rest_framework.generics  # noqa: F401

print("BOOT OK")
"""

APP_DEFAULTS = """
from restflow.authentication import BaseAuthentication
from restflow.pagination import PageNumberPagination
from restflow.permissions import BasePermission
from restflow.throttling import SimpleRateThrottle


class Auth(BaseAuthentication):
    def authenticate(self, request):
        return None


class Permission(BasePermission):
    def has_permission(self, request, view):
        return True


class Throttle(SimpleRateThrottle):
    scope = "smoke"

    def get_cache_key(self, request, view):
        return None


class Pagination(PageNumberPagination):
    page_size = 10
"""


def test_restflow_classes_resolve_in_drf_settings(tmp_path):
    (tmp_path / "app_defaults.py").write_text(textwrap.dedent(APP_DEFAULTS))
    boot = tmp_path / "boot.py"
    boot.write_text(BOOT_SCRIPT.format(tmp=str(tmp_path)))

    result = subprocess.run(
        [sys.executable, str(boot)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "BOOT OK" in result.stdout


def test_restflow_base_modules_import_without_rest_framework_views():
    script = textwrap.dedent(
        """
        import sys

        from django.conf import settings

        settings.configure(DATABASES={}, INSTALLED_APPS=[], USE_TZ=True)

        import restflow.exceptions
        import restflow.pagination
        import restflow.permissions
        import restflow.throttling

        assert "rest_framework.views" not in sys.modules, sorted(
            m for m in sys.modules if m.startswith("rest_framework")
        )
        print("CLEAN")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout
