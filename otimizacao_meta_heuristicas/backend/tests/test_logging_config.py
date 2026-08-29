import json
import logging

from app.logging_config import JsonLogFormatter, log_event


def _make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="football_intelligence",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_json_log_formatter_produces_valid_json_with_core_fields():
    formatter = JsonLogFormatter()
    record = _make_record("something happened")

    formatted = formatter.format(record)
    payload = json.loads(formatted)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "football_intelligence"
    assert payload["message"] == "something happened"


def test_log_event_attaches_extra_fields(caplog):
    logger = logging.getLogger("football-intelligence-test-logger")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = True

    with caplog.at_level(logging.INFO, logger="football-intelligence-test-logger"):
        log_event(logger, "http_request", request_id="abc123", status_code=200)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.extra_fields == {"request_id": "abc123", "status_code": 200}
