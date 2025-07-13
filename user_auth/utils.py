from itsdangerous import URLSafeTimedSerializer
from django.conf import settings
from typing import Optional


def generate_confirmation_token(email: str) -> str:
    if settings.SECRET_KEY is None:
        raise ValueError("SECRET_KEY is not set")
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    return serializer.dumps(email, salt="email-confirm-salt")


def confirm_token(token: str, expiration: int = 3600) -> Optional[str]:
    if settings.SECRET_KEY is None:
        raise ValueError("SECRET_KEY is not set")
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        email: str = serializer.loads(
            token, salt="email-confirm-salt", max_age=expiration
        )
        return email
    except Exception:
        return None
