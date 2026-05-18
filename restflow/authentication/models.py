from datetime import datetime, timezone

from django.db import models


class BlacklistedToken(models.Model):
    """
    A revoked JWT keyed by its JTI claim.
    Used by ModelBlacklistBackend; rows persist until cleanup_expired is called.
    """

    jti = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "restflow_authentication"
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"BlacklistedToken(jti={self.jti}, expires_at={self.expires_at})"

    @classmethod
    def cleanup_expired(cls) -> int:
        """Deletes all rows whose expires_at is in the past and returns the deleted count."""
        deleted, _ = cls.objects.filter(
            expires_at__lt=datetime.now(tz=timezone.utc)
        ).delete()
        return deleted

    @classmethod
    async def acleanup_expired(cls) -> int:
        """Async variant of cleanup_expired."""
        deleted, _ = await cls.objects.filter(
            expires_at__lt=datetime.now(tz=timezone.utc)
        ).adelete()
        return deleted
