import structlog
import logging
import sys

# Ensure structlog output goes to stdout so tests can capture it
_root_logger = logging.getLogger()
if not _root_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.DEBUG)
    _root_logger.addHandler(_handler)
_root_logger.setLevel(logging.DEBUG)

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

def get_logger(trace_id: str = "", agent_name: str = ""):
    logger = structlog.get_logger()
    if trace_id:
        logger = logger.bind(trace_id=trace_id)
    if agent_name:
        logger = logger.bind(agent_name=agent_name)
    return logger
