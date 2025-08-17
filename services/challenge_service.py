import json
import logging
import os
from typing import Optional, Tuple, cast, Dict

from challenge.models import Challenge, Submission, Sandbox
from challenge.exceptions import SandboxCreateTimeoutException
from challenge.utils import (
    create_loop_device,
    mount_volume,
    clean_up_volume,
    acquire_lock,
    release_lock,
)
from services.docker_service import DockerService
from services.firewall_service import get_firewall_service
from user_auth.models import UserSession

logger = logging.getLogger(__name__)


class ChallengeService:
    def __init__(self) -> None:
        self.docker_service = DockerService()

    def submit_flag(
        self, user_id: int, challenge_id: int, flag: str
    ) -> Tuple[bool, str]:
        try:
            challenge = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return False, "Challenge not found"

        already_solved = Submission.objects.filter(
            user_id=user_id, challenge_id=challenge_id, correct=True
        ).exists()

        if already_solved:
            return False, "You have already solved this challenge."

        is_correct = flag.strip() == challenge.flag.strip()
        submission = Submission(
            user_id=user_id, challenge_id=challenge_id, correct=is_correct
        )

        try:
            submission.save()

            if is_correct:
                logger.info(
                    f"Flag submitted correctly: user_id={user_id}, challenge_id={challenge_id}"
                )
                return True, "correct flag"
            else:
                logger.info(
                    f"Flag submitted incorrectly: user_id={user_id}, challenge_id={challenge_id}"
                )
                return False, "incorrect flag"
        except Exception:
            logger.error(
                f"Error submitting flag: user_id={user_id}, challenge_id={challenge_id}",
                exc_info=True,
            )
            return False, "Error submitting flag, please try again later."

    def get_or_create_sandbox(
        self, challenge: Challenge, user_id: Optional[int] = None
    ) -> Optional[Sandbox]:
        if challenge.static:
            sandbox_q_kwargs = {"challenge_id": challenge.id, "active": True}
            lock_name = f"sandbox_lock_{challenge.id}"
        else:
            if not user_id:
                logger.error(
                    f"user_id required for non-static challenge: challenge_id={challenge.id}"
                )
                return None
            sandbox_q_kwargs = {
                "challenge_id": challenge.id,
                "active": True,
                "user_id": user_id,
            }
            lock_name = f"sandbox_lock_{challenge.id}_{user_id}"

        sandbox = Sandbox.objects.filter(**sandbox_q_kwargs).first()
        if sandbox:
            logger.info(
                f"Sandbox already exists: sandbox_id={sandbox.id}, challenge_id={challenge.id}"
            )
            return sandbox

        if not acquire_lock(lock_name):
            logger.warning(
                f"Failed to acquire lock for sandbox creation: lock_name={lock_name}"
            )
            return None

        try:
            sandbox = Sandbox.objects.filter(**sandbox_q_kwargs).first()
            if sandbox:
                logger.info(
                    f"Sandbox created by another process: sandbox_id={sandbox.id}"
                )
                return sandbox

            sandbox = self._create_sandbox(challenge, user_id)
            return sandbox
        finally:
            release_lock(lock_name)

    def _create_sandbox(
        self, challenge: Challenge, user_id: Optional[int] = None
    ) -> Optional[Sandbox]:
        challenge_ports = {"8000/tcp": None}
        if challenge.tcp_ports:
            challenge_ports = {f"{port}/tcp": None for port in challenge.tcp_ports}

        container_name = (
            f"xctf-{challenge.id}-{user_id}" if user_id else f"xctf-{challenge.id}"
        )

        try:
            volume_file = create_loop_device(challenge.id, user_id, 100)
            mount_point = mount_volume(volume_file, challenge.id, user_id)
        except Exception:
            logger.error(
                f"Error creating volume: challenge_id={challenge.id}", exc_info=True
            )
            clean_up_volume(challenge.id, user_id)
            raise

        container = None
        try:
            container = self.docker_service.create_container(
                image=cast(str, challenge.image_tag),
                name=container_name,
                ports=cast(Dict[str, Optional[int]], challenge_ports),
                volumes=cast(
                    Dict[str, Dict[str, str]],
                    {mount_point: {"bind": "/data", "mode": "rw"}},
                ),
                labels={
                    "user_id": str(user_id) if user_id else "",
                    "challenge_id": str(challenge.id),
                },
            )

            if not self.docker_service.wait_for_healthy(container.id, timeout=60):  # type: ignore
                raise SandboxCreateTimeoutException

            container.reload()
            if "8000/tcp" not in container.ports or not container.ports["8000/tcp"]:
                raise ValueError("Required port 8000/tcp not found in container")

            port_mappings = {
                k.split("/")[0]: v[0]["HostPort"]
                for k, v in container.ports.items()
                if k.split("/")[1] == "tcp"
            }

            port_mappings_file = os.path.join(mount_point, ".xctf_port_mappings.json")
            try:
                with open(port_mappings_file, "w") as f:
                    json.dump(port_mappings, f)
                os.chmod(port_mappings_file, 0o644)
                logger.info(f"Wrote port mappings to {port_mappings_file}")
            except Exception:
                logger.warning("Failed to write port mappings file", exc_info=True)

            container_port = container.ports["8000/tcp"][0]["HostPort"]

            try:
                sandbox = Sandbox(
                    container_id=container.id,  # type: ignore
                    container_port=container_port,
                    challenge_id=challenge.id,
                    active=True,
                    user_id=user_id,
                    port_mappings=port_mappings,
                )
                sandbox.save()
                logger.info(
                    f"Sandbox created successfully: sandbox_id={sandbox.id}, challenge_id={challenge.id}"
                )

                self._add_sandbox_firewall_rules(sandbox, challenge)
                return sandbox
            except Exception:
                logger.error(
                    f"Error saving sandbox to database: challenge_id={challenge.id}",
                    exc_info=True,
                )

                if (
                    container
                    and "8000/tcp" in container.ports
                    and container.ports["8000/tcp"]
                ):
                    try:
                        container_port = container.ports["8000/tcp"][0]["HostPort"]
                        firewall_service = get_firewall_service()
                        firewall_service.remove_all_port_mappings_for_sandbox(
                            container_port, None
                        )
                    except Exception:
                        logger.warning(
                            "Failed to cleanup firewall rules during error handling",
                            exc_info=True,
                        )

                self.docker_service.stop_and_remove_container(container.id)  # type: ignore
                clean_up_volume(challenge.id, user_id)
                raise

        except Exception:
            logger.error("Error creating sandbox", exc_info=True)
            if container:
                try:
                    if "8000/tcp" in container.ports and container.ports["8000/tcp"]:
                        try:
                            container_port = container.ports["8000/tcp"][0]["HostPort"]
                            firewall_service = get_firewall_service()
                            firewall_service.remove_all_port_mappings_for_sandbox(
                                container_port, None
                            )
                        except Exception:
                            logger.warning(
                                "Failed to cleanup firewall rules during error handling",
                                exc_info=True,
                            )

                    self.docker_service.stop_and_remove_container(container.id)  # type: ignore
                except Exception:
                    logger.error("Error stopping and removing container", exc_info=True)
                    pass
            clean_up_volume(challenge.id, user_id)
            raise

    def check_user_solved_challenge(
        self, user_id: Optional[int], challenge_id: int
    ) -> bool:
        if not user_id:
            logger.error(
                f"User ID is required to check if user has solved challenge: challenge_id={challenge_id}"
            )
            return False
        return Submission.objects.filter(
            user_id=user_id, challenge_id=challenge_id, correct=True
        ).exists()

    def _add_sandbox_firewall_rules(
        self, sandbox: Sandbox, challenge: Challenge
    ) -> None:
        try:
            firewall_service = get_firewall_service()
            firewall_service.initialize_firewall()

            if challenge.static:
                firewall_service.add_static_port(sandbox.container_port)
                if sandbox.port_mappings:
                    for port in sandbox.port_mappings.values():
                        if isinstance(port, (int, str)):
                            try:
                                port_int = int(port)
                                firewall_service.add_static_port(port_int)
                            except (ValueError, TypeError):
                                pass
                logger.info(
                    f"Added static sandbox ports to firewall: sandbox_id={sandbox.id}"
                )
                return

            if not sandbox.user_id:
                logger.warning(
                    f"Cannot add firewall rules: sandbox has no user_id: sandbox_id={sandbox.id}"
                )
                return

            user_session = UserSession.objects.filter(
                user_id=sandbox.user_id, active=True
            ).first()

            if not user_session:
                logger.warning(
                    f"Cannot add firewall rules: no active session found for user_id={sandbox.user_id}"
                )
                return

            ip_address = user_session.ip_address
            firewall_service.add_port_ip_mapping(sandbox.container_port, ip_address)

            if sandbox.port_mappings:
                for port in sandbox.port_mappings.values():
                    if isinstance(port, (int, str)):
                        try:
                            port_int = int(port)
                            firewall_service.add_port_ip_mapping(port_int, ip_address)
                        except (ValueError, TypeError):
                            pass

            logger.info(
                f"Added firewall rules for sandbox: sandbox_id={sandbox.id}, ip={ip_address}"
            )
        except Exception:
            logger.error(
                f"Failed to add firewall rules for sandbox: sandbox_id={sandbox.id}",
                exc_info=True,
            )
