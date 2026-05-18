from django.apps import AppConfig


class CachingConfig(AppConfig):
    """Django app config for the restflow caching subsystem."""

    name = "restflow.caching"
    label = "restflow_caching"
    verbose_name = "Restflow Caching"
    default = True
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Trigger cache rule discovery once Django finishes loading apps."""
        from restflow.caching.registry import CacheRegister  # noqa: PLC0415
        CacheRegister.auto_discover()
