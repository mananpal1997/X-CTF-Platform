import json
import logging
import os
import subprocess

import jsonschema
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from django.core.paginator import Paginator

from user_auth.models import User
from challenge.models import Challenge, Submission, Sandbox
from services.docker_service import DockerService
from services.firewall_service import get_firewall_service
from challenge.utils import clean_up_volume, get_redis_client
from django.conf import settings
from tasks.tasks import send_notification
from typing import Callable, ParamSpec, TypeVar, Concatenate, cast
from django.http import HttpRequest, HttpResponse

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)

logger = logging.getLogger(__name__)

metadata_schema = {
    "type": "object",
    "properties": {
        "NAME": {"type": "string"},
        "POINTS": {"type": "integer"},
        "FLAG": {"type": "string"},
        "ACTIVE": {"type": "boolean"},
        "CATEGORY": {"type": "string"},
        "STATIC": {"type": "boolean"},
        "TCP_PORTS": {"type": "array", "items": {"type": "integer"}},
    },
}


def admin_required(
    view_func: Callable[Concatenate[HttpRequest, P], R],
) -> Callable[Concatenate[HttpRequest, P], R]:
    def wrapper(request: HttpRequest, /, *args: P.args, **kwargs: P.kwargs) -> R:
        user = getattr(request, "user", None)
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            messages.error(request, "You must be logged in to access the admin panel.")
            return cast(R, redirect("home"))
        if not hasattr(user, "is_admin") or not user.is_admin:
            messages.error(
                request, "You do not have permission to access the admin panel."
            )
            return cast(R, redirect("home"))
        return view_func(request, *args, **kwargs)

    return wrapper


@admin_required
def admin_index(request: HttpRequest) -> HttpResponse:
    context = {
        "title": "Admin Panel",
    }
    return render(request, "admin/index.html", context)


@admin_required
def user_list(request: HttpRequest) -> HttpResponse:
    users = User.objects.all().order_by("-id")

    search = request.GET.get("search", "")
    if search:
        users = users.filter(Q(username__icontains=search) | Q(email__icontains=search))

    paginator = Paginator(users, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "title": "Users",
        "users": page_obj,
        "search": search,
    }
    return render(request, "admin/user_list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def user_edit(request: HttpRequest, user_id: int) -> HttpResponse:
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect("admin:user_list")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        is_admin = request.POST.get("is_admin") == "on"
        banned = request.POST.get("banned") == "on"
        verified = request.POST.get("verified") == "on"

        if User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, "Username already exists.")
        elif User.objects.filter(email=email).exclude(id=user_id).exists():
            messages.error(request, "Email already exists.")
        else:
            was_banned = user.banned
            user.username = username
            user.email = email
            user.is_admin = is_admin
            user.banned = banned
            user.verified = verified
            user.save()

            redis_client = get_redis_client()
            cache_key = f"user:{user.id}"
            redis_client.delete(cache_key)

            if not was_banned and banned:
                messages.warning(request, f"User {user.username} has been banned.")
            else:
                messages.success(request, "User updated successfully.")
            return redirect("admin:user_list")

    context = {
        "title": f"Edit User: {user.username}",
        "user_obj": user,
    }
    return render(request, "admin/user_edit.html", context)


