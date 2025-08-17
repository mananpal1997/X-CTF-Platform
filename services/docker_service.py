import docker
from docker.models.containers import Container
import logging
import time
from typing import Dict, Optional, List, Any, cast

logger = logging.getLogger(__name__)


class DockerService:
    def __init__(self) -> None:
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def create_container(
        self,
        image: str,
        name: str,
        ports: Optional[Dict[str, Optional[int]]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        labels: Optional[Dict[str, str]] = None,
        mem_limit: str = "512m",
        memswap_limit: str = "512m",
        cpu_quota: int = 50000,
        detach: bool = True,
    ) -> Container:
        try:
            logger.info(f"Creating container: image={image}, name={name}")
            container = self.client.containers.run(  # type: ignore
                image,
                detach=detach,
                ports=ports or {},
                name=name,
                mem_limit=mem_limit,
                memswap_limit=memswap_limit,
                cpu_quota=cpu_quota,
                volumes=volumes or {},
                labels=labels or {},
            )
            container.reload()
            logger.info(f"Container created: container_id={container.id}, name={name}")
            return cast(Container, container)
        except docker.errors.ImageNotFound:
            logger.error(f"Docker image not found: image={image}", exc_info=True)
            raise
        except docker.errors.APIError:
            logger.error(f"Docker API error: image={image}", exc_info=True)
            raise
        except Exception:
            logger.error(
                f"Unexpected error creating container: image={image}", exc_info=True
            )
            raise

    def get_container(self, container_id: str) -> Container:
        try:
            return self.client.containers.get(container_id)
        except docker.errors.NotFound:
            logger.warning(
                f"Container not found: container_id={container_id}", exc_info=True
            )
            raise
        except Exception:
            logger.error(
                f"Error getting container: container_id={container_id}", exc_info=True
            )
            raise

    def stop_container(self, container_id: str) -> bool:
        try:
            container = self.get_container(container_id)
            logger.info(
                f"Stopping container: container_id={container_id}, name={container.name}"
            )
            container.stop()
            logger.info(f"Container stopped: container_id={container_id}")
            return True
        except docker.errors.NotFound:
            logger.warning(
                f"Container not found for stopping: container_id={container_id}",
                exc_info=True,
            )
            return False
        except Exception:
            logger.error(
                f"Error stopping container: container_id={container_id}", exc_info=True
            )
            return False

    def remove_container(self, container_id: str, force: bool = True) -> bool:
        try:
            container = self.get_container(container_id)
            logger.info(
                f"Removing container: container_id={container_id}, name={container.name}, force={force}"
            )
            container.remove(force=force)
            logger.info(f"Container removed: container_id={container_id}")
            return True
        except docker.errors.NotFound:
            logger.warning(
                f"Container not found for removal: container_id={container_id}",
                exc_info=True,
            )
            return False
        except Exception:
            logger.error(
                f"Error removing container: container_id={container_id}", exc_info=True
            )
            return False

    def stop_and_remove_container(self, container_id: str, force: bool = True) -> bool:
        try:
            self.stop_container(container_id)
            return self.remove_container(container_id, force=force)
        except Exception:
            logger.error(
                f"Error stopping and removing container: container_id={container_id}",
                exc_info=True,
            )
            return False

    def list_containers(
        self, all: bool = True, filters: Optional[Dict[str, Any]] = None
    ) -> List[Container]:
        try:
            return self.client.containers.list(all=all, filters=filters or {})
        except Exception:
            logger.error(f"Error listing containers: filters={filters}", exc_info=True)
            raise

    def get_container_health(self, container_id: str) -> Optional[str]:
        try:
            container = self.get_container(container_id)
            container.reload()
            return getattr(container, "health", None)
        except Exception:
            logger.error(
                f"Error getting container health: container_id={container_id}",
                exc_info=True,
            )
            return None

    def wait_for_healthy(self, container_id: str, timeout: int = 60) -> bool:
        start_time = time.perf_counter()

        while time.perf_counter() - start_time < timeout:
            health = self.get_container_health(container_id)
            if health == "healthy":
                logger.info(f"Container is healthy: container_id={container_id}")
                return True
            time.sleep(1)

        logger.warning(
            f"Container health check timeout: container_id={container_id}, timeout={timeout}"
        )
        return False
