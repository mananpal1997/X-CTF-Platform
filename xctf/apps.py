from django.apps import AppConfig
import logging
import sys
import threading

logger = logging.getLogger(__name__)


class XctfConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "xctf"

    def ready(self) -> None:
        if (
            "migrate" in sys.argv
            or "makemigrations" in sys.argv
            or "collectstatic" in sys.argv
        ):
            return

        def initialize_firewall_sync() -> None:
            try:
                from services.firewall_service import get_firewall_service
                from user_auth.models import UserSession
                from challenge.models import Sandbox
                from django.db import OperationalError, ProgrammingError
                from django.db import connections

                connections.close_all()

                logger.info("Initializing firewall on startup...")
                firewall_service = get_firewall_service()
                firewall_service.initialize_firewall()

                try:
                    logger.info("Rebuilding firewall rules from database...")

                    active_sessions = UserSession.objects.filter(active=True)
                    active_ports = set()

                    for session in active_sessions:
                        active_sandboxes = Sandbox.objects.filter(
                            user_id=session.user_id, active=True
                        ).select_related("challenge")

                        for sandbox in active_sandboxes:
                            if not sandbox.challenge.static:
                                firewall_service.add_port_ip_mapping(
                                    sandbox.container_port, session.ip_address
                                )
                                active_ports.add(sandbox.container_port)

                                if sandbox.port_mappings:
                                    for port in sandbox.port_mappings.values():
                                        if isinstance(port, (int, str)):
                                            try:
                                                port_int = int(port)
                                                firewall_service.add_port_ip_mapping(
                                                    port_int, session.ip_address
                                                )
                                                active_ports.add(port_int)
                                            except (ValueError, TypeError):
                                                pass

                    static_sandboxes = Sandbox.objects.filter(
                        active=True, challenge__static=True
                    )

                    for sandbox in static_sandboxes:
                        firewall_service.add_static_port(sandbox.container_port)
                        active_ports.add(sandbox.container_port)

                        if sandbox.port_mappings:
                            for port in sandbox.port_mappings.values():
                                if isinstance(port, (int, str)):
                                    try:
                                        port_int = int(port)
                                        firewall_service.add_static_port(port_int)
                                        active_ports.add(port_int)
                                    except (ValueError, TypeError):
                                        pass

                    firewall_service.clean_orphan_ports(active_ports)

                    logger.info("Firewall rules rebuilt successfully")
                except (ProgrammingError, OperationalError) as e:
                    error_msg = str(e)
                    if (
                        "doesn't exist" in error_msg
                        or "no such table" in error_msg.lower()
                    ):
                        logger.info(
                            "UserSession table does not exist yet, skipping firewall rule rebuild (normal during migration)"
                        )
                    else:
                        logger.warning(
                            f"Database error during firewall rebuild: {error_msg}"
                        )
                finally:
                    connections.close_all()
            except Exception:
                logger.error("Error initializing firewall on startup", exc_info=True)

        thread = threading.Thread(target=initialize_firewall_sync, daemon=True)
        thread.start()
