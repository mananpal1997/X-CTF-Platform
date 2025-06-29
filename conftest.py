import pytest
from typing import List
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from challenge.models import Challenge, Sandbox, Submission
from user_auth.models import UserSession

User = get_user_model()


@pytest.fixture(autouse=True)
def configure_email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def disable_rate_limiting(settings):
    settings.DISABLE_RATE_LIMITING = True


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def user(db) -> User:
    user, _ = User.objects.get_or_create(
        username="testuser",
        defaults={
            "email": "test@example.com",
            "verified": True,
            "is_active": True,
        },
    )
    if not user.has_usable_password():
        user.set_password("testpass123")
        user.save()
    return user


@pytest.fixture
def admin_user(db) -> User:
    user, _ = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@example.com",
            "verified": True,
            "is_admin": True,
            "is_active": True,
        },
    )
    if not user.has_usable_password():
        user.set_password("adminpass123")
        user.save()
    return user


@pytest.fixture
def challenge(db) -> Challenge:
    return Challenge.objects.create(
        name="Test Challenge",
        category="Web",
        points=100,
        flag="FLAG{test}",
        static=False,
        active=True,
    )


@pytest.fixture
def static_challenge(db) -> Challenge:
    return Challenge.objects.create(
        name="Static Challenge",
        category="Web",
        points=50,
        flag="FLAG{static}",
        static=True,
        active=True,
    )


@pytest.fixture
def sandbox(db, user, challenge) -> Sandbox:
    return Sandbox.objects.create(
        user=user,
        challenge=challenge,
        container_id="test-container-id",
        container_port=8000,
        active=True,
        port_mappings={},
    )


@pytest.fixture
def submission(db, user, challenge) -> Submission:
    return Submission.objects.create(
        user=user,
        challenge=challenge,
        correct=True,
    )


@pytest.fixture
def logged_in_client(client, user, db) -> Client:
    client.force_login(user)
    expires_at = timezone.now() + timedelta(seconds=86400)
    UserSession.objects.create(
        user=user,
        ip_address="127.0.0.1",
        session_token="",
        expires_at=expires_at,
        active=True,
    )
    return client


@pytest.fixture
def user_session(db, user) -> UserSession:
    expires_at = timezone.now() + timedelta(seconds=86400)
    return UserSession.objects.create(
        user=user,
        ip_address="127.0.0.1",
        session_token="",
        expires_at=expires_at,
        active=True,
    )


@pytest.fixture
def challenges(db) -> List[Challenge]:
    return [
        Challenge.objects.create(
            name="Test Challenge",
            category="Misc",
            points=50,
            flag="FLAG{test}",
            static=True,
            active=True,
        ),
        Challenge.objects.create(
            name="Test Challenge 2",
            category="Web",
            points=50,
            flag="FLAG{test}",
            static=False,
            active=True,
        ),
        Challenge.objects.create(
            name="Test Challenge 3",
            category="Web",
            points=100,
            flag="FLAG{test}",
            static=False,
            active=True,
        ),
        Challenge.objects.create(
            name="Test Challenge 4",
            category="Web",
            points=200,
            flag="FLAG{test}",
            static=False,
            active=True,
        ),
    ]


@pytest.fixture
def user_submissions(db, user, challenges) -> List[Submission]:
    return [
        Submission.objects.create(
            user=user,
            challenge=challenges[0],
            correct=False,
        ),
        Submission.objects.create(
            user=user,
            challenge=challenges[1],
            correct=False,
        ),
        Submission.objects.create(
            user=user,
            challenge=challenges[2],
            correct=True,
        ),
    ]


@pytest.fixture
def active_user_sandboxes(db, user, challenges) -> List[Sandbox]:
    return [
        Sandbox.objects.create(
            user=user,
            challenge=challenges[0],
            container_id="test-container-id",
            container_port=8000,
            active=True,
        ),
        Sandbox.objects.create(
            user=user,
            challenge=challenges[1],
            container_id="test-container-id",
            container_port=8000,
            active=True,
        ),
    ]
