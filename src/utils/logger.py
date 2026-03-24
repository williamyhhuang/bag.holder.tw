"""
Centralized logging system with structured logging and database integration
"""
import logging
import logging.handlers
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from contextvars import ContextVar

from sqlalchemy.orm import Session

from ..database.models import SystemLog
from ..database.connection import db_manager

# Context variable for request ID tracking
request_id_context: ContextVar[str] = ContextVar('request_id', default='')

class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured logs in JSON format
    """

    def format(self, record: logging.LogRecord) -> str:
        # Create base log structure
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'module': record.name,
            'message': record.getMessage(),
            'request_id': request_id_context.get(''),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        # Add function and line info for debug mode
        if record.levelno <= logging.DEBUG:
            log_entry.update({
                'function': record.funcName,
                'filename': record.filename,
                'line_number': record.lineno
            })

        return json.dumps(log_entry, ensure_ascii=False, default=str)

class DatabaseLogHandler(logging.Handler):
    """
    Custom log handler that writes logs to database
    """

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self.buffer = []
        self.buffer_size = 100
        self._last_flush = datetime.now()

    def emit(self, record: logging.LogRecord):
        """Emit a log record to database"""
        try:
            # Create log entry
            log_entry = {
                'level': record.levelname,
                'module': record.name,
                'message': record.getMessage(),
                'details': self._get_details(record)
            }

            self.buffer.append(log_entry)

            # Flush buffer if it's full or for ERROR/CRITICAL levels
            if (len(self.buffer) >= self.buffer_size or
                record.levelno >= logging.ERROR or
                (datetime.now() - self._last_flush).seconds > 60):
                self.flush()

        except Exception:
            # Don't let logging errors break the application
            self.handleError(record)

    def _get_details(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract additional details from log record"""
        details = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'function': record.funcName,
            'filename': record.filename,
            'line_number': record.lineno,
            'request_id': request_id_context.get(''),
        }

        # Add exception info if present
        if record.exc_info:
            details['exception'] = self.format(record)

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            details.update(record.extra_fields)

        return details

    def flush(self):
        """Flush buffered logs to database"""
        if not self.buffer:
            return

        try:
            with db_manager.get_session() as session:
                log_objects = [
                    SystemLog(
                        level=entry['level'],
                        module=entry['module'],
                        message=entry['message'],
                        details=entry['details']
                    )
                    for entry in self.buffer
                ]

                session.add_all(log_objects)
                session.commit()

            self.buffer.clear()
            self._last_flush = datetime.now()

        except Exception as e:
            # If database is unavailable, just clear buffer to prevent memory issues
            print(f"Failed to write logs to database: {e}", file=sys.stderr)
            self.buffer.clear()

