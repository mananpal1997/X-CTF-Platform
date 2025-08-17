import pytest
from unittest.mock import Mock, patch
from django.test import RequestFactory
from challenge.models import Challenge, Submission
from services.challenge_service import ChallengeService
from services.docker_service import DockerService
from services.firewall_service import FirewallService, get_firewall_service


@pytest.mark.django_db
class TestChallengeService:
    @pytest.fixture
    def challenge_service(self):
        return ChallengeService()

    @pytest.fixture
    def challenge(self, db):
        return Challenge.objects.create(
            name="Test Challenge",
            category="Web",
            points=100,
            flag="FLAG{test123}",
            static=False,
            active=True,
        )

    @pytest.fixture
    def static_challenge(self, db):
        return Challenge.objects.create(
            name="Static Challenge",
            category="Crypto",
            points=200,
            flag="FLAG{static}",
            static=True,
            active=True,
        )

    def test_submit_flag_correct(self, challenge_service, challenge, user):
        success, message = challenge_service.submit_flag(
            user.id, challenge.id, "FLAG{test123}"
        )
        assert success is True
        assert message == "correct flag"

        submission = Submission.objects.get(user_id=user.id, challenge_id=challenge.id)
        assert submission.correct is True

    def test_submit_flag_incorrect(self, challenge_service, challenge, user):
        success, message = challenge_service.submit_flag(
            user.id, challenge.id, "FLAG{wrong}"
        )
        assert success is False
        assert message == "incorrect flag"

        submission = Submission.objects.get(user_id=user.id, challenge_id=challenge.id)
        assert submission.correct is False

    def test_submit_flag_challenge_not_found(self, challenge_service, user):
        success, message = challenge_service.submit_flag(user.id, 99999, "FLAG{test}")
        assert success is False
        assert message == "Challenge not found"

    def test_submit_flag_already_solved(self, challenge_service, challenge, user):
        Submission.objects.create(user=user, challenge=challenge, correct=True)

        success, message = challenge_service.submit_flag(
            user.id, challenge.id, "FLAG{test123}"
        )
        assert success is False
        assert message == "You have already solved this challenge."

    def test_submit_flag_with_whitespace(self, challenge_service, challenge, user):
        success, message = challenge_service.submit_flag(
            user.id, challenge.id, "  FLAG{test123}  "
        )
        assert success is True
        assert message == "correct flag"

    def test_check_user_solved_challenge_true(self, challenge_service, challenge, user):
        Submission.objects.create(user=user, challenge=challenge, correct=True)

        result = challenge_service.check_user_solved_challenge(user.id, challenge.id)
        assert result is True

    def test_check_user_solved_challenge_false(
        self, challenge_service, challenge, user
    ):
        result = challenge_service.check_user_solved_challenge(user.id, challenge.id)
        assert result is False

    def test_check_user_solved_challenge_no_user_id(self, challenge_service, challenge):
        result = challenge_service.check_user_solved_challenge(None, challenge.id)
        assert result is False

    def test_check_user_solved_challenge_incorrect_submission(
        self, challenge_service, challenge, user
    ):
        Submission.objects.create(user=user, challenge=challenge, correct=False)

        result = challenge_service.check_user_solved_challenge(user.id, challenge.id)
        assert result is False


