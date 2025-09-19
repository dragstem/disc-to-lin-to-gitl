"""Comprehensive error handling, logging, and retry mechanisms."""

import logging
from logging.handlers import RotatingFileHandler
import time
import os
from typing import Callable, Any, Optional
from src.config_manager import ConfigManager

class ErrorLogger:
    """Handles error management, logging, and retry mechanisms."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize error logger.

        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup structured logging with rotation.

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger('linear_gitlab_sync')
        if logger.hasHandlers():
            return logger

        logger.setLevel(getattr(logging, self.config.log_level.upper(), logging.INFO))

        # Create logs directory
        log_dir = './logs'
        os.makedirs(log_dir, exist_ok=True)

        # Rotating file handler (1GB max, keep 1 year worth ~365 files of 3MB each day avg)
        log_file = os.path.join(log_dir, 'sync.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1024*1024*1024,  # 1GB
            backupCount=365
        )
        file_handler.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def log(self, level: str, message: str, exc_info: Optional[Any] = None) -> None:
        """Log message at specified level.

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: Log message
            exc_info: Exception info for error logs
        """
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message, exc_info=exc_info)

    def retry_with_backoff(self, func: Callable, *args, max_retries: int = 3,
                          base_delay: float = 1.0, **kwargs) -> Any:
        """Execute function with exponential backoff retry.

        Args:
            func: Function to execute
            args: Positional arguments for function
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            kwargs: Keyword arguments for function

        Returns:
            Result of successful function execution

        Raises:
            Exception: Last exception if all retries fail
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    self.log('warning',
                            f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay:.1f}s")
                    time.sleep(delay)
                else:
                    self.log('error',
                            f"Final attempt failed: {str(e)}")

        # Raise the last exception if all retries exhausted
        if last_exception:
            raise last_exception

    def handle_api_error(self, service: str, error: Exception, context: Optional[str] = None) -> None:
        """Handle API errors with structured logging.

        Args:
            service: API service name (linear, gitlab)
            error: Exception instance
            context: Additional context information
        """
        error_msg = f"{service} API error: {str(error)}"
        if context:
            error_msg += f" (context: {context})"

        # Check if it's a rate limit error
        if "rate limit" in str(error).lower() or "429" in str(error):
            self.log('warning', error_msg + " - Rate limited")
        elif "timeout" in str(error).lower():
            self.log('warning', error_msg + " - Timeout")
        else:
            self.log('error', error_msg)