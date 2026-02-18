import structlog
import logging
import sys
from datetime import datetime

def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Настройка структурированного логирования"""
    
    # Настройка базового логгера
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            *([] if not log_file else [logging.FileHandler(log_file)])
        ]
    )

    # Настройка процессоров для structlog
    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

def get_logger(name: str = None):
    """Получение настроенного логгера"""
    return structlog.get_logger(name)

# Пример использования:
# logger = get_logger(__name__)
# logger.info("user_action", action="subscription_gift", user_id=123, status="success") 