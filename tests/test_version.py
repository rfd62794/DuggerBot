"""Tests for duggerbot.version — Phase 3.6."""

from unittest.mock import patch, MagicMock

from duggerbot.version import (
    get_revision,
    get_remote_revision,
    get_version_string,
    get_git_hash,
    is_update_available,
    pull_update,
    apply_update_and_exit,
)


def _mock_run_git(returncode: int, stdout: str):
    """Return a mock subprocess.run result."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


def test_get_revision_returns_int():
    """Mocked git → returns integer."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(0, "174\n")):
        assert get_revision() == 174


def test_get_revision_returns_zero_on_git_failure():
    """git fails → returns 0."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(1, "")):
        assert get_revision() == 0


def test_get_version_string_format():
    """Returns '0.1.0.rN' pattern."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(0, "42\n")):
        v = get_version_string()
        assert v == "0.1.0.r42"


def test_get_version_string_contains_revision():
    """Revision N matches get_revision()."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(0, "99\n")):
        v = get_version_string()
        assert "r99" in v
        assert get_revision() == 99


def test_get_git_hash_returns_string():
    """Mocked git → returns string."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(0, "abc1234\n")):
        assert get_git_hash() == "abc1234"


def test_get_git_hash_returns_unknown_on_failure():
    """git fails → 'unknown'."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(1, "")):
        assert get_git_hash() == "unknown"


def test_is_update_available_true_when_remote_ahead():
    """remote > local → True."""
    call_count = [0]
    def fake_run(*args, **kwargs):
        call_count[0] += 1
        cmd = args[0]
        if "origin/main" in cmd:
            return _mock_run_git(0, "200\n")
        if "HEAD" in cmd:
            return _mock_run_git(0, "174\n")
        return _mock_run_git(0, "")  # git fetch

    with patch("duggerbot.version.subprocess.run", side_effect=fake_run):
        assert is_update_available() is True


def test_is_update_available_false_when_current():
    """remote == local → False."""
    def fake_run(*args, **kwargs):
        cmd = args[0]
        if "origin/main" in cmd or "HEAD" in cmd:
            return _mock_run_git(0, "174\n")
        return _mock_run_git(0, "")

    with patch("duggerbot.version.subprocess.run", side_effect=fake_run):
        assert is_update_available() is False


def test_pull_update_returns_true_on_success():
    """git pull exit 0 → True."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(0, "")):
        assert pull_update() is True


def test_pull_update_returns_false_on_failure():
    """git pull exit 1 → False."""
    with patch("duggerbot.version.subprocess.run", return_value=_mock_run_git(1, "")):
        assert pull_update() is False
