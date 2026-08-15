# shared/tests/test_logger.py
import json
import logging

from shared.logger import get_logger


def test_logger_includes_trace_id(caplog):
    logger = get_logger(trace_id="txn-123", agent_name="Sentry")
    with caplog.at_level(logging.INFO):
        logger.info("anomaly detected", anomaly="gpu_failure")
    assert len(caplog.records) == 1
    record = caplog.records[0]
    # structlog's JSONRenderer puts bound context in the JSON output
    log_data = json.loads(record.msg)
    assert log_data["trace_id"] == "txn-123"
    assert log_data["agent_name"] == "Sentry"
