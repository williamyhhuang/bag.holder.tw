"""
Rate limiting utilities for API requests and system operations
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import json

import redis.asyncio as aioredis

from .logger import get_logger

logger = get_logger(__name__)

class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded"""
    pass

class RateLimiter:
    """
    In-memory rate limiter for basic rate limiting
    """

    def __init__(self, max_requests: int, time_window: int):
        """
        Initialize rate limiter

        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: list = []
        self._lock: asyncio.Lock = None  # type: ignore

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> bool:
        """
        Acquire permission to make a request

        Returns:
            True if request is allowed, raises RateLimitExceeded if not
        """
        async with self._get_lock():
            now = time.time()

            # Remove requests outside the time window
            self.requests = [req_time for req_time in self.requests
                           if now - req_time < self.time_window]

            if len(self.requests) >= self.max_requests:
                # Calculate wait time
                oldest_request = min(self.requests)
                wait_time = self.time_window - (now - oldest_request)

                if wait_time > 0:
                    logger.warning(f"Rate limit exceeded, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
                    return await self.acquire()

            # Add current request
            self.requests.append(now)
            return True

    def reset(self):
        """Reset the rate limiter"""
        self.requests.clear()

class RedisRateLimiter:
    """
    Redis-based rate limiter for distributed systems
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        key_prefix: str = "rate_limit",
        max_requests: int = 30,
        time_window: int = 60
    ):
        """
        Initialize Redis rate limiter

        Args:
            redis_client: Redis client instance
            key_prefix: Prefix for Redis keys
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.time_window = time_window

    def _get_key(self, identifier: str) -> str:
        """Get Redis key for identifier"""
        return f"{self.key_prefix}:{identifier}"

    async def acquire(self, identifier: str = "default") -> bool:
        """
        Acquire permission to make a request

        Args:
            identifier: Unique identifier for the rate limit (e.g., API endpoint)

        Returns:
            True if request is allowed
        """
        key = self._get_key(identifier)
        now = int(time.time())
        window_start = now - self.time_window

        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Remove expired requests
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current requests in window
        pipe.zcard(key)

        # Execute pipeline
        results = await pipe.execute()
        current_requests = results[1]

        if current_requests >= self.max_requests:
            # Get the oldest request time
            oldest_requests = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest_requests:
                oldest_time = oldest_requests[0][1]
                wait_time = self.time_window - (now - oldest_time)

                if wait_time > 0:
                    logger.warning(f"Rate limit exceeded for {identifier}, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
                    return await self.acquire(identifier)

        # Add current request
        await self.redis.zadd(key, {str(now): now})

        # Set expiration for cleanup
        await self.redis.expire(key, self.time_window + 60)

        return True

    async def get_remaining(self, identifier: str = "default") -> int:
        """
        Get remaining requests in current window

        Args:
            identifier: Unique identifier for the rate limit

        Returns:
            Number of remaining requests
        """
        key = self._get_key(identifier)
        now = int(time.time())
        window_start = now - self.time_window

        # Remove expired requests and count
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)

        results = await pipe.execute()
        current_requests = results[1]

        return max(0, self.max_requests - current_requests)

    async def reset(self, identifier: str = "default"):
        """
        Reset rate limit for identifier

        Args:
            identifier: Unique identifier to reset
        """
        key = self._get_key(identifier)
        await self.redis.delete(key)

class DatabaseRateLimiter:
    """
    Database-based rate limiter with persistent storage
    """

    def __init__(
        self,
        api_name: str,
        max_requests: int = 30,
        time_window_minutes: int = 1
    ):
        """
        Initialize database rate limiter

        Args:
            api_name: Name of the API (e.g., 'fubon_api', 'telegram_api')
            max_requests: Maximum number of requests allowed
            time_window_minutes: Time window in minutes
        """
        self.api_name = api_name
        self.max_requests = max_requests
        self.time_window_minutes = time_window_minutes

    async def acquire(self, endpoint: str = None) -> bool:
        """
        Acquire permission to make a request

        Args:
            endpoint: Optional specific endpoint

        Returns:
            True if request is allowed
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.time_window_minutes)
        window_start = window_start.replace(second=0, microsecond=0)  # Round to minute

        try:
            with db_manager.get_session() as session:
                # Clean up old records
                session.query(APIRateLimit).filter(
                    APIRateLimit.api_name == self.api_name,
                    APIRateLimit.window_start < window_start
                ).delete()

                # Get or create current window record
                rate_limit = session.query(APIRateLimit).filter(
                    APIRateLimit.api_name == self.api_name,
                    APIRateLimit.endpoint == endpoint,
                    APIRateLimit.window_start == window_start
                ).first()

                if rate_limit is None:
                    rate_limit = APIRateLimit(
                        api_name=self.api_name,
                        endpoint=endpoint,
                        window_start=window_start,
                        window_duration_minutes=self.time_window_minutes,
                        request_count=0
                    )
                    session.add(rate_limit)

                # Check if limit is exceeded
                if rate_limit.request_count >= self.max_requests:
                    wait_time = (window_start + timedelta(minutes=self.time_window_minutes) - now).total_seconds()

                    if wait_time > 0:
                        logger.warning(
                            f"Rate limit exceeded for {self.api_name}:{endpoint}, "
                            f"waiting {wait_time:.2f} seconds"
                        )
                        await asyncio.sleep(wait_time)
                        return await self.acquire(endpoint)

                # Increment request count
                rate_limit.request_count += 1
                session.commit()

                logger.debug(
                    f"Rate limit {self.api_name}:{endpoint}: "
                    f"{rate_limit.request_count}/{self.max_requests}"
                )

                return True

        except Exception as e:
            logger.error(f"Database rate limiter error: {e}")
            # Fallback: allow request but log error
            return True

    async def get_remaining(self, endpoint: str = None) -> int:
        """
        Get remaining requests in current window

        Args:
            endpoint: Optional specific endpoint

        Returns:
            Number of remaining requests
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.time_window_minutes)
        window_start = window_start.replace(second=0, microsecond=0)

        try:
            with db_manager.get_session() as session:
                rate_limit = session.query(APIRateLimit).filter(
                    APIRateLimit.api_name == self.api_name,
                    APIRateLimit.endpoint == endpoint,
                    APIRateLimit.window_start == window_start
                ).first()

                if rate_limit is None:
                    return self.max_requests

                return max(0, self.max_requests - rate_limit.request_count)

        except Exception as e:
            logger.error(f"Database rate limiter error: {e}")
            return self.max_requests  # Fallback

class RateLimitManager:
    """
    Unified rate limit manager that can use different backends
    """

    def __init__(self):
        self.limiters: Dict[str, Any] = {}

    def add_limiter(self, name: str, limiter: Any):
        """Add a rate limiter"""
        self.limiters[name] = limiter

    def get_limiter(self, name: str) -> Optional[Any]:
        """Get a rate limiter by name"""
        return self.limiters.get(name)

    async def acquire(self, limiter_name: str, identifier: str = "default") -> bool:
        """
        Acquire permission from a named rate limiter

        Args:
            limiter_name: Name of the rate limiter
            identifier: Identifier for the request

        Returns:
            True if request is allowed
        """
        limiter = self.get_limiter(limiter_name)
        if limiter is None:
            logger.warning(f"Rate limiter '{limiter_name}' not found")
            return True

        if hasattr(limiter, 'acquire'):
            if isinstance(limiter, (RedisRateLimiter, DatabaseRateLimiter)):
                return await limiter.acquire(identifier)
            else:
                return await limiter.acquire()

        return True

# Global rate limit manager instance
rate_limit_manager = RateLimitManager()

# Helper function to create Redis client
async def create_redis_client(redis_url: str) -> aioredis.Redis:
    """
    Create Redis client for rate limiting

    Args:
        redis_url: Redis connection URL

    Returns:
        Redis client instance
    """
    try:
        redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_keepalive=True,
            socket_keepalive_options={}
        )

        # Test connection
        await redis_client.ping()
        logger.info("Redis connection established for rate limiting")

        return redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

# Helper function to setup default rate limiters
async def setup_rate_limiters(redis_url: str = None):
    """
    Setup default rate limiters

    Args:
        redis_url: Optional Redis URL for Redis-based rate limiting
    """
    try:
        # Basic in-memory rate limiter for Fubon API
        fubon_limiter = RateLimiter(max_requests=30, time_window=60)
        rate_limit_manager.add_limiter("fubon_basic", fubon_limiter)

        # Database rate limiter for persistent tracking
        fubon_db_limiter = DatabaseRateLimiter(
            api_name="fubon_api",
            max_requests=30,
            time_window_minutes=1
        )
        rate_limit_manager.add_limiter("fubon_db", fubon_db_limiter)

        # Telegram rate limiter
        telegram_limiter = RateLimiter(max_requests=30, time_window=1)
        rate_limit_manager.add_limiter("telegram", telegram_limiter)

        # Redis rate limiter if available
        if redis_url:
            try:
                redis_client = await create_redis_client(redis_url)

                fubon_redis_limiter = RedisRateLimiter(
                    redis_client=redis_client,
                    key_prefix="fubon_api",
                    max_requests=30,
                    time_window=60
                )
                rate_limit_manager.add_limiter("fubon_redis", fubon_redis_limiter)

                telegram_redis_limiter = RedisRateLimiter(
                    redis_client=redis_client,
                    key_prefix="telegram_api",
                    max_requests=30,
                    time_window=1
                )
                rate_limit_manager.add_limiter("telegram_redis", telegram_redis_limiter)

                logger.info("Redis rate limiters configured")

            except Exception as e:
                logger.warning(f"Redis rate limiters not available: {e}")

        logger.info("Rate limiters configured successfully")

    except Exception as e:
        logger.error(f"Failed to setup rate limiters: {e}")
        raise