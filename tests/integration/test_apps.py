from unittest.mock import patch


def test_caching_config_ready_calls_cache_register_auto_discover():
    from restflow.caching.apps import CachingConfig

    config = CachingConfig.__new__(CachingConfig)

    with patch(
        "restflow.caching.registry.CacheRegister.auto_discover"
    ) as mock_auto_discover:
        config.ready()

    mock_auto_discover.assert_called_once_with()


def test_caching_config_declares_standalone_app_metadata():
    from restflow.caching.apps import CachingConfig

    assert CachingConfig.name == "restflow.caching"
    assert CachingConfig.label == "restflow_caching"
    assert CachingConfig.default is True


def test_caching_config_ready_processes_pending_rules_without_top_level_app():
    from django.contrib.auth import get_user_model

    from restflow.caching import (
        ArgsKeyField,
        CacheRegister,
        ConstantKeyField,
        InvalidationRule,
        cache_result,
    )
    from restflow.caching.apps import CachingConfig

    CacheRegister.clear()
    User = get_user_model()

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User, field_mapping={"user_id": "id"}, rewarm=True
            )
        ],
    )
    def fn(user_id: int):  # pragma: no cover - registration-only test
        return user_id

    assert CacheRegister.is_discovered is False
    assert CacheRegister.pending_count >= 1

    try:
        config = CachingConfig.__new__(CachingConfig)
        config.ready()

        assert CacheRegister.is_discovered is True
        assert CacheRegister.pending_count == 0
        assert User in CacheRegister._connected_models
    finally:
        CacheRegister.clear()


def test_auto_discover_registers_each_rule_once():
    from django.contrib.auth import get_user_model

    from restflow.caching import (
        ArgsKeyField,
        CacheRegister,
        InvalidationRule,
        cache_result,
    )

    CacheRegister.clear()
    User = get_user_model()

    def declare_during_import():
        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def fn(user_id: int):  # pragma: no cover - registration-only test
            return user_id

    try:
        with patch.object(
            CacheRegister, "_import_cache_modules", side_effect=declare_during_import
        ):
            CacheRegister.auto_discover()

        assert len(CacheRegister._model_rule_ids[User]) == 1
        signatures = [
            (id(rule["func"]), id(rule["invalidation_rule"]))
            for rule in CacheRegister._rules.values()
        ]
        assert len(signatures) == len(set(signatures))
    finally:
        CacheRegister.clear()


def test_rules_added_after_discovery_are_not_queued_again():
    from django.contrib.auth import get_user_model

    from restflow.caching import (
        ArgsKeyField,
        CacheRegister,
        InvalidationRule,
        cache_result,
    )

    CacheRegister.clear()
    User = get_user_model()

    try:
        with patch.object(CacheRegister, "_import_cache_modules"):
            CacheRegister.auto_discover()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def fn(user_id: int):  # pragma: no cover - registration-only test
            return user_id

        assert CacheRegister.pending_count == 0
        assert len(CacheRegister._model_rule_ids[User]) == 1
    finally:
        CacheRegister.clear()
