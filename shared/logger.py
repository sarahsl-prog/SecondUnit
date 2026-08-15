import logging
import sys

import structlog

_configured = False


def configure_logging() -> None:
    """Set up stdlib logging + structlog. Idempotent — safe to call more
    than once (e.g. once explicitly at service startup, then again lazily
    from get_logger() for anything that imports this module directly,
    like agent unit tests that never touch a service's main.py).

    This used to run as an import-time side effect just from
    `import shared.logger`, which was surprising in isolated unit tests
    and would (harmlessly, since guarded) re-run structlog.configure()
    on every import. Now nothing happens until logging is actually used
    (review #21)."""
    global _configured
    if _configured:
        return

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(trace_id: str = "", agent_name: str = ""):
    configure_logging()
    logger = structlog.get_logger()
    if trace_id:
        logger = logger.bind(trace_id=trace_id)
    if agent_name:
        logger = logger.bind(agent_name=agent_name)
    return logger
