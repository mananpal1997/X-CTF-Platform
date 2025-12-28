from datetime import timedelta
import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Q, OuterRef, Exists
from typing import Optional, List, Tuple, cast

from challenge.models import Sandbox, Challenge, Submission
from challenge.utils import clean_up_volume
from notifications.models import Notification
from user_auth.models import User, UserSession
from services.docker_service import DockerService
from services.firewall_service import get_firewall_service
from services.challenge_service import ChallengeService
from notifications.views import publish_notification

logger = logging.getLogger(__name__)


@shared_task  # type: ignore
def cleanup_sandbox(sandbox_id: int) -> None:
    docker_service = DockerService()
    firewall_service = get_firewall_service()

    try:
        sandbox = Sandbox.objects.get(id=sandbox_id)
    except Sandbox.DoesNotExist:
        logger.warning(f"Sandbox not found: sandbox_id={sandbox_id}", exc_info=True)
        return

    try:
        firewall_service.remove_all_port_mappings_for_sandbox(
            sandbox.container_port, sandbox.port_mappings
        )
        logger.info(
            f"Removed all firewall rules for sandbox: sandbox_id={sandbox_id}, port={sandbox.container_port}"
        )
    except Exception:
        logger.error(
            f"Error removing firewall rules during cleanup: sandbox_id={sandbox_id}",
            exc_info=True,
        )

    try:
        logger.info(
            f"Cleaning up sandbox: sandbox_id={sandbox_id}, container_id={sandbox.container_id}"
        )
        docker_service.stop_and_remove_container(sandbox.container_id, force=True)
        logger.info(f"Container removed successfully: sandbox_id={sandbox_id}")
    except Exception:
        logger.error(
            f"Error removing container during cleanup: sandbox_id={sandbox_id}",
            exc_info=True,
        )

    sandbox.active = False
    sandbox.destroyed_at = timezone.now()
    sandbox.save()

    clean_up_volume(sandbox.challenge_id, sandbox.user_id)


@shared_task  # type: ignore
def destroy_non_static_sandboxes() -> None:
    now = timezone.now()

    sandboxes_to_destroy = Sandbox.objects.filter(
        active=True, challenge__static=False
    ).filter(
        Q(
            Exists(
                Submission.objects.filter(
                    challenge_id=OuterRef("challenge_id"),
                    user_id=OuterRef("user_id"),
                    correct=True,
                )
            )
        )
        | Q(created_at__lte=now - timedelta(hours=2))
    )

    for sandbox in sandboxes_to_destroy:
        logger.info(f"Destroying non-static sandbox: sandbox_id={sandbox.id}")
        cleanup_sandbox.delay(sandbox.id)

    logger.info(
        f"Scheduled cleanup for {sandboxes_to_destroy.count()} non-static sandboxes"
    )


@shared_task  # type: ignore
def refresh_sandboxes(challenge_name: str) -> None:
    challenge_service = ChallengeService()

    try:
        challenge = Challenge.objects.get(name=challenge_name)
    except Challenge.DoesNotExist:
        logger.warning(f"Challenge not found: {challenge_name}", exc_info=True)
        return

    if not challenge.active:
        logger.info(f"Challenge is not active: {challenge_name}")
        return

    active_sandboxes = Sandbox.objects.filter(
        challenge_id=challenge.id, active=True
    ).values_list("id", "user_id")

    for sandbox_id, user_id in cast(List[Tuple[int, Optional[int]]], active_sandboxes):
        cleanup_sandbox(sandbox_id)
        try:
            if user_id:
                _ = User.objects.get(id=user_id)
                challenge_service._create_sandbox(challenge, user_id)
                send_notification.delay(
                    f"Your sandbox has been updated for challenge named {challenge_name}.",
                    user_id=user_id,
                )
            else:
                challenge_service._create_sandbox(challenge, None)
                send_notification.delay(
                    f"Your sandbox has been updated for challenge named {challenge_name}.",
                    to_all=True,
                )
        except Exception:
            logger.error(
                f"Error refreshing sandbox: challenge_name={challenge_name}, sandbox_id={sandbox_id}",
                exc_info=True,
            )

    logger.info(f"Refreshed sandboxes for challenge: {challenge_name}")


@shared_task  # type: ignore
def send_notification(
    message: str, user_id: Optional[int] = None, to_all: bool = False
) -> None:
    if to_all:
        users = User.objects.all()
        for user in users:
            Notification.objects.create(message=message, user_id=user.id)
            publish_notification(user.id, message)
    elif user_id:
        Notification.objects.create(message=message, user_id=user_id)
        publish_notification(user_id, message)

    logger.info(
        f"Sent notification: message={message[:50]}..., to_all={to_all}, user_id={user_id}"
    )


@shared_task  # type: ignore
def clean_orphan_firewall_ports() -> None:
    try:
        logger.info("Starting orphan firewall port cleanup...")

        active_sandboxes = Sandbox.objects.filter(active=True)

        active_ports = set()
        for sandbox in active_sandboxes:
            active_ports.add(sandbox.container_port)

            if sandbox.port_mappings:
                for port in sandbox.port_mappings.values():
                    if isinstance(port, (int, str)):
                        try:
                            port_int = int(port)
                            active_ports.add(port_int)
                        except (ValueError, TypeError):
                            pass

        logger.info(
            f"Found {len(active_sandboxes)} active sandboxes with {len(active_ports)} total ports"
        )

        firewall_service = get_firewall_service()
        firewall_service.clean_orphan_ports(active_ports)

        logger.info("Orphan firewall port cleanup completed")
    except Exception:
        logger.error("Error cleaning orphan firewall ports", exc_info=True)


@shared_task  # type: ignore
def cleanup_expired_sessions() -> None:
    now = timezone.now()
    firewall_service = get_firewall_service()

    expired_sessions = UserSession.objects.filter(active=True, expires_at__lte=now)

    for session in expired_sessions:
        try:
            active_sandboxes = Sandbox.objects.filter(
                user_id=session.user_id, active=True
            )

            for sandbox in active_sandboxes:
                if sandbox.challenge.static:
                    continue

                firewall_service.remove_all_port_mappings_for_sandbox(
                    sandbox.container_port, sandbox.port_mappings
                )

            session.active = False
            session.save()
            logger.info(
                f"Cleaned up expired session: user_id={session.user_id}, ip={session.ip_address}"
            )
        except Exception:
            logger.error(
                f"Error cleaning up expired session: session_id={session.id}",
                exc_info=True,
            )

    logger.info(f"Cleaned up {expired_sessions.count()} expired sessions")
