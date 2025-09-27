from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse, HttpRequest, HttpResponse
import json
import time
import logging

from .models import Notification
from challenge.utils import get_redis_client
from typing import Generator

logger = logging.getLogger(__name__)


@login_required
def notifications_view(request: HttpRequest) -> HttpResponse:
    user = request.user

    notifications_list = list(
        Notification.objects.filter(user_id=user.id).order_by("-created_at")  # type: ignore
    )

    context = {
        "title": "Notifications",
        "notifications": notifications_list,
    }
    return render(request, "notifications/notifications.html", context)


def publish_notification(user_id: int, message: str) -> None:
    try:
        redis_client = get_redis_client()
        channel = f"notifications:{user_id}"
        data = json.dumps({"message": message, "user_id": user_id})
        redis_client.publish(channel, data)
    except Exception:
        logger.error("Error publishing notification", exc_info=True)


@login_required
def stream_view(request: HttpRequest, channel: str) -> StreamingHttpResponse:
    user = request.user

    try:
        channel_id = int(channel)
        if channel_id != user.id:
            return StreamingHttpResponse("", status=403)
    except ValueError:
        return StreamingHttpResponse("", status=400)

    def event_stream() -> Generator[str, None, None]:
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        redis_client = get_redis_client()
        pubsub = redis_client.pubsub()  # type: ignore
        pubsub_channel = f"notifications:{channel_id}"
        pubsub.subscribe(pubsub_channel)

        try:
            last_heartbeat = time.time()
            heartbeat_interval = 30

            while True:
                message = pubsub.get_message(
                    timeout=1.0, ignore_subscribe_messages=True
                )

                if message:
                    try:
                        data = json.loads(message["data"])
                        yield f"event: notification\ndata: {json.dumps(data)}\n\n"
                    except (json.JSONDecodeError, KeyError):
                        logger.error(
                            "Error parsing notification message", exc_info=True
                        )

                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield "event: heartbeat\n\n"
                    last_heartbeat = current_time

        except GeneratorExit:
            pass
        except Exception:
            logger.error("Error in event stream", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Error in event stream'})}\n\n"
        finally:
            pubsub.unsubscribe(pubsub_channel)
            pubsub.close()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
