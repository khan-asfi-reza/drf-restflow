import asyncio
import sys
import types
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from restflow.authentication import (
    AccessToken,
    JWTAuthentication,
    RefreshToken,
)
from restflow.authentication.jwt import (
    CacheBlacklistBackend,
    get_user_authentication_rule,
    resolve_token_blacklist_backend,
)
from restflow.caching.registry import CacheRegistry


def run_coro(coro):
    return asyncio.run(coro)


def custom_user_rule(user):
    return user is not None and user.is_active


def jwt_settings(**overrides):
    base = {
        "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "BLACKLIST_ENABLED": False,
        "BLACKLIST_ALLOW_LOCMEM": True,
    }
    base.update(overrides)
    return {"RESTFLOW_SETTINGS": {"JWT": base}}


class TestUserAuthRuleResolution:
    def test_dotted_path_user_authentication_rule_imported(self):
        with override_settings(
            **jwt_settings(
                USER_AUTHENTICATION_RULE=(
                    "tests.integration.api.test_coverage_fillins.custom_user_rule"
                ),
            )
        ):
            rule = get_user_authentication_rule()
            assert rule is custom_user_rule

    def test_callable_user_authentication_rule_returned_unchanged(self):
        with override_settings(
            **jwt_settings(USER_AUTHENTICATION_RULE=custom_user_rule),
        ):
            rule = get_user_authentication_rule()
            assert rule is custom_user_rule


class TestBlacklistBackendDottedPathResolution:
    def test_dotted_path_blacklist_backend_imported(self):
        backend = resolve_token_blacklist_backend(
            "restflow.authentication.jwt.CacheBlacklistBackend"
        )
        assert isinstance(backend, CacheBlacklistBackend)

    def test_unknown_spec_type_falls_back_to_cache_backend(self):
        backend = resolve_token_blacklist_backend(object())
        assert isinstance(backend, CacheBlacklistBackend)

    def test_int_spec_falls_back_to_cache_backend(self):
        backend = resolve_token_blacklist_backend(42)
        assert isinstance(backend, CacheBlacklistBackend)


@pytest.mark.django_db(transaction=True)
class TestJWTRevokeTokenInRotateAndAuthenticate:
    def test_refresh_rotate_carries_revoke_claim_in_minted_access(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="rev1", password="orig", is_active=True
        )
        with override_settings(**jwt_settings(CHECK_REVOKE_TOKEN=True)):
            refresh = RefreshToken.for_user(user)
            assert "hash_password" in refresh.payload
            access = refresh.access_token
            assert "hash_password" in access.payload

    def test_password_change_rejects_old_token(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="rev2", password="orig", is_active=True
        )
        with override_settings(**jwt_settings(CHECK_REVOKE_TOKEN=True)):
            token = AccessToken.for_user(user)
            user.set_password("changed")
            user.save()

            factory = RequestFactory()
            request = Request(
                factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}")
            )
            with pytest.raises(AuthenticationFailed, match="password"):
                run_coro(JWTAuthentication().aauthenticate(request))


@pytest.mark.django_db(transaction=True)
class TestSimpleJWTPasswordChangedRejection:
    def test_simplejwt_password_change_rejects_old_token(self):
        pytest.importorskip("rest_framework_simplejwt")
        import importlib

        from restflow.authentication import simplejwt as simplejwt_mod

        User = get_user_model()
        user = User.objects.create_user(
            username="sj1", password="orig", is_active=True
        )
        sj_settings = {
            "SIMPLE_JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
                "CHECK_REVOKE_TOKEN": True,
                "REVOKE_TOKEN_CLAIM": "hash_password",
            },
        }
        with override_settings(**sj_settings):
            importlib.reload(simplejwt_mod)
            stale_token = {
                "user_id": user.pk,
                "hash_password": "stale-hash-not-current",
            }
            with pytest.raises(AuthenticationFailed, match="password"):
                run_coro(
                    simplejwt_mod.SimpleJWTAuthentication().aget_user(stale_token)
                )

        importlib.reload(simplejwt_mod)


class TestCacheRegisterImportFailure:
    def test_auto_discover_swallows_import_error_in_app_submodule(
        self, tmp_path
    ):
        package = types.ModuleType("optional_dep_test_pkg")
        package.__path__ = [str(tmp_path)]
        sys.modules["optional_dep_test_pkg"] = package

        broken = tmp_path / "broken.py"
        broken.write_text("import nonexistent_optional_dep_xyz\n")

        from django.apps import AppConfig, apps

        class StubConfig(AppConfig):
            name = "optional_dep_test_pkg"
            label = "optional_dep_test_pkg"
            verbose_name = "Optional Dep Test"

        config = StubConfig("optional_dep_test_pkg", package)
        config.module = package
        config.apps = apps
        config.models = {}
        apps.app_configs[config.label] = config
        apps.ready = True
        apps.clear_cache()

        try:
            registry = CacheRegistry()
            registry._discovered = False
            registry._import_cache_modules()
        finally:
            apps.app_configs.pop(config.label, None)
            apps.clear_cache()
            sys.modules.pop("optional_dep_test_pkg", None)
            sys.modules.pop("optional_dep_test_pkg.broken", None)


class TestMultipleChoiceFieldFlattenNonString:
    def test_flatten_keeps_non_string_items_in_set(self):
        from rest_framework.exceptions import ValidationError

        from restflow.filters.fields import MultipleChoiceField

        class StringField(MultipleChoiceField):
            lookup_categories = []

        field = StringField(choices=[("a", "A"), ("b", "B")])
        with pytest.raises(ValidationError):
            field.to_internal_value([1, "a"])


@pytest.mark.django_db
class TestSyncUpdateMixinPrefetchedCacheReset:
    def test_update_resets_prefetched_objects_cache(self):
        from rest_framework import serializers as drf_serializers

        from restflow.views import APIView
        from restflow.views.mixins import UpdateModelMixin
        from tests.models import SampleModel

        class Serializer(drf_serializers.ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["id", "integer_field"]

        instance = SampleModel.objects.create(integer_field=1)
        instance._prefetched_objects_cache = {"some": "thing"}

        class View(UpdateModelMixin, APIView):
            serializer_class = Serializer
            permission_classes = []

            def get_object(self):
                obj = SampleModel.objects.get(pk=instance.pk)
                obj._prefetched_objects_cache = {"some": "thing"}
                return obj

            def put(self, request):
                return self.update(request)

        import json
        factory = RequestFactory()
        request = factory.put(
            "/",
            data=json.dumps({"integer_field": 2}),
            content_type="application/json",
        )
        response = View.as_view()(request)
        assert response.status_code == 200
