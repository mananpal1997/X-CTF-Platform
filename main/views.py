import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.db.models import Sum, Max, Q
from django.db.models.functions import Coalesce
from django.db import connection
from django.contrib.auth.decorators import login_required
from user_auth.models import User
from challenge.utils import get_redis_client

logger = logging.getLogger(__name__)


def health_check(request: HttpRequest) -> JsonResponse:
    checks = {
        "status": "ok",
        "database": False,
        "redis": False,
    }
    status_code = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = True
    except Exception:
        logger.error("Error checking database", exc_info=True)
        checks["database"] = False
        checks["status"] = "degraded"
        status_code = 503

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        checks["redis"] = True
    except Exception:
        logger.error("Error checking Redis", exc_info=True)
        checks["redis"] = False
        checks["status"] = "degraded"
        status_code = 503

    if not all([checks["database"], checks["redis"]]):
        status_code = 503

    return JsonResponse(checks, status=status_code)


@login_required
def scoreboard_view(request: HttpRequest) -> HttpResponse:
    users_list = list(
        User.objects.annotate(
            total_score=Coalesce(
                Sum(
                    "submission__challenge__points",
                    filter=Q(
                        submission__correct=True, submission__challenge__active=True
                    ),
                ),
                0,
            ),
            latest_submission=Max(
                "submission__submitted_at",
                filter=Q(submission__correct=True, submission__challenge__active=True),
            ),
        )
        .order_by("-total_score", "latest_submission")
        .values("username", "banned", "total_score", "latest_submission")
    )

    scores = [
        (user["username"], user["banned"], int(user["total_score"] or 0))
        for user in users_list
    ]

    context = {
        "title": "Scoreboard",
        "scores": scores,
    }
    return render(request, "main/scoreboard.html", context)
