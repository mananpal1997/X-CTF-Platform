import logging
from django.conf import settings
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout as django_logout
from django.utils.deprecation import MiddlewareMixin

from .models import User, UserSession
from challenge.utils import get_redis_client
from services.firewall_service import get_firewall_service
from challenge.models import Sandbox
from django.http import HttpRequest, HttpResponse
from typing import Optional, Any

logger = logging.getLogger(__name__)


class UserStatusMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> Optional[Any]:
        user: Optional[User] = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        user_id: int = user.id

        if user.banned:
            django_logout(request)
            request.session.flush()
            try:
                cache_key = f"user:{user_id}"
                redis_client = get_redis_client()
                redis_client.delete(cache_key)
            except Exception:
                pass
            messages.error(request, "Your account has been banned.")
            return redirect("home")

        if not user.is_admin:
            if not hasattr(request, "_ip_session_checked"):
                firewall_service = get_firewall_service()
                client_ip = firewall_service.get_client_ip(request)

                has_active_session = UserSession.objects.filter(
                    user_id=user_id, ip_address=client_ip, active=True
                ).exists()

                request._ip_session_checked = True  # type: ignore
                request._has_active_session = has_active_session  # type: ignore

                if not has_active_session:
                    old_session = (
                        UserSession.objects.filter(user_id=user_id, active=True)
                        .only("id", "ip_address")
                        .first()
                    )

                    if old_session:
                        old_ip = old_session.ip_address
                        try:
                            firewall_service.initialize_firewall()

                            active_sandboxes = (
                                Sandbox.objects.filter(user_id=user_id, active=True)
                                .select_related("challenge")
                                .only(
                                    "container_port",
                                    "port_mappings",
                                    "challenge__static",
                                )
                            )

                            for sandbox in active_sandboxes:
                                if sandbox.challenge.static:
                                    continue

                                firewall_service.remove_port_ip_mapping(
                                    sandbox.container_port, old_ip
                                )

                                if sandbox.port_mappings:
                                    for port in sandbox.port_mappings.values():
                                        if isinstance(port, (int, str)):
                                            try:
                                                port_int = int(port)
                                                firewall_service.remove_port_ip_mapping(
                                                    port_int, old_ip
                                                )
                                            except (ValueError, TypeError):
                                                pass

                            old_session.active = False
                            old_session.save(update_fields=["active"])
                        except Exception:
                            logger.error(
                                "Failed to remove firewall rules during IP mismatch logout",
                                exc_info=True,
                            )
                            if old_session:
                                old_session.active = False
                                old_session.save(update_fields=["active"])

                    django_logout(request)
                    request.session.flush()
                    messages.warning(
                        request,
                        "Your session IP address has changed. Please log in again.",
                    )
                    return redirect("login")

        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response["X-Frame-Options"] = "DENY"

        response["X-Content-Type-Options"] = "nosniff"

        response["X-XSS-Protection"] = "1; mode=block"

        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        host = request.get_host().split(":")[0].lower()
        is_secure = request.is_secure() or host in (
            "localhost",
            "127.0.0.1",
            "::1",
            settings.SERVER_NAME.split(":")[0],
        )
        if is_secure:
            response["Cross-Origin-Opener-Policy"] = "same-origin"

        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "frame-ancestors 'none';"
        )
        response["Content-Security-Policy"] = csp

        return response
