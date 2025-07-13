from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    verified = models.BooleanField(default=False, null=False)
    is_admin = models.BooleanField(default=False, null=False)
    banned = models.BooleanField(default=False, null=False)

    class Meta:
        indexes = [
            models.Index(fields=["banned"], name="idx_user_banned"),
            models.Index(fields=["is_admin"], name="idx_user_is_admin"),
        ]

    def __str__(self) -> str:
        return self.username


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="user_id")
    ip_address = models.CharField(max_length=45, null=False)
    session_token = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    expires_at = models.DateTimeField(null=False)
    active = models.BooleanField(default=True, null=False)

    class Meta:
        db_table = "user_session"
        managed = True
        indexes = [
            models.Index(fields=["user", "active"], name="idx_user_active"),
            models.Index(fields=["ip_address", "active"], name="idx_ip_active"),
            models.Index(
                fields=["user", "ip_address", "active"], name="idx_user_ip_active"
            ),
        ]

    def __str__(self) -> str:
        return f"UserSession user_id={self.user_id} ip={self.ip_address}"
