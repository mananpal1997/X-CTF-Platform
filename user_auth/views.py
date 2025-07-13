from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout as django_logout
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import logging

from .models import User, UserSession
from .utils import generate_confirmation_token, confirm_token
from .decorators import rate_limit
from django.core.mail import send_mail
from django.urls import reverse
from django.db.models import Sum, Count
from django.conf import settings
from challenge.models import Sandbox, Challenge, Submission
from notifications.models import Notification
from services.firewall_service import get_firewall_service
from collections import defaultdict
from django.http import HttpRequest, HttpResponse
from typing import Mapping, cast, Any

logger = logging.getLogger(__name__)


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


def send_confirmation_email(user_email: str) -> None:
    token = generate_confirmation_token(user_email)
    server_name = getattr(settings, "SERVER_NAME", "localhost:8080")
    protocol = "https" if getattr(settings, "SESSION_COOKIE_SECURE", False) else "http"
    confirm_url = f"{protocol}://{server_name}{reverse('confirm_email', args=[token])}"

    html_message = f'<p>Please confirm your email by clicking <a href="{confirm_url}">here</a>.</p>'
    subject = "Please confirm your email"

    send_mail(
        subject=subject,
        message=f"Please confirm your email by visiting: {confirm_url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        html_message=html_message,
        fail_silently=False,
    )


@require_http_methods(["GET"])
def home(request: HttpRequest) -> HttpResponse:
    user = request.user

    if not user.is_authenticated:
        return render(request, "user_auth/home.html", {"user": None})

    active_challenges = list(Challenge.objects.filter(active=True))
    challenge_ids = [c.id for c in active_challenges]

    challenges_by_category = defaultdict(list)
    challenge_solves = {}

    solve_counts = (
        Submission.objects.filter(challenge_id__in=challenge_ids, correct=True)
        .values("challenge_id")
        .annotate(count=Count("id"))
    )
    solve_counts_dict = {item["challenge_id"]: item["count"] for item in solve_counts}

    for challenge in active_challenges:
        challenge_solves[challenge.name] = solve_counts_dict.get(challenge.id, 0)
        challenges_by_category[challenge.category].append(challenge)

    successful_challenge_ids = set(
        Submission.objects.filter(
            user_id=user.id, challenge__active=True, correct=True
        ).values_list("challenge_id", flat=True)
    )

    submissions = {
        challenge.id: challenge.id in successful_challenge_ids
        for challenge in active_challenges
    }
    correct_submissions = dict(submissions)

    result = Submission.objects.filter(
        user_id=user.id, challenge__active=True, correct=True
    ).aggregate(total=Sum("challenge__points"))
    user_score = result["total"] or 0

    total_score = (
        Challenge.objects.filter(active=True).aggregate(total=Sum("points"))["total"]
        or 0
    )

    unread_notifications = list(
        Notification.objects.filter(user_id=user.id, is_read=False)
    )

    user_sandboxes = (
        Sandbox.objects.filter(user=user, active=True).select_related("challenge").all()
    )

    static_challenges = [c for c in active_challenges if c.static]
    static_sandboxes = {}
    if static_challenges:
        static_challenge_ids = [c.id for c in static_challenges]
        static_sandbox_objs = (
            Sandbox.objects.filter(challenge_id__in=static_challenge_ids, active=True)
            .select_related("challenge")
            .all()
        )
        for sandbox in static_sandbox_objs:
            static_sandboxes[sandbox.challenge_id] = {
                "has_sandbox": True,
                "port": sandbox.container_port,
                "static": True,
            }

    sandboxes_dict = {}
    for sandbox in user_sandboxes:
        sandboxes_dict[sandbox.challenge_id] = {
            "has_sandbox": True,
            "port": sandbox.container_port,
            "static": sandbox.challenge.static,
        }

    sandboxes_dict.update(static_sandboxes)
    active_sandboxes = sandboxes_dict

    context: Mapping[str, Any] = {
        "user": user,
        "challenges_by_category": dict(challenges_by_category),
        "correct_submissions": correct_submissions,
        "score": user_score,
        "total_score": total_score,
        "challenge_solves": challenge_solves,
        "unread_notifications": unread_notifications,
        "active_sandboxes": active_sandboxes,
    }
    return render(request, "user_auth/home.html", context)


