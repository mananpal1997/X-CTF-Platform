import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver
from typing import Any

from challenge.models import Challenge, Sandbox
from user_auth.models import User
from tasks.tasks import cleanup_sandbox, send_notification

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Challenge)
def handle_challenge_deactivation(
    sender: Any, instance: Challenge, **kwargs: Any
) -> None:
    if instance.pk:
        try:
            old_instance = Challenge.objects.get(pk=instance.pk)
            if old_instance.active and not instance.active:
                challenge_name = instance.name
                logger.info(
                    f"Challenge {challenge_name} is being deactivated, cleaning up sandboxes..."
                )

                active_sandboxes = Sandbox.objects.filter(
                    challenge_id=instance.id, active=True
                )

                for sandbox in active_sandboxes:
                    cleanup_sandbox.delay(sandbox.id)

                send_notification.delay(
                    f"Challenge {challenge_name} has been deactivated.", to_all=True
                )

                logger.info(
                    f"Scheduled cleanup for {active_sandboxes.count()} sandboxes for challenge {challenge_name}"
                )
        except Challenge.DoesNotExist:
            pass


@receiver(pre_save, sender=User)
def handle_user_ban(sender: Any, instance: User, **kwargs: Any) -> None:
    if instance.pk:
        try:
            old_instance = User.objects.get(pk=instance.pk)
            if not old_instance.banned and instance.banned:
                logger.info(
                    f"User {instance.username} is being banned, cleaning up sandboxes..."
                )

                active_sandboxes = Sandbox.objects.filter(
                    user_id=instance.id, active=True
                )

                for sandbox in active_sandboxes:
                    cleanup_sandbox.delay(sandbox.id)

                logger.info(
                    f"Scheduled cleanup for {active_sandboxes.count()} sandboxes for user {instance.username}"
                )
        except User.DoesNotExist:
            pass
