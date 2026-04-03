from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """
    Django app config for the BlacklistedToken model.
    Required in INSTALLED_APPS only when using ModelBlacklistBackend.
    """

    name = "restflow.authentication"
    label = "restflow_authentication"
    verbose_name = "Restflow Authentication"
