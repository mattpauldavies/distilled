import logging
import os

import pytest

from app.config import Settings
from app.logging import configure_logging


@pytest.fixture(autouse=True)
def reset_logging():
    root = logging.getLogger()
    root.handlers.clear()
    yield
    root.handlers.clear()


@pytest.fixture
def log_dir(tmp_path):
    return str(tmp_path / "logs")


def make_settings(environment: str = "development") -> Settings:
    kwargs: dict = dict(
        environment=environment,
        database_url="postgresql+asyncpg://x:x@localhost/x",
        github_app_id=0,
        github_private_key_path="",
        github_webhook_secret="",
    )
    if environment == "production":
        kwargs.update(
            github_webhook_secret="test-secret",
            internal_cron_secret="test-secret",
            clerk_secret_key="test-secret",
            clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        )
    return Settings(**kwargs)


class TestDevelopmentMode:
    def test_adds_file_handler(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_creates_log_file(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        assert os.path.exists(os.path.join(log_dir, "dev.log"))

    def test_writes_logs_to_file(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        logging.getLogger("test").info("hello from test")
        content = open(os.path.join(log_dir, "dev.log")).read()
        assert "hello from test" in content

    def test_truncates_on_restart(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        logging.getLogger("test").info("first run")

        logging.getLogger().handlers.clear()
        configure_logging(make_settings("development"), log_dir=log_dir)
        logging.getLogger("test").info("second run")

        content = open(os.path.join(log_dir, "dev.log")).read()
        assert "first run" not in content
        assert "second run" in content


class TestProductionMode:
    def test_no_file_handler(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_no_log_directory_created(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        assert not os.path.exists(log_dir)


class TestConsoleHandler:
    def test_always_adds_console_handler(self, log_dir):
        for env in ("development", "production"):
            logging.getLogger().handlers.clear()
            configure_logging(make_settings(env), log_dir=log_dir)
            root = logging.getLogger()
            stream_handlers = [
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            ]
            assert len(stream_handlers) == 1

    def test_log_level_is_info(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        assert logging.getLogger().level == logging.INFO