@pytest.mark.django_db
class TestDockerService:
    @pytest.fixture
    def docker_service(self):
        return DockerService()

    @pytest.fixture
    def mock_container(self):
        container = Mock()
        container.id = "test-container-id"
        container.name = "test-container"
        container.ports = {"8000/tcp": [{"HostPort": "32768"}]}
        container.reload = Mock()
        container.stop = Mock()
        container.remove = Mock()
        return container

    @pytest.fixture
    def mock_docker_client(self, mock_container):
        client = Mock()
        containers = Mock()
        containers.run = Mock(return_value=mock_container)
        containers.get = Mock(return_value=mock_container)
        containers.list = Mock(return_value=[mock_container])
        client.containers = containers
        return client

    def test_create_container_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        docker_service._client = mock_docker_client
        container = docker_service.create_container(
            image="test-image:latest",
            name="test-container",
            ports={"8000/tcp": None},
        )
        assert container.id == "test-container-id"
        mock_docker_client.containers.run.assert_called_once()
        mock_container.reload.assert_called_once()

    def test_create_container_image_not_found(self, docker_service, mock_docker_client):
        import docker.errors

        mock_docker_client.containers.run.side_effect = docker.errors.ImageNotFound(
            "Image not found"
        )

        docker_service._client = mock_docker_client
        with pytest.raises(docker.errors.ImageNotFound):
            docker_service.create_container(
                image="nonexistent-image:latest",
                name="test-container",
            )

    def test_get_container_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        docker_service._client = mock_docker_client
        container = docker_service.get_container("test-container-id")
        assert container.id == "test-container-id"
        mock_docker_client.containers.get.assert_called_once_with("test-container-id")

    def test_get_container_not_found(self, docker_service, mock_docker_client):
        import docker.errors

        mock_docker_client.containers.get.side_effect = docker.errors.NotFound(
            "Container not found"
        )

        docker_service._client = mock_docker_client
        with pytest.raises(docker.errors.NotFound):
            docker_service.get_container("nonexistent-id")

    def test_stop_container_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        docker_service._client = mock_docker_client
        result = docker_service.stop_container("test-container-id")
        assert result is True
        mock_container.stop.assert_called_once()

    def test_stop_container_not_found(self, docker_service, mock_docker_client):
        import docker.errors

        mock_docker_client.containers.get.side_effect = docker.errors.NotFound(
            "Container not found"
        )

        docker_service._client = mock_docker_client
        result = docker_service.stop_container("nonexistent-id")
        assert result is False

    def test_remove_container_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        docker_service._client = mock_docker_client
        result = docker_service.remove_container("test-container-id", force=True)
        assert result is True
        mock_container.remove.assert_called_once_with(force=True)

    def test_stop_and_remove_container_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        docker_service._client = mock_docker_client
        result = docker_service.stop_and_remove_container("test-container-id")
        assert result is True
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    def test_list_containers(self, docker_service, mock_docker_client, mock_container):
        docker_service._client = mock_docker_client
        containers = docker_service.list_containers(all=True, filters={"label": "test"})
        assert len(containers) == 1
        assert containers[0].id == "test-container-id"
        mock_docker_client.containers.list.assert_called_once_with(
            all=True, filters={"label": "test"}
        )

    def test_get_container_health(
        self, docker_service, mock_docker_client, mock_container
    ):
        mock_container.health = "healthy"
        docker_service._client = mock_docker_client
        health = docker_service.get_container_health("test-container-id")
        assert health == "healthy"
        mock_container.reload.assert_called_once()

    def test_get_container_health_none(
        self, docker_service, mock_docker_client, mock_container
    ):
        del mock_container.health
        docker_service._client = mock_docker_client
        health = docker_service.get_container_health("test-container-id")
        assert health is None

    def test_wait_for_healthy_success(
        self, docker_service, mock_docker_client, mock_container
    ):
        mock_container.health = "healthy"
        docker_service._client = mock_docker_client
        with patch("time.sleep"):
            result = docker_service.wait_for_healthy("test-container-id", timeout=60)
            assert result is True

    def test_wait_for_healthy_timeout(
        self, docker_service, mock_docker_client, mock_container
    ):
        mock_container.health = None
        docker_service._client = mock_docker_client
        with patch("time.sleep"):
            with patch("time.perf_counter", side_effect=[0, 61]):
                result = docker_service.wait_for_healthy(
                    "test-container-id", timeout=60
                )
                assert result is False


