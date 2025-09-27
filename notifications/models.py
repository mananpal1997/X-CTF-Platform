from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        "user_auth.User", on_delete=models.CASCADE, db_column="user_id"
    )
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        managed = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Notification {self.id} - {self.message}"
