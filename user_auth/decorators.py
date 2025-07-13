from functools import wraps
from django.http import HttpRequest, HttpResponse
from typing import Callable, Any, ParamSpec, TypeVar, Concatenate
from django_ratelimit.decorators import ratelimit
from django.conf import settings

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)


def get_rate_limit_key_fn(group: str, request: HttpRequest) -> str:
    if hasattr(request, "user") and request.user.is_authenticated:
        return f"user:{request.user.id}"
    x_forwarded_for: str = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        return f"ip:{x_forwarded_for.split(',')[0]}"
    else:
        return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"


def rate_limit(rate: str, method: str = "POST", block: bool = True) -> Callable[
    [Callable[Concatenate[HttpRequest, P], R]],
    Callable[Concatenate[HttpRequest, P], R],
]:
    def decorator(
        view_func: Callable[Concatenate[HttpRequest, P], R],
    ) -> Callable[Concatenate[HttpRequest, P], R]:
        ratelimited_func = ratelimit(
            key=get_rate_limit_key_fn, rate=rate, method=method, block=block
        )(view_func)

        @wraps(view_func)
        def sync_wrapper(request: HttpRequest, /, *args: Any, **kwargs: Any) -> Any:
            if settings.DISABLE_RATE_LIMITING:
                return view_func(request, *args, **kwargs)
            return ratelimited_func(request, *args, **kwargs)

        return sync_wrapper

    return decorator
