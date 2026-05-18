from restflow.serializers import Field, Serializer


class TokenObtainSerializer(Serializer):
    """Validates a username and password pair for a token obtain request."""

    username: str
    password: str = Field(write_only=True)


class TokenRefreshSerializer(Serializer):
    """Validates a refresh token string."""

    refresh: str


class TokenBlacklistSerializer(Serializer):
    """Validates the refresh token to blacklist."""

    refresh: str