class TelegramLogHandler(logging.Handler):
    """
    Log handler that sends critical errors to Telegram
    """

    def __init__(self, telegram_client=None, chat_id: str = None, level=logging.ERROR):
        super().__init__(level)
        self.telegram_client = telegram_client
        self.chat_id = chat_id
        self.last_sent = {}
        self.cooldown_seconds = 300  # 5 minutes cooldown

    def emit(self, record: logging.LogRecord):
        """Send log record to Telegram"""
        if not self.telegram_client or not self.chat_id:
            return

        try:
            # Implement cooldown to prevent spam
            message_key = f"{record.name}:{record.levelname}"
            now = datetime.now()

            if (message_key in self.last_sent and
                (now - self.last_sent[message_key]).seconds < self.cooldown_seconds):
                return

            # Format message for Telegram
            message = self._format_telegram_message(record)

            # Send async (implement this based on your Telegram client)
            # asyncio.create_task(self.telegram_client.send_message(self.chat_id, message))

            self.last_sent[message_key] = now

        except Exception:
            self.handleError(record)

    def _format_telegram_message(self, record: logging.LogRecord) -> str:
        """Format log record for Telegram"""
        emoji = "🔴" if record.levelno >= logging.ERROR else "🟡"

        message = f"{emoji} *{record.levelname}*\n"
        message += f"*Module:* {record.name}\n"
        message += f"*Message:* {record.getMessage()}\n"
        message += f"*Time:* {datetime.fromtimestamp(record.created).isoformat()}"

        if record.exc_info:
            message += f"\n*Exception:* `{self.formatException(record.exc_info)[:500]}`"

        return message

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_file_size: str = "10MB",
    backup_count: int = 5,
    enable_database_logging: bool = True,
    enable_structured_logging: bool = True,
    enable_telegram_alerts: bool = False,
    telegram_client=None,
    telegram_chat_id: str = None
) -> logging.Logger:
    """
    Setup centralized logging configuration

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
        max_file_size: Maximum size per log file
        backup_count: Number of backup log files to keep
        enable_database_logging: Whether to log to database
        enable_structured_logging: Whether to use structured JSON logging
        enable_telegram_alerts: Whether to send critical errors to Telegram
        telegram_client: Telegram client instance
        telegram_chat_id: Telegram chat ID for alerts

    Returns:
        Configured logger instance
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if enable_structured_logging:
        console_formatter = StructuredFormatter()
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert size string to bytes
        size_bytes = _parse_size(max_file_size)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=size_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )

        if enable_structured_logging:
            file_formatter = StructuredFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            )

        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Database handler
    if enable_database_logging:
        try:
            db_handler = DatabaseLogHandler(level=logging.INFO)
            root_logger.addHandler(db_handler)
        except Exception as e:
            print(f"Failed to setup database logging: {e}", file=sys.stderr)

    # Telegram handler
    if enable_telegram_alerts and telegram_client and telegram_chat_id:
        try:
            telegram_handler = TelegramLogHandler(
                telegram_client=telegram_client,
                chat_id=telegram_chat_id,
                level=logging.ERROR
            )
            root_logger.addHandler(telegram_handler)
        except Exception as e:
            print(f"Failed to setup Telegram logging: {e}", file=sys.stderr)

    # Set levels for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    return root_logger

def _parse_size(size_str: str) -> int:
    """Parse size string to bytes"""
    size_str = size_str.upper().strip()

    if size_str.endswith('KB'):
        return int(float(size_str[:-2]) * 1024)
    elif size_str.endswith('MB'):
        return int(float(size_str[:-2]) * 1024 * 1024)
    elif size_str.endswith('GB'):
        return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
    else:
        return int(size_str)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)

def log_with_context(logger: logging.Logger, level: int, message: str, **kwargs):
    """
    Log a message with additional context

    Args:
        logger: Logger instance
        level: Logging level
        message: Log message
        **kwargs: Additional context fields
    """
    # Create log record with extra fields
    extra = {'extra_fields': kwargs}
    logger.log(level, message, extra=extra)

def set_request_id(request_id: str):
    """Set request ID for current context"""
    request_id_context.set(request_id)

def get_request_id() -> str:
    """Get request ID from current context"""
    return request_id_context.get('')

# Exception tracking utilities
class ErrorTracker:
    """Track and categorize application errors"""

    def __init__(self):
        self.error_counts = {}
        self.logger = get_logger(__name__)

    def track_error(self, error: Exception, context: Dict[str, Any] = None):
        """
        Track an error occurrence

        Args:
            error: Exception instance
            context: Additional context about the error
        """
        error_type = type(error).__name__
        error_message = str(error)

        # Update error count
        error_key = f"{error_type}:{error_message}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

        # Log with context
        log_context = {
            'error_type': error_type,
            'error_count': self.error_counts[error_key],
            'context': context or {}
        }

        log_with_context(
            self.logger,
            logging.ERROR,
            f"{error_type}: {error_message}",
            **log_context
        )

    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of tracked errors"""
        return self.error_counts.copy()

# Global error tracker instance
error_tracker = ErrorTracker()