@pytest.mark.django_db
class TestFirewallService:
    @pytest.fixture
    def firewall_service(self):
        service = FirewallService()
        service._initialized = False
        return service

    @pytest.fixture
    def mock_subprocess_success(self):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        return mock_result

    @pytest.fixture
    def mock_subprocess_failure(self):
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error message"
        return mock_result

    def test_run_nftables_command_success(
        self, firewall_service, mock_subprocess_success
    ):
        with patch("subprocess.run", return_value=mock_subprocess_success):
            success, output = firewall_service._run_nftables_command(
                "list table inet xctf"
            )
            assert success is True
            assert output == "success"

    def test_run_nftables_command_failure(
        self, firewall_service, mock_subprocess_failure
    ):
        with patch("subprocess.run", return_value=mock_subprocess_failure):
            with pytest.raises(RuntimeError):
                firewall_service._run_nftables_command(
                    "list table inet xctf", check=True
                )

    def test_run_nftables_command_failure_no_check(
        self, firewall_service, mock_subprocess_failure
    ):
        with patch("subprocess.run", return_value=mock_subprocess_failure):
            success, output = firewall_service._run_nftables_command(
                "list table inet xctf", check=False
            )
            assert success is False
            assert "Error message" in output

    def test_initialize_firewall_already_initialized(self, firewall_service):
        firewall_service._initialized = True
        result = firewall_service.initialize_firewall()
        assert result is True

    def test_initialize_firewall_table_exists(
        self, firewall_service, mock_subprocess_success
    ):
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.initialize_firewall()
            assert result is True
            assert firewall_service._initialized is True

    def test_initialize_firewall_new_table(self, firewall_service):
        mock_success = Mock()
        mock_success.returncode = 0
        mock_success.stdout = "success"
        mock_success.stderr = ""

        mock_failure = Mock()
        mock_failure.returncode = 1
        mock_failure.stdout = ""
        mock_failure.stderr = "not found"

        with patch("subprocess.run", side_effect=[mock_failure] + [mock_success] * 20):
            result = firewall_service.initialize_firewall()
            assert result is True
            assert firewall_service._initialized is True

    def test_add_port_ip_mapping_success(
        self, firewall_service, mock_subprocess_success
    ):
        firewall_service._initialized = True
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.add_port_ip_mapping(32768, "192.168.1.1")
            assert result is True

    def test_add_port_ip_mapping_not_initialized(
        self, firewall_service, mock_subprocess_success
    ):
        firewall_service._initialized = False
        mock_failure = Mock()
        mock_failure.returncode = 1
        mock_failure.stdout = ""
        mock_failure.stderr = "not found"

        with patch(
            "subprocess.run",
            side_effect=[mock_failure] + [mock_subprocess_success] * 20,
        ):
            result = firewall_service.add_port_ip_mapping(32768, "192.168.1.1")
            assert result is True

    def test_remove_port_ip_mapping_success(
        self, firewall_service, mock_subprocess_success
    ):
        firewall_service._initialized = True
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.remove_port_ip_mapping(32768, "192.168.1.1")
            assert result is True

    def test_remove_port_ip_mapping_not_initialized(self, firewall_service):
        firewall_service._initialized = False
        result = firewall_service.remove_port_ip_mapping(32768, "192.168.1.1")
        assert result is False

    def test_add_static_port_success(self, firewall_service, mock_subprocess_success):
        firewall_service._initialized = True
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.add_static_port(8000)
            assert result is True

    def test_remove_static_port_success(
        self, firewall_service, mock_subprocess_success
    ):
        firewall_service._initialized = True
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.remove_static_port(8000)
            assert result is True

    def test_remove_sandbox_port_success(
        self, firewall_service, mock_subprocess_success
    ):
        firewall_service._initialized = True
        with patch("subprocess.run", return_value=mock_subprocess_success):
            result = firewall_service.remove_sandbox_port(32768)
            assert result is True

    def test_get_client_ip_from_x_forwarded_for(self, firewall_service):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_FORWARDED_FOR="192.168.1.1, 10.0.0.1")
        ip = firewall_service.get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_from_x_real_ip(self, firewall_service):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REAL_IP="192.168.1.2")
        ip = firewall_service.get_client_ip(request)
        assert ip == "192.168.1.2"

    def test_get_client_ip_from_remote_addr(self, firewall_service):
        factory = RequestFactory()
        request = factory.get("/", REMOTE_ADDR="192.168.1.3")
        ip = firewall_service.get_client_ip(request)
        assert ip == "192.168.1.3"

    def test_get_client_ip_default(self, firewall_service):
        factory = RequestFactory()
        request = factory.get("/")
        ip = firewall_service.get_client_ip(request)
        assert ip == "127.0.0.1"

    def test_save_rules_to_file_success(
        self, firewall_service, mock_subprocess_success, tmp_path
    ):
        firewall_service.NFTABLES_RULES_FILE = str(tmp_path / "test-rules.conf")
        firewall_service._initialized = True

        mock_success_with_output = Mock()
        mock_success_with_output.returncode = 0
        mock_success_with_output.stdout = "table inet xctf { ... }"
        mock_success_with_output.stderr = ""

        with patch("subprocess.run", return_value=mock_success_with_output):
            result = firewall_service.save_rules_to_file()
            assert result is True
            assert (tmp_path / "test-rules.conf").exists()

    def test_get_firewall_service_singleton(self):
        service1 = get_firewall_service()
        service2 = get_firewall_service()
        assert service1 is service2
        assert isinstance(service1, FirewallService)