@admin_required
def challenge_list(request: HttpRequest) -> HttpResponse:
    challenges = Challenge.objects.all().order_by("-id")

    search = request.GET.get("search", "")
    if search:
        challenges = challenges.filter(
            Q(name__icontains=search) | Q(category__icontains=search)
        )

    paginator = Paginator(challenges, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "title": "Challenges",
        "challenges": page_obj,
        "search": search,
    }
    return render(request, "admin/challenge_list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def challenge_edit_metadata(request: HttpRequest, challenge_id: int) -> HttpResponse:
    try:
        challenge = Challenge.objects.get(id=challenge_id)
    except Challenge.DoesNotExist:
        messages.error(request, "Challenge not found.")
        return redirect("admin:challenge_list")

    if not challenge.metadata_filepath or not os.path.exists(
        challenge.metadata_filepath
    ):
        messages.error(
            request, f"Metadata file not found for challenge {challenge.name}."
        )
        return redirect("admin:challenge_list")

    if request.method == "POST":
        try:
            metadata_content = json.loads(request.POST["metadata"])
            jsonschema.validate(metadata_content, metadata_schema)

            with open(challenge.metadata_filepath, "w") as metadata_file:
                json.dump(metadata_content, metadata_file, indent=4)

            messages.success(request, "Metadata file updated successfully.")

            challenge_dir_name = os.path.dirname(challenge.metadata_filepath).split(
                "/"
            )[-1]
            result = subprocess.run(
                [
                    "python",
                    "manage.py",
                    "setup_challenges",
                    "--challenge-name",
                    challenge_dir_name,
                    "--challenges-dir",
                    settings.CHALLENGES_DIRECTORY,
                ],
                cwd=settings.BASE_DIR,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                messages.success(request, "Challenge setup updated successfully.")
            else:
                messages.warning(
                    request, f"Challenge setup had issues: {result.stderr}"
                )

        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON format.")
        except jsonschema.ValidationError as e:
            messages.error(request, f"Invalid metadata format: {e.message}")
        except Exception as e:
            logger.error("Error updating metadata:", exc_info=True)
            messages.error(request, f"Error updating metadata: {str(e)}")

        return redirect("admin:challenge_list")

    with open(challenge.metadata_filepath, "r") as metadata_file:
        metadata_content = metadata_file.read()

    context = {
        "title": f"Edit Metadata for {challenge.name}",
        "challenge": challenge,
        "metadata_content": metadata_content,
    }
    return render(request, "admin/edit_challenge_metadata.html", context)


@admin_required
def sandbox_list(request: HttpRequest) -> HttpResponse:
    sandboxes = (
        Sandbox.objects.select_related("challenge", "user").all().order_by("-id")
    )

    search = request.GET.get("search", "")
    if search:
        sandboxes = sandboxes.filter(
            Q(container_id__icontains=search)
            | Q(challenge__name__icontains=search)
            | Q(user__username__icontains=search)
        )

    paginator = Paginator(sandboxes, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "title": "Sandboxes",
        "sandboxes": page_obj,
        "search": search,
    }
    return render(request, "admin/sandbox_list.html", context)


@admin_required
def submission_list(request: HttpRequest) -> HttpResponse:
    submissions = (
        Submission.objects.select_related("user", "challenge")
        .all()
        .order_by("-submitted_at")
    )

    search = request.GET.get("search", "")
    if search:
        submissions = submissions.filter(
            Q(user__username__icontains=search) | Q(challenge__name__icontains=search)
        )

    correct_filter = request.GET.get("correct", "")
    if correct_filter == "true":
        submissions = submissions.filter(correct=True)
    elif correct_filter == "false":
        submissions = submissions.filter(correct=False)

    paginator = Paginator(submissions, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "title": "Submissions",
        "submissions": page_obj,
        "search": search,
        "correct_filter": correct_filter,
    }
    return render(request, "admin/submission_list.html", context)


@admin_required
def docker_containers(request: HttpRequest) -> HttpResponse:
    docker_service = DockerService()
    containers = docker_service.list_containers(all=True)
    containers = [
        container
        for container in containers
        if container.name and container.name.startswith("xctf-")
    ]

    context = {
        "title": "Docker Containers",
        "containers": containers,
    }
    return render(request, "admin/docker_containers.html", context)


@admin_required
@require_http_methods(["POST"])
def docker_stop_container(request: HttpRequest, container_id: str) -> HttpResponse:
    docker_service = DockerService()
    try:
        if docker_service.stop_container(container_id):
            messages.success(request, f"Container {container_id} stopped.")
        else:
            messages.warning(
                request, f"Container {container_id} not found or already stopped."
            )
    except Exception as e:
        logger.error("Error stopping container", exc_info=True)
        messages.error(request, f"Error stopping container: {str(e)}")
    return redirect("admin:docker_containers")


@admin_required
@require_http_methods(["POST"])
def docker_remove_container(request: HttpRequest, container_id: str) -> HttpResponse:
    docker_service = DockerService()
    try:
        container = docker_service.get_container(container_id)

        user_id_label = container.labels.get("user_id")
        user_id = int(user_id_label) if user_id_label else None
        challenge_id = int(container.labels.get("challenge_id"))

        sandbox = Sandbox.objects.filter(
            container_id=container_id,
            challenge_id=challenge_id,
            user_id=user_id,  # type: ignore
            active=True,
        ).first()

        if sandbox:
            firewall_service = get_firewall_service()
            try:
                firewall_service.remove_all_port_mappings_for_sandbox(
                    sandbox.container_port, sandbox.port_mappings
                )
                logger.info(
                    f"Removed firewall rules for sandbox {sandbox.id} before container removal"
                )
            except Exception:
                logger.error("Error removing firewall rules:", exc_info=True)

        if docker_service.remove_container(container_id, force=True):
            messages.success(request, f"Container {container_id} removed.")

            clean_up_volume(challenge_id, user_id)
            messages.success(
                request, f"Volumes associated with {container_id} removed."
            )

            if sandbox:
                sandbox.active = False
                sandbox.destroyed_at = timezone.now()
                sandbox.save()
                messages.success(request, f"Sandbox {sandbox.id} deactivated.")
        else:
            messages.warning(request, f"Container {container_id} not found.")
    except Exception as e:
        logger.error("Error removing container", exc_info=True)
        messages.error(request, f"Error removing container: {str(e)}")
    return redirect("admin:docker_containers")


@admin_required
def send_notifications(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        message = request.POST.get("message", "").strip()
        if not message:
            messages.error(request, "Empty message not allowed")
            return redirect("admin:send_notifications")

        send_notification.delay(message, to_all=True)
        messages.success(request, "Notification sent to all users.")
        return redirect("admin:send_notifications")

    context = {
        "title": "Send Notifications",
    }
    return render(request, "admin/notifications.html", context)
