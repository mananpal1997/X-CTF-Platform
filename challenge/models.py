from django.db import models


class Challenge(models.Model):
    name = models.CharField(max_length=150, unique=True, null=False)
    points = models.IntegerField(null=False)
    flag = models.CharField(max_length=500, null=False)
    active = models.BooleanField(null=False, default=True, db_index=True)
    category = models.CharField(max_length=150, null=False)
    image_tag = models.CharField(max_length=500, null=True, blank=True)
    static = models.BooleanField(null=False, default=False)
    metadata_filepath = models.CharField(max_length=256, null=True, blank=True)
    tcp_ports = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "challenge"
        managed = True
        indexes = [
            models.Index(fields=["active"], name="idx_challenge_active"),
        ]

    def __str__(self) -> str:
        return f"<Challenge {self.category}::{self.name}>"


class Submission(models.Model):
    user = models.ForeignKey(
        "user_auth.User",
        on_delete=models.CASCADE,
        db_column="user_id",
        null=False,
        db_index=True,
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        db_column="challenge_id",
        null=False,
        db_index=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    correct = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "submission"
        managed = True
        indexes = [
            models.Index(
                fields=["user", "challenge", "correct"],
                name="idx_sub_user_chal_correct",
            ),
            models.Index(fields=["challenge", "correct"], name="idx_sub_chal_correct"),
        ]

    def __str__(self) -> str:
        return f"<Submission user_id={self.user_id} challenge_id={self.challenge_id} correct={self.correct}>"


class Sandbox(models.Model):
    container_id = models.CharField(max_length=256, null=False)
    container_port = models.IntegerField(null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    destroyed_at = models.DateTimeField(null=True, blank=True)
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        db_column="challenge_id",
        null=False,
        db_index=True,
    )
    user = models.ForeignKey(
        "user_auth.User",
        on_delete=models.CASCADE,
        db_column="user_id",
        null=True,
        blank=True,
        db_index=True,
    )
    active = models.BooleanField(null=False, default=True, db_index=True)
    port_mappings = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "sandbox"
        managed = True
        indexes = [
            models.Index(
                fields=["challenge", "active"], name="idx_sandbox_chal_active"
            ),
            models.Index(
                fields=["challenge", "user", "active"],
                name="idx_sandbox_chal_user_active",
            ),
        ]

    def __str__(self) -> str:
        return f"<Sandbox id={self.id} challenge_id={self.challenge_id} user_id={self.user_id}>"