@require_http_methods(["GET", "POST"])
@rate_limit("3/h", method="POST")
def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        errors = {}

        if not username or len(username) < 4 or len(username) > 25:
            errors["username"] = ["Username must be between 4 and 25 characters"]

        if not email:
            errors["email"] = ["Email is required"]

        if not password or len(password) < 6:
            errors["password"] = ["Password must be at least 6 characters"]

        if password != confirm_password:
            errors["confirm_password"] = ["Passwords must match"]

        if errors:
            context = {"errors": errors, "username": username, "email": email}
            return render(request, "user_auth/register.html", context)

        try:
            User.objects.get(username=username)
            errors["username"] = [
                "This username is already taken. Please choose another."
            ]
            context = {"errors": errors, "username": username, "email": email}
            return render(request, "user_auth/register.html", context)
        except User.DoesNotExist:
            pass

        try:
            User.objects.get(email=email)
            errors["email"] = [
                "This email is already registered. Please choose another."
            ]
            context = {"errors": errors, "username": username, "email": email}
            return render(request, "user_auth/register.html", context)
        except User.DoesNotExist:
            pass

        try:
            with transaction.atomic():
                user = User(
                    username=username,
                    email=email,
                    verified=False,
                    is_admin=False,
                    banned=False,
                )
                user.set_password(password)
                user.save()

            send_confirmation_email(user.email)

            messages.success(
                request,
                "Registration successful! Check your inbox and verify your email to log in.",
            )
            return redirect("login")
        except Exception:
            logger.error("Failed to create user", exc_info=True)
            errors["general"] = ["Failed to create user"]
            context = {"errors": errors, "username": username, "email": email}
            return render(request, "user_auth/register.html", context)

    return render(request, "user_auth/register.html")


@require_http_methods(["GET", "POST"])
@rate_limit("5/m", method="POST")
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            messages.error(request, "Username and password are required")
            return render(request, "user_auth/login.html")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, "Invalid username or password.")
            return render(request, "user_auth/login.html")

        if not user.check_password(password):
            messages.error(request, "Invalid username or password.")
            return render(request, "user_auth/login.html")

        if not user.verified:
            messages.error(request, "Verify your email!")
            return render(request, "user_auth/login.html")

        if user.banned:
            messages.error(request, "You have been banned. Contact admins.")
            return render(request, "user_auth/login.html")

        client_ip = get_client_ip(request)

        existing_session = UserSession.objects.filter(user=user, active=True).first()
        old_ip = existing_session.ip_address if existing_session else None

        with transaction.atomic():
            UserSession.objects.filter(user=user, active=True).update(active=False)

            expires_at = timezone.now() + timedelta(seconds=86400)
            session = UserSession(
                user=user,
                ip_address=client_ip,
                session_token="",
                expires_at=expires_at,
                active=True,
            )
            session.save()

        try:
            firewall_service = get_firewall_service()
            firewall_service.initialize_firewall()

            active_sandboxes = list(
                Sandbox.objects.filter(user=user, active=True).select_related(
                    "challenge"
                )
            )

            if old_ip and old_ip != client_ip:
                for sandbox in active_sandboxes:
                    if not sandbox.challenge.static:
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

            for sandbox in active_sandboxes:
                if not sandbox.challenge.static:
                    firewall_service.add_port_ip_mapping(
                        sandbox.container_port, client_ip
                    )
                    if sandbox.port_mappings:
                        for port in sandbox.port_mappings.values():
                            if isinstance(port, (int, str)):
                                try:
                                    port_int = int(port)
                                    firewall_service.add_port_ip_mapping(
                                        port_int, client_ip
                                    )
                                except (ValueError, TypeError):
                                    pass
        except Exception:
            logger.error("Failed to set up firewall rules during login", exc_info=True)

        login(request, user)

        messages.success(request, "Login successful.")
        return redirect("home")

    return render(request, "user_auth/login.html")


@require_http_methods(["GET", "POST"])
@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    user = cast(User, request.user)
    client_ip = get_client_ip(request)

    user_session = UserSession.objects.filter(
        user=user, ip_address=client_ip, active=True
    ).first()

    if user_session:
        try:
            firewall_service = get_firewall_service()
            firewall_service.initialize_firewall()

            active_sandboxes = list(
                Sandbox.objects.filter(user=user, active=True).select_related(
                    "challenge"
                )
            )

            for sandbox in active_sandboxes:
                if sandbox.challenge.static:
                    continue

                firewall_service.remove_port_ip_mapping(
                    sandbox.container_port, client_ip
                )

                if sandbox.port_mappings:
                    for port in sandbox.port_mappings.values():
                        if isinstance(port, (int, str)):
                            try:
                                port_int = int(port)
                                firewall_service.remove_port_ip_mapping(
                                    port_int, client_ip
                                )
                            except (ValueError, TypeError):
                                pass
        except Exception:
            logger.error(
                "Failed to remove firewall rules during logout",
                exc_info=True,
            )

        user_session.active = False
        user_session.save()

    django_logout(request)

    return redirect("home")


@require_http_methods(["GET"])
def confirm_email_view(request: HttpRequest, token: str) -> HttpResponse:
    email = confirm_token(token)

    if email:
        try:
            user = User.objects.get(email=email)
            user.verified = True
            user.save()
            messages.success(request, "Your email has been confirmed!")
        except User.DoesNotExist:
            messages.error(request, "Invalid email")
    else:
        messages.error(request, "The confirmation link is invalid or has expired.")

    return redirect("home")
