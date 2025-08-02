import re
import time
import logging

from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from typing import cast
from django.contrib.auth.decorators import login_required

from .models import Challenge, Sandbox
from .exceptions import SandboxCreateTimeoutException
from user_auth.decorators import rate_limit
from services.challenge_service import ChallengeService

logger = logging.getLogger(__name__)

challenge_service = ChallengeService()


def get_client_ip(request: HttpRequest) -> str:
    x_forwarded_for: str = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        ips = [ip.strip() for ip in x_forwarded_for.split(",")]
        if ips and ips[0]:
            return ips[0]

    x_real_ip: str = request.META.get("HTTP_X_REAL_IP", "")
    if x_real_ip:
        return x_real_ip.strip()

    return cast(str, request.META.get("REMOTE_ADDR", "0.0.0.0"))


def _generate_sandbox_url(sandbox: Sandbox) -> str:
    server_name = getattr(settings, "SERVER_NAME", "localhost:8080")
    server_url = re.sub(r":\d+$", f":{sandbox.container_port}", server_name)
    return f"http://{server_url}"


@require_http_methods(["POST"])
@rate_limit("5/m", method="POST")
@login_required
def start_challenge(request: HttpRequest, challenge_id: int) -> HttpResponse:
    user = request.user

    try:
        challenge = Challenge.objects.get(id=challenge_id)
    except Challenge.DoesNotExist:
        messages.error(request, "Challenge not found.")
        return redirect("home")

    if not challenge.active:
        messages.error(request, "Challenge is not active.")
        return redirect("home")

    if challenge_service.check_user_solved_challenge(user.id, challenge_id):
        messages.warning(request, "You have already solved it.")
        return redirect("home")

    try:
        user_id_for_sandbox = None if challenge.static else user.id
        sandbox = challenge_service.get_or_create_sandbox(
            challenge, user_id_for_sandbox
        )

        if sandbox:
            return redirect(_generate_sandbox_url(sandbox))
        else:
            retries = 0
            while retries < 10:
                time.sleep(6)

                if challenge.static:
                    sandbox = Sandbox.objects.filter(
                        challenge_id=challenge_id, active=True
                    ).first()
                else:
                    sandbox = Sandbox.objects.filter(
                        challenge_id=challenge_id, active=True, user_id=user.id  # type: ignore
                    ).first()

                if sandbox:
                    return redirect(_generate_sandbox_url(sandbox))
                retries += 1

            messages.error(request, "Error starting challenge, check with admins.")
            return redirect("home")

    except SandboxCreateTimeoutException:
        messages.error(request, "Challenge stuck in unhealthy state")
        return redirect("home")
    except Exception:
        logger.error("Error starting challenge", exc_info=True)
        messages.error(request, "Error starting challenge")
        return redirect("home")


@require_http_methods(["POST"])
@rate_limit("10/m", method="POST")
@login_required
def submit_flag(request: HttpRequest, challenge_id: int) -> HttpResponse:
    user = request.user

    try:
        _ = Challenge.objects.get(id=challenge_id)
    except Challenge.DoesNotExist:
        messages.error(request, "Challenge not found.")
        return redirect("home")

    flag = request.POST.get("flag", "").strip()
    if not flag:
        messages.error(request, "Invalid flag submission.")
        return redirect("home")

    if len(flag) > 500:
        messages.error(request, "Flag is too long.")
        return redirect("home")

    success, message = challenge_service.submit_flag(
        cast(int, user.id), challenge_id, flag
    )

    if success:
        messages.success(request, message)
    else:
        if "already" in message.lower():
            messages.warning(request, message)
        else:
            messages.error(request, message)

    return redirect("home")
