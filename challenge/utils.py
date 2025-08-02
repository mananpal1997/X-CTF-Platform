import os
import subprocess
import time
import logging
import redis
from django.conf import settings
from urllib.parse import urlparse
from typing import List, Optional

logger = logging.getLogger(__name__)


def get_redis_client() -> redis.Redis:
    redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    redis_password = getattr(settings, "REDIS_PASSWORD", None)
    if redis_password:
        parsed = urlparse(redis_url)
        redis_url = (
            f"redis://:{redis_password}@{parsed.hostname}:{parsed.port}{parsed.path}"
        )
    return redis.from_url(redis_url)  # type: ignore


def acquire_lock(lock_name: str, timeout: int = 10) -> bool:
    redis_client = get_redis_client()
    start_time = time.time()
    while time.time() - start_time < timeout:
        if redis_client.setnx(lock_name, 1):
            redis_client.expire(lock_name, timeout)
            return True
        time.sleep(0.1)
    return False


def release_lock(lock_name: str) -> None:
    redis_client = get_redis_client()
    redis_client.delete(lock_name)


def run_command(args: List[str], check: bool = True) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=check)
    if result.returncode != 0 and check:
        raise subprocess.CalledProcessError(
            result.returncode, args, result.stdout, result.stderr
        )
    return result.stdout.strip()


def create_loop_device(challenge_id: int, user_id: Optional[int], size_mb: int) -> str:
    volume_base = getattr(
        settings, "CHALLENGE_CONTAINER_VOLUME_BASE", "/tmp/xctf_volumes"
    )
    if user_id:
        volume_file = os.path.join(
            volume_base, f"challenge_{challenge_id}_{user_id}_container.img"
        )
    else:
        volume_file = os.path.join(
            volume_base, f"challenge_{challenge_id}_container.img"
        )

    if not os.path.exists(volume_file):
        logger.info(
            f"Creating loop device file: challenge_id={challenge_id}, user_id={user_id}, volume_file={volume_file}, size_mb={size_mb}"
        )
        run_command(
            ["dd", "if=/dev/zero", f"of={volume_file}", "bs=1M", f"count={size_mb}"]
        )
        run_command(["mkfs.ext4", volume_file])
    else:
        logger.debug(f"Loop device file already exists: volume_file={volume_file}")
    return volume_file


def mount_volume(volume_file: str, challenge_id: int, user_id: Optional[int]) -> str:
    volume_base = getattr(
        settings, "CHALLENGE_CONTAINER_VOLUME_BASE", "/tmp/xctf_volumes"
    )
    if user_id:
        mount_point = os.path.join(
            volume_base, f"challenge_{challenge_id}_{user_id}_container"
        )
    else:
        mount_point = os.path.join(volume_base, f"challenge_{challenge_id}_container")

    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    logger.info(
        f"Mounting volume: volume_file={volume_file}, mount_point={mount_point}, challenge_id={challenge_id}, user_id={user_id}"
    )
    run_command(["sudo", "mount", "-o", "loop", volume_file, mount_point])
    return mount_point


def unmount_volume(challenge_id: int, user_id: Optional[int]) -> str:
    volume_base = getattr(
        settings, "CHALLENGE_CONTAINER_VOLUME_BASE", "/tmp/xctf_volumes"
    )
    if user_id:
        mount_point = os.path.join(
            volume_base, f"challenge_{challenge_id}_{user_id}_container"
        )
    else:
        mount_point = os.path.join(volume_base, f"challenge_{challenge_id}_container")

    try:
        logger.info(
            f"Unmounting volume: mount_point={mount_point}, challenge_id={challenge_id}, user_id={user_id}"
        )
        run_command(["sudo", "umount", mount_point])
    except subprocess.CalledProcessError:
        logger.error(
            f"Failed to unmount volume (mount_point={mount_point}, challenge_id={challenge_id}, user_id={user_id})",
            exc_info=True,
        )
    return mount_point


def clean_up_volume(challenge_id: int, user_id: Optional[int]) -> None:
    volume_base = getattr(
        settings, "CHALLENGE_CONTAINER_VOLUME_BASE", "/tmp/xctf_volumes"
    )
    try:
        if user_id:
            volume_file = os.path.join(
                volume_base, f"challenge_{challenge_id}_{user_id}_container.img"
            )
            mount_point = os.path.join(
                volume_base, f"challenge_{challenge_id}_{user_id}_container"
            )
        else:
            volume_file = os.path.join(
                volume_base, f"challenge_{challenge_id}_container.img"
            )
            mount_point = os.path.join(
                volume_base, f"challenge_{challenge_id}_container"
            )

        unmount_volume(challenge_id, user_id)

        if os.path.exists(volume_file):
            logger.info(
                f"Removing loop device file: volume_file={volume_file}, challenge_id={challenge_id}, user_id={user_id}"
            )
            os.remove(volume_file)
        else:
            logger.debug(f"Loop device file does not exist: volume_file={volume_file}")

        if os.path.exists(mount_point):
            logger.info(
                f"Removing mount point: mount_point={mount_point}, challenge_id={challenge_id}, user_id={user_id}"
            )
            os.rmdir(mount_point)
        else:
            logger.debug(f"Mount point does not exist: mount_point={mount_point}")

        logger.info(
            f"Cleanup complete for volume: challenge_id={challenge_id}, user_id={user_id}"
        )
    except Exception:
        logger.error(
            f"Error during volume cleanup: challenge_id={challenge_id}, user_id={user_id}",
            exc_info=True,
        )
