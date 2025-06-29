import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "xctf.settings")

app = Celery("xctf")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

app.conf.beat_schedule = {
    "kill-completed-sandbox-containers-every-minute": {
        "task": "tasks.tasks.destroy_non_static_sandboxes",
        "schedule": crontab(minute="*/1"),
    },
    "cleanup-expired-sessions-every-5-minutes": {
        "task": "tasks.tasks.cleanup_expired_sessions",
        "schedule": crontab(minute="*/5"),
    },
    "clean-orphan-firewall-ports-every-10-minutes": {
        "task": "tasks.tasks.clean_orphan_firewall_ports",
        "schedule": crontab(minute="*/10"),
    },
}

app.conf.timezone = "UTC"


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # type: ignore
    print(f"Request: {self.request!r}")
