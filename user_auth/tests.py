import pytest
from django.http import HttpRequest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from user_auth.models import UserSession
from user_auth.views import get_client_ip

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create(
            username="testuser",
            email="test@example.com",
        )
        assert user.is_admin is False
        assert user.verified is False

    def test_create_admin_user(self):
        user = User.objects.create(
            username="admin",
            email="admin@example.com",
            is_admin=True,
            verified=True,
        )
        user.set_password("adminpass123")
        user.save()
        assert user.is_admin is True
        assert user.verified is True

    def test_user_str(self):
        user = User.objects.create(
            username="testuser",
            email="test@example.com",
        )
        assert str(user) == "testuser"

    def test_user_password_hashing(self):
        user = User.objects.create(
            username="testuser",
            email="test@example.com",
        )
        user.set_password("testpass123")
        user.save()
        assert user.check_password("testpass123")
        assert not user.check_password("wrongpassword")


@pytest.mark.django_db
class TestUserSessionModel:
    def test_create_session(self, user):
        expires_at = timezone.now() + timedelta(seconds=86400)
        session = UserSession.objects.create(
            user=user,
            ip_address="127.0.0.1",
            session_token="test-token",
            expires_at=expires_at,
            active=True,
        )
        assert session.user == user
        assert session.ip_address == "127.0.0.1"
        assert session.active is True

    def test_session_expiration(self, user):
        expires_at = timezone.now() - timedelta(seconds=1)
        session = UserSession.objects.create(
            user=user,
            ip_address="127.0.0.1",
            session_token="test-token",
            expires_at=expires_at,
            active=True,
        )
        assert session.expires_at < timezone.now()

        expires_at = timezone.now() + timedelta(seconds=86400)
        session.expires_at = expires_at
        session.save()
        assert session.expires_at > timezone.now()


@pytest.mark.django_db
class TestHomeView:
    def test_home_view_unauthenticated(self, client):
        url = reverse("home")
        response = client.get(url)
        assert response.status_code == 200
        assert (
            '<a class="nav-link" href="/register/">Register</a>'
            in response.content.decode()
        )

    def test_home_view_authenticated(self, logged_in_client):
        url = reverse("home")
        response = logged_in_client.get(url)
        assert response.status_code == 200
        assert (
            '<a class="nav-link" href="/register/">Register</a>'
            not in response.content.decode()
        )


@pytest.mark.django_db
class TestRegistrationView:
    def test_registration_get(self, client):
        url = reverse("register")
        response = client.get(url)
        assert response.status_code == 200

    def test_registration_post_valid(self, client, mailoutbox):
        url = reverse("register")
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepass123",
            "confirm_password": "securepass123",
        }
        response = client.post(url, data)
        assert (
            response.status_code == 302
        ), f"Expected 302 redirect, got {response.status_code}"

        user_exists = User.objects.filter(username="newuser").exists()
        assert user_exists, "User was not created"

        assert len(mailoutbox) == 1, f"Expected 1 email, got {len(mailoutbox)}"
        assert mailoutbox[0].to == ["newuser@example.com"]
        assert (
            "confirm" in mailoutbox[0].subject.lower()
        ), f"User 'newuser' was not created. Mailoutbox has {len(mailoutbox)} emails"

    def test_registration_duplicate_username(self, client, user):
        url = reverse("register")
        data = {
            "username": user.username,
            "email": "different@example.com",
            "password": "securepass123",
            "confirm_password": "securepass123",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        assert User.objects.filter(email="different@example.com").count() == 0

    def test_registration_password_mismatch(self, client):
        url = reverse("register")
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepass123",
            "confirm_password": "differentpass",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        assert User.objects.filter(username="newuser").count() == 0


@pytest.mark.django_db
class TestLoginView:
    def test_login_get(self, client):
        url = reverse("login")
        response = client.get(url)
        assert response.status_code == 200

    def test_login_post_valid(self, client, user):
        url = reverse("login")
        data = {
            "username": user.username,
            "password": "testpass123",
        }
        response = client.post(url, data, follow=True)
        assert response.status_code == 200

    def test_login_post_invalid(self, client, user):
        url = reverse("login")
        data = {
            "username": user.username,
            "password": "wrongpassword",
        }
        response = client.post(url, data)
        assert response.status_code == 200


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_authenticated(self, logged_in_client):
        url = reverse("logout")
        response = logged_in_client.post(url)
        assert response.status_code == 302

    def test_logout_unauthenticated(self, client):
        url = reverse("logout")
        response = client.post(url)
        assert response.status_code == 302


class TestGetClientIp:
    def test_get_client_ip_with_no_ips(self):
        request = HttpRequest()
        ip = get_client_ip(request)
        assert ip == "0.0.0.0"

    def test_get_client_ip_with_x_forwarded_for(self):
        request = HttpRequest()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "127.0.0.1, 192.168.1.1",
        }
        ip = get_client_ip(request)
        assert ip == "127.0.0.1"

    def test_get_client_ip_with_x_real_ip(self):
        request = HttpRequest()
        request.META = {
            "HTTP_X_REAL_IP": "127.0.0.1",
        }
        ip = get_client_ip(request)
        assert ip == "127.0.0.1"

    def test_get_client_ip_with_remote_addr(self):
        request = HttpRequest()
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
        }
        ip = get_client_ip(request)
        assert ip == "127.0.0.1"

    def test_get_client_ip_with_multiple_ips(self):
        request = HttpRequest()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "192.168.1.1,127.0.0.1",
            "HTTP_X_REAL_IP": "127.0.0.1",
            "REMOTE_ADDR": "127.0.0.1",
        }
        ip = get_client_ip(request)
        assert ip == "192.168.1.1"
