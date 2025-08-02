import pytest
from challenge.models import Challenge, Submission, Sandbox


@pytest.mark.django_db
class TestChallengeModel:
    def test_create_challenge(self):
        challenge = Challenge.objects.create(
            name="Test Challenge",
            category="Web",
            points=100,
            flag="FLAG{test}",
            static=False,
            active=True,
        )
        assert challenge.name == "Test Challenge"
        assert challenge.category == "Web"
        assert challenge.points == 100
        assert challenge.flag == "FLAG{test}"
        assert challenge.static is False
        assert challenge.active is True

    def test_challenge_str(self, challenge):
        assert str(challenge) == "<Challenge Web::Test Challenge>"

    def test_static_challenge(self, static_challenge):
        assert static_challenge.static is True


@pytest.mark.django_db
class TestSubmissionModel:
    def test_create_submission(self, user, challenge):
        submission = Submission.objects.create(
            user=user,
            challenge=challenge,
            correct=True,
        )
        assert submission.user == user
        assert submission.challenge == challenge
        assert submission.correct is True

    def test_incorrect_submission(self, user, challenge):
        submission = Submission.objects.create(
            user=user,
            challenge=challenge,
            correct=False,
        )
        assert submission.correct is False


@pytest.mark.django_db
class TestSandboxModel:
    def test_create_sandbox(self, user, challenge):
        sandbox = Sandbox.objects.create(
            user=user,
            challenge=challenge,
            container_id="test-container",
            container_port=8000,
            active=True,
            port_mappings={},
        )
        assert sandbox.user == user
        assert sandbox.challenge == challenge
        assert sandbox.container_port == 8000
        assert sandbox.active is True
