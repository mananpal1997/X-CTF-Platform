import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from challenge.models import Challenge
from tasks.tasks import send_notification, refresh_sandboxes


def validate_metadata(metadata):
    required_fields = ["NAME", "POINTS", "FLAG", "STATIC", "ACTIVE", "CATEGORY"]
    for field in required_fields:
        if field not in metadata:
            return False, f"Missing required field: {field}"
    return True, None


class Command(BaseCommand):
    help = "Setup docker images of challenges and create objects in database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed output",
        )
        parser.add_argument(
            "--challenge-name",
            type=str,
            default="",
            help="Process only a specific challenge",
        )
        parser.add_argument(
            "--skip-docker",
            action="store_true",
            help="Skip Docker image building (only update database)",
        )
        parser.add_argument(
            "--challenges-dir",
            type=str,
            default=settings.CHALLENGES_DIRECTORY,
            help="Path to challenges directory",
        )

    def handle(self, *args, **options):
        verbose = options["verbose"]
        challenge_name = options["challenge_name"]
        skip_docker = options["skip_docker"]
        challenges_directory = options["challenges_dir"]

        if not os.path.exists(challenges_directory):
            self.stdout.write(
                self.style.ERROR(
                    f"Challenges directory not found: {challenges_directory}"
                )
            )
            return

        docker_client = None
        if not skip_docker:
            try:
                import docker

                docker_client = docker.from_env()
            except ImportError:
                self.stdout.write(
                    self.style.WARNING(
                        "docker library not installed. Use --skip-docker to skip Docker operations."
                    )
                )
                return
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not connect to Docker: {e}. Use --skip-docker to skip Docker operations."
                    )
                )
                return

        for challenge_dir_name in os.listdir(challenges_directory):
            if challenge_name and challenge_dir_name != challenge_name:
                continue

            challenge_directory = os.path.join(challenges_directory, challenge_dir_name)
            if not os.path.isdir(challenge_directory):
                continue

            metadata_file = os.path.join(challenge_directory, "metadata.json")
            if not os.path.exists(metadata_file):
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(
                            f"metadata.json missing for {challenge_dir_name}"
                        )
                    )
                continue

            try:
                with open(metadata_file) as f:
                    challenge_metadata = json.load(f)
            except Exception as err:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error parsing metadata.json for {challenge_dir_name}: {err}"
                    )
                )
                continue

            is_valid, error_msg = validate_metadata(challenge_metadata)
            if not is_valid:
                self.stdout.write(
                    self.style.ERROR(
                        f"metadata.json for {challenge_dir_name} is invalid: {error_msg}"
                    )
                )
                continue

            image_tag = None
            image_changed = False
            if not skip_docker:
                challenge_dockerfile = os.path.join(challenge_directory, "Dockerfile")
                if not os.path.exists(challenge_dockerfile):
                    if verbose:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Dockerfile missing for {challenge_dir_name}"
                            )
                        )
                    continue

                self.stdout.write(f"Building docker image for {challenge_dir_name}...")
                try:
                    image_tag = (
                        f"xctf-{challenge_metadata['CATEGORY']}:{challenge_dir_name}"
                    )
                    image, build_logs = docker_client.images.build(
                        path=challenge_directory,
                        tag=image_tag,
                        buildargs={
                            "CHALLENGE_NAME": challenge_metadata["NAME"],
                            "FLAG_VALUE": challenge_metadata["FLAG"],
                        },
                    )
                    for log in build_logs:
                        if verbose:
                            self.stdout.write(log.get("stream", "").strip())
                        if "stream" in log:
                            log_line = log["stream"].strip()
                            if "Using cache" not in log_line:
                                image_changed = True
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully built image for {challenge_dir_name} with tags {image.tags}"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error building image for {challenge_dir_name}: {e}"
                        )
                    )
                    continue
            else:
                image_tag = (
                    f"xctf-{challenge_metadata['CATEGORY']}:{challenge_dir_name}"
                )

            try:
                challenge_obj = Challenge.objects.filter(
                    name=challenge_metadata["NAME"]
                ).first()

                if challenge_obj is None:
                    self.stdout.write(
                        f"Creating database entry for {challenge_dir_name}..."
                    )
                    challenge_obj = Challenge(
                        name=challenge_metadata["NAME"],
                        points=challenge_metadata["POINTS"],
                        category=challenge_metadata["CATEGORY"],
                        static=challenge_metadata["STATIC"],
                        active=challenge_metadata["ACTIVE"],
                        flag=challenge_metadata["FLAG"],
                        image_tag=image_tag,
                        tcp_ports=challenge_metadata.get("TCP_PORTS"),
                        metadata_filepath=metadata_file,
                    )
                    challenge_obj.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully created database entry for {challenge_dir_name}"
                        )
                    )
                    send_notification.delay(
                        f"Challenge {challenge_metadata['NAME']} has been created.",
                        to_all=True,
                    )
                else:
                    self.stdout.write(
                        f"Updating database entry for {challenge_dir_name}..."
                    )

                    changes = []
                    if challenge_obj.points != challenge_metadata["POINTS"]:
                        changes.append(
                            f"points changed from {challenge_obj.points} to {challenge_metadata['POINTS']}"
                        )
                    if challenge_obj.flag != challenge_metadata["FLAG"]:
                        changes.append("flag has been updated")
                    if (
                        challenge_metadata["ACTIVE"] is True
                        and challenge_obj.active is False
                    ):
                        changes.append("status changed from inactive to active")
                    elif (
                        challenge_metadata["ACTIVE"] is False
                        and challenge_obj.active is True
                    ):
                        changes.append("status changed from active to inactive")

                    challenge_obj.points = challenge_metadata["POINTS"]
                    challenge_obj.category = challenge_metadata["CATEGORY"]
                    challenge_obj.static = challenge_metadata["STATIC"]
                    challenge_obj.active = challenge_metadata["ACTIVE"]
                    challenge_obj.flag = challenge_metadata["FLAG"]
                    challenge_obj.image_tag = image_tag
                    challenge_obj.tcp_ports = challenge_metadata.get("TCP_PORTS")
                    challenge_obj.metadata_filepath = metadata_file
                    challenge_obj.save()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully updated database entry for {challenge_dir_name}"
                        )
                    )
                    if changes and verbose:
                        for change in changes:
                            self.stdout.write(f"  - {change}")
                    if changes or image_changed:
                        send_notification.delay(
                            f"Challenge {challenge_metadata['NAME']} has been updated.",
                            to_all=True,
                        )
                        refresh_sandboxes.delay(challenge_metadata["NAME"])

            except Exception as err:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error saving database entry for {challenge_dir_name}: {err}"
                    )
                )

        self.stdout.write(self.style.SUCCESS("Challenge setup completed!"))
