"""
Centralized error handling utilities and decorators
"""
import asyncio
import functools
import traceback
from typing import Any, Callable, Dict, Optional, Type, Union
from datetime import datetime

from .logger import get_logger, error_tracker, log_with_context

logger = get_logger(__name__)

class ApplicationError(Exception):
    """Base application error class"""

    def __init__(
        self,
        message: str,
        error_code: str = None,
        context: Dict[str, Any] = None,
        original_error: Exception = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
        self.original_error = original_error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary"""
        return {
            'error_code': self.error_code,
            'message': self.message,
            'context': self.context,
            'timestamp': self.timestamp.isoformat(),
            'original_error': str(self.original_error) if self.original_error else None
        }

class APIError(ApplicationError):
    """API-related errors"""
    pass

class DatabaseError(ApplicationError):
    """Database-related errors"""
    pass

class ValidationError(ApplicationError):
    """Data validation errors"""
    pass

class ConfigurationError(ApplicationError):
    """Configuration-related errors"""
    pass

class RateLimitError(ApplicationError):
    """Rate limiting errors"""
    pass

class DataProcessingError(ApplicationError):
    """Data processing errors"""
    pass

def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator to retry function execution on failure

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Log final failure
                        log_with_context(
                            logger,
                            logger.ERROR,
                            f"Function {func.__name__} failed after {max_retries} retries",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e)
                        )
                        raise

                    # Log retry attempt
                    log_with_context(
                        logger,
                        logger.WARNING,
                        f"Function {func.__name__} failed, retrying in {current_delay}s",
                        function=func.__name__,
                        attempt=attempt + 1,
                        error=str(e),
                        delay=current_delay
                    )

                    # Call retry callback if provided
                    if on_retry:
                        try:
                            await on_retry(attempt, e, current_delay)
                        except Exception as callback_error:
                            logger.warning(f"Retry callback failed: {callback_error}")

                    # Wait before retry
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Log final failure
                        log_with_context(
                            logger,
                            logger.ERROR,
                            f"Function {func.__name__} failed after {max_retries} retries",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e)
                        )
                        raise

                    # Log retry attempt
                    log_with_context(
                        logger,
                        logger.WARNING,
                        f"Function {func.__name__} failed, retrying in {current_delay}s",
                        function=func.__name__,
                        attempt=attempt + 1,
                        error=str(e),
                        delay=current_delay
                    )

                    # Call retry callback if provided
                    if on_retry:
                        try:
                            if asyncio.iscoroutinefunction(on_retry):
                                asyncio.create_task(on_retry(attempt, e, current_delay))
                            else:
                                on_retry(attempt, e, current_delay)
                        except Exception as callback_error:
                            logger.warning(f"Retry callback failed: {callback_error}")

                    # Wait before retry
                    import time
                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

def handle_errors(
    default_return_value: Any = None,
    exceptions: tuple = (Exception,),
    log_level: int = None,
    reraise: bool = False
):
    """
    Decorator to handle and log errors gracefully

    Args:
        default_return_value: Value to return if error occurs
        exceptions: Tuple of exceptions to handle
        log_level: Logging level for caught exceptions
        reraise: Whether to re-raise the exception after logging
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                # Track error
                context = {
                    'function': func.__name__,
                    'args': str(args)[:200],  # Truncate for safety
                    'kwargs': str(kwargs)[:200]
                }
                error_tracker.track_error(e, context)

                # Log error
                level = log_level if log_level is not None else logger.ERROR
                log_with_context(
                    logger,
                    level,
                    f"Error in {func.__name__}: {str(e)}",
                    **context
                )

                if reraise:
                    raise

                return default_return_value

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                # Track error
                context = {
                    'function': func.__name__,
                    'args': str(args)[:200],
                    'kwargs': str(kwargs)[:200]
                }
                error_tracker.track_error(e, context)

                # Log error
                level = log_level if log_level is not None else logger.ERROR
                log_with_context(
                    logger,
                    level,
                    f"Error in {func.__name__}: {str(e)}",
                    **context
                )

                if reraise:
                    raise

                return default_return_value

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

def safe_execute(
    func: Callable,
    *args,
    default_return=None,
    log_errors: bool = True,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling

    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Default return value on error
        log_errors: Whether to log errors
        **kwargs: Function keyword arguments

    Returns:
        Function result or default return value
    """
    try:
        if asyncio.iscoroutinefunction(func):
            # For async functions, return the coroutine
            return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            context = {
                'function': func.__name__,
                'args': str(args)[:200],
                'kwargs': str(kwargs)[:200]
            }
            error_tracker.track_error(e, context)

            log_with_context(
                logger,
                logger.ERROR,
                f"Safe execution failed for {func.__name__}: {str(e)}",
                **context
            )

        return default_return

class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before trying again
            expected_exception: Exception type that triggers circuit breaker
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise ApplicationError(
                        "Circuit breaker is OPEN",
                        error_code="CIRCUIT_BREAKER_OPEN",
                        context={"function": func.__name__}
                    )

            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise ApplicationError(
                        "Circuit breaker is OPEN",
                        error_code="CIRCUIT_BREAKER_OPEN",
                        context={"function": func.__name__}
                    )

            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit"""
        if self.last_failure_time is None:
            return True

        return (datetime.now() - self.last_failure_time).total_seconds() > self.recovery_timeout

    def _on_success(self):
        """Handle successful execution"""
        self.failure_count = 0
        self.state = "CLOSED"

    def _on_failure(self):
        """Handle failed execution"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

def format_exception(e: Exception, include_traceback: bool = True) -> str:
    """
    Format exception for logging

    Args:
        e: Exception instance
        include_traceback: Whether to include traceback

    Returns:
        Formatted exception string
    """
    if include_traceback:
        return ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    else:
        return f"{type(e).__name__}: {str(e)}"

# Context manager for error handling
class ErrorContext:
    """Context manager for structured error handling"""

    def __init__(
        self,
        operation: str,
        reraise: bool = True,
        log_level: int = None,
        context: Dict[str, Any] = None
    ):
        self.operation = operation
        self.reraise = reraise
        self.log_level = log_level or logger.ERROR
        self.context = context or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Track and log error
            error_tracker.track_error(exc_val, {
                'operation': self.operation,
                **self.context
            })

            log_with_context(
                logger,
                self.log_level,
                f"Error in operation '{self.operation}': {str(exc_val)}",
                operation=self.operation,
                error_type=exc_type.__name__,
                **self.context
            )

            # Suppress exception if reraise is False
            return not self.reraise