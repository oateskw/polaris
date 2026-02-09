"""Tests for CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from polaris.cli.main import app

runner = CliRunner()


class TestInitCommand:
    """Tests for init command."""

    def test_init_creates_database(self, tmp_path, monkeypatch):
        """Test init command creates database."""
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

        with patch("polaris.cli.main.get_settings") as mock_settings:
            mock_settings.return_value.database_url = f"sqlite:///{db_path}"
            mock_settings.return_value.data_dir = tmp_path
            mock_settings.return_value.is_anthropic_configured = False
            mock_settings.return_value.is_instagram_configured = False

            result = runner.invoke(app, ["init"])

            assert result.exit_code == 0
            assert "initialized successfully" in result.output.lower()


class TestVersionCommand:
    """Tests for version command."""

    def test_version_shows_version(self):
        """Test version command shows version number."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "polaris" in result.output.lower()


class TestAccountsCommands:
    """Tests for accounts commands."""

    def test_accounts_list_no_accounts(self, tmp_path, monkeypatch):
        """Test accounts list with no accounts."""
        db_path = tmp_path / "test.db"

        with patch("polaris.cli.accounts.get_session") as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            with patch("polaris.cli.accounts.AccountRepository") as mock_repo:
                mock_repo.return_value.get_active_accounts.return_value = []

                result = runner.invoke(app, ["accounts", "list"])

                assert result.exit_code == 0
                assert "no accounts found" in result.output.lower()


class TestContentCommands:
    """Tests for content commands."""

    def test_content_list_no_content(self, tmp_path, monkeypatch):
        """Test content list with no content."""
        with patch("polaris.cli.content.get_session") as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            with patch("polaris.cli.content.ContentRepository") as mock_repo:
                mock_repo.return_value.get_all.return_value = []

                result = runner.invoke(app, ["content", "list"])

                assert result.exit_code == 0
                assert "no content found" in result.output.lower()

    def test_content_generate_no_api_key(self, monkeypatch):
        """Test content generate without API key."""
        with patch("polaris.cli.content.get_settings") as mock_settings:
            mock_settings.return_value.is_anthropic_configured = False

            result = runner.invoke(app, ["content", "generate", "--topic", "test"])

            assert result.exit_code == 1
            assert "anthropic api key not configured" in result.output.lower()


class TestScheduleCommands:
    """Tests for schedule commands."""

    def test_schedule_list_no_schedules(self):
        """Test schedule list with no schedules."""
        with patch("polaris.cli.schedule.get_session") as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            with patch("polaris.cli.schedule.ScheduleRepository") as mock_repo:
                mock_repo.return_value.get_pending.return_value = []

                result = runner.invoke(app, ["schedule", "list"])

                assert result.exit_code == 0
                assert "no scheduled posts found" in result.output.lower()


class TestAnalyticsCommands:
    """Tests for analytics commands."""

    def test_analytics_report_no_accounts(self):
        """Test analytics report with no accounts."""
        with patch("polaris.cli.analytics.get_session") as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            with patch("polaris.cli.analytics.AccountRepository") as mock_repo:
                mock_repo.return_value.get_active_accounts.return_value = []

                result = runner.invoke(app, ["analytics", "report"])

                assert result.exit_code == 0
                assert "no active accounts found" in result.output.lower()
