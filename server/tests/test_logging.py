import configparser
import importlib
import json
import logging
import os
import sys

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


def _console_handler() -> logging.StreamHandler:
    """The single non-file StreamHandler on root."""
    handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert len(handlers) == 1
    return handlers[0]


def _format(level: int, msg: str, *, name: str = "test", args: tuple = (), exc_info=None) -> str:
    """Render one record through the configured console formatter."""
    record = logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1, msg=msg, args=args, exc_info=exc_info
    )
    formatter = _console_handler().formatter
    assert formatter is not None
    return formatter.format(record)


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


class TestStreamDestination:
    """Railway classifies anything on stderr as an error, whatever the record says."""

    def test_console_handler_writes_to_stdout_in_production(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        console = _console_handler()
        assert console.stream is sys.stdout

    def test_console_handler_writes_to_stdout_in_development(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        console = _console_handler()
        assert console.stream is sys.stdout


class TestProductionJsonFormat:
    def test_emits_json_with_railway_field_contract(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        payload = json.loads(_format(logging.INFO, "attributed 1 PRs", name="app.services.x"))
        assert payload["message"] == "attributed 1 PRs"
        assert payload["level"] == "info"
        assert payload["logger"] == "app.services.x"
        assert payload["timestamp"]

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (logging.DEBUG, "debug"),
            (logging.INFO, "info"),
            (logging.WARNING, "warn"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "error"),
        ],
    )
    def test_maps_levels_to_railway_severities(self, log_dir, level, expected):
        configure_logging(make_settings("production"), log_dir=log_dir)
        assert json.loads(_format(level, "msg"))["level"] == expected

    def test_renders_interpolated_message(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        payload = json.loads(_format(logging.INFO, "attributed %d PRs", args=(3,)))
        assert payload["message"] == "attributed 3 PRs"

    def test_includes_exception_text(self, log_dir):
        configure_logging(make_settings("production"), log_dir=log_dir)
        try:
            raise ValueError("boom")
        except ValueError:
            record = _format(logging.ERROR, "handler failed", exc_info=sys.exc_info())
        payload = json.loads(record)
        assert "ValueError: boom" in payload["exception"]

    def test_development_keeps_plain_text(self, log_dir):
        configure_logging(make_settings("development"), log_dir=log_dir)
        rendered = _format(logging.INFO, "hello", name="app.x")
        assert rendered.endswith("INFO app.x: hello")


class TestNoisyThirdPartyLoggers:
    """httpx logs one INFO line per outbound Clerk/GitHub call — pure noise at our volume."""

    @pytest.mark.parametrize("name", ["httpx", "httpcore"])
    def test_third_party_request_logging_is_warning_only(self, log_dir, name):
        configure_logging(make_settings("production"), log_dir=log_dir)
        assert logging.getLogger(name).getEffectiveLevel() == logging.WARNING


class TestUvicornLoggers:
    """Uvicorn configures its own handlers at boot; uvicorn.error defaults to stderr."""

    @pytest.mark.parametrize("name", ["uvicorn", "uvicorn.error", "uvicorn.access"])
    def test_uvicorn_loggers_propagate_to_root(self, log_dir, name):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.addHandler(logging.StreamHandler(sys.stderr))
        uvicorn_logger.propagate = False

        configure_logging(make_settings("production"), log_dir=log_dir)

        assert uvicorn_logger.handlers == []
        assert uvicorn_logger.propagate is True


class TestAlembicLogging:
    """Migrations run as their own process (Railway pre-deploy) and never call
    configure_logging, so alembic.ini is the only thing steering their output."""

    def _console_handler_args(self) -> str:
        parser = configparser.ConfigParser()
        parser.read(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        return parser["handler_console"]["args"]

    def test_console_handler_writes_to_stdout(self):
        assert "sys.stdout" in self._console_handler_args()

    def test_console_handler_does_not_write_to_stderr(self):
        assert "sys.stderr" not in self._console_handler_args()


class TestConfiguredAtImportTime:
    """uvicorn logs "Started server process" *after* importing the app but before
    lifespan runs, so configuring inside lifespan left those boot lines on stderr."""

    def test_importing_main_configures_logging(self):
        import app.main

        logging.getLogger().handlers.clear()
        uvicorn_error = logging.getLogger("uvicorn.error")
        uvicorn_error.addHandler(logging.StreamHandler(sys.stderr))
        uvicorn_error.propagate = False

        importlib.reload(app.main)

        assert _console_handler().stream is sys.stdout
        assert uvicorn_error.handlers == []
        assert uvicorn_error.propagate is True

    def test_uvicorn_boot_message_is_captured_as_info(self, capsys, monkeypatch):
        import app.main

        # The reload re-runs configure_logging(settings) with the real settings
        # singleton, whose environment comes from the developer's .env (CI sets
        # ENVIRONMENT=test). Pin a non-development environment so the JSON
        # formatter under test is selected regardless of the ambient .env.
        monkeypatch.setattr("app.config.settings.environment", "test")

        logging.getLogger().handlers.clear()
        importlib.reload(app.main)

        logging.getLogger("uvicorn.error").info("Started server process [%d]", 1)

        captured = capsys.readouterr()
        assert captured.err == ""
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["message"] == "Started server process [1]"
        assert payload["level"] == "info"
