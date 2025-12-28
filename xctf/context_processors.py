from django.conf import settings
from django.http import HttpRequest
from typing import Dict


def github_repo(request: HttpRequest) -> Dict[str, str]:
    return {"GITHUB_REPO": settings.GITHUB_REPO}
