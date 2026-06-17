"""Tests for duggerbot.ponds — Phase 4b."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from duggerbot.ponds import self_status
from duggerbot.ponds import devto, blog, youtube, calendar


async def test_self_status_returns_pond_name(tmp_path):
    """Run self_status.run() with mocked subprocess → result["pond"] == "self_status"."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r50"):
            # No issues dir
            result = await self_status.run()
            assert result["pond"] == "self_status"


async def test_self_status_summary_contains_version(tmp_path):
    """Mocked get_version_string → summary contains version string."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r99"):
            result = await self_status.run()
            assert "0.1.0.r99" in result["summary"]


async def test_self_status_no_issues_when_dir_empty(tmp_path):
    """No issues in docs/issues → open_issues == []."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r50"):
            with patch("duggerbot.ponds.self_status._read_open_issues", return_value=[]):
                result = await self_status.run()
                assert result["open_issues"] == []


# ---------------------------------------------------------------------------
# Phase 4b — Dev.to pond tests
# ---------------------------------------------------------------------------

async def test_devto_returns_stats_on_success():
    """Mock httpx → article_count, total_reads in result."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"page_views_count": 500, "positive_reactions_count": 10},
        {"page_views_count": 300, "positive_reactions_count": 5},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("duggerbot.ponds.devto.httpx.AsyncClient") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = MagicMock(return_value=None)
        mock_ctx.get = MagicMock(return_value=mock_response)
        mock_client.return_value = mock_ctx

        with patch.dict("os.environ", {"DEVTO_API_KEY": "test_key"}):
            result = await devto.run()
            assert result["article_count"] == 2
            assert result["total_reads"] == 800


async def test_devto_returns_error_when_key_missing():
    """No DEVTO_API_KEY → error key set."""
    with patch.dict("os.environ", {}, clear=True):
        result = await devto.run()
        assert "error" in result
        assert result["summary"] == "📊 Dev.to: not configured"


async def test_devto_summary_contains_article_count():
    """Mock 3 articles → summary contains "3"."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"page_views_count": 100, "positive_reactions_count": 1},
        {"page_views_count": 200, "positive_reactions_count": 2},
        {"page_views_count": 300, "positive_reactions_count": 3},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("duggerbot.ponds.devto.httpx.AsyncClient") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = MagicMock(return_value=None)
        mock_ctx.get = MagicMock(return_value=mock_response)
        mock_client.return_value = mock_ctx

        with patch.dict("os.environ", {"DEVTO_API_KEY": "test_key"}):
            result = await devto.run()
            assert "3" in result["summary"]


# ---------------------------------------------------------------------------
# Phase 4b — Blog pond tests
# ---------------------------------------------------------------------------

async def test_blog_returns_posts_on_success():
    """Mock httpx → posts list in result."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"date": "2024-06-21T10:00:00", "title": {"rendered": "Test Post"}}
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("duggerbot.ponds.blog.httpx.AsyncClient") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = MagicMock(return_value=None)
        mock_ctx.get = MagicMock(return_value=mock_response)
        mock_client.return_value = mock_ctx

        with patch.dict("os.environ", {
            "WORDPRESS_URL": "https://test.com",
            "WORDPRESS_USER": "user",
            "WORDPRESS_APP_PASSWORD": "pass",
        }):
            result = await blog.run()
            assert len(result["posts"]) == 1


async def test_blog_returns_not_configured_when_env_missing():
    """No WORDPRESS_URL → error."""
    with patch.dict("os.environ", {}, clear=True):
        result = await blog.run()
        assert "error" in result
        assert result["summary"] == "✍️ Blog: not configured"


async def test_blog_summary_contains_post_title():
    """Mock post with title → title in summary."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"date": "2024-06-21T10:00:00", "title": {"rendered": "My Great Post"}}
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("duggerbot.ponds.blog.httpx.AsyncClient") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = MagicMock(return_value=None)
        mock_ctx.get = MagicMock(return_value=mock_response)
        mock_client.return_value = mock_ctx

        with patch.dict("os.environ", {
            "WORDPRESS_URL": "https://test.com",
            "WORDPRESS_USER": "user",
            "WORDPRESS_APP_PASSWORD": "pass",
        }):
            result = await blog.run()
            assert "My Great Post" in result["summary"]


# ---------------------------------------------------------------------------
# Phase 4b — YouTube/Calendar pond tests (credential error handling)
# ---------------------------------------------------------------------------

async def test_youtube_returns_error_when_no_credentials():
    """get_credentials returns None → error key set."""
    with patch("duggerbot.ponds.youtube.get_credentials", return_value=None):
        result = await youtube.run()
        assert "error" in result
        assert "credentials" in result["summary"]


async def test_calendar_returns_error_when_no_credentials():
    """get_credentials returns None → error key set."""
    with patch("duggerbot.ponds.calendar.get_credentials", return_value=None):
        result = await calendar.run()
        assert "error" in result
        assert "credentials" in result["summary"]


# ---------------------------------------------------------------------------
# Phase 4b — Morning dispatch assembler test
# ---------------------------------------------------------------------------

async def test_morning_dispatch_assembles_all_sections():
    """Mock all four sub-ponds → summary contains all pond names."""
    with patch("duggerbot.ponds.self_status.youtube_run") as mock_yt:
        with patch("duggerbot.ponds.self_status.calendar_run") as mock_cal:
            with patch("duggerbot.ponds.self_status.blog_run") as mock_blog:
                with patch("duggerbot.ponds.self_status.devto_run") as mock_devto:
                    mock_yt.return_value = {"summary": "📺 YouTube test"}
                    mock_cal.return_value = {"summary": "📅 Calendar test"}
                    mock_blog.return_value = {"summary": "✍️ Blog test"}
                    mock_devto.return_value = {"summary": "📊 Dev.to test"}

                    with patch("duggerbot.version.get_version_string", return_value="0.1.0.r99"):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value.stdout = "236 passed in 2.0s"
                            result = await self_status.run()

                            assert "📺" in result["summary"] or "YouTube" in result["summary"]
                            assert "📅" in result["summary"] or "Calendar" in result["summary"]
                            assert "✍️" in result["summary"] or "Blog" in result["summary"]
                            assert "📊" in result["summary"] or "Dev.to" in result["summary"]
