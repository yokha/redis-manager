import time
import asyncio
import logging
from typing import Dict, Any, List, Union
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster, ClusterNode
from .config import (
    DEFAULT_POOL_OPTIONS,
    DEFAULT_CLUSTER_POOL_OPTIONS,
    VALID_POOL_ARGS,
    VALID_CLUSTER_ARGS,
    DEFAULT_VALUES,
)
from .prometheus_metrics import (
    update_failed_connections_attempts,
)


class NoHealthyPoolsException(Exception):
    """Exception raised when no healthy Redis connection pool is available."""


class InvalidPoolArguments(Exception):
    """Custom exception for invalid pool arguments."""


class RedisConnection:
    """Manages a Redis connection, handling initialization, health, and lifecycle."""

    def __init__(
        self,
        redis_url: str,
        pool_size: int = DEFAULT_VALUES["max_connection_size"],
        pool_args: Union[Dict[str, Any], None] = None,
        use_cluster: bool = DEFAULT_VALUES["use_redis_cluster"],
        startup_nodes: Union[List[ClusterNode], None] = None,
        logger: Union[logging.Logger, None] = None,
    ):
        """
        Initialize a Redis connection.

        Args:
            redis_url (str): Redis server URL.
            pool_size (int): Maximum connections in the pool.
            pool_args (dict): Custom connection pool arguments.
            use_cluster (bool): Whether to use Redis cluster.
            startup_nodes (list): Cluster startup nodes for Redis cluster mode.
            logger (logging.Logger): Custom logger instance.
        """
        self.redis_url = redis_url
        self.use_cluster = use_cluster
        self.startup_nodes = startup_nodes
        self.logger = logger or logging.getLogger(__name__)
        self.health_status = False
        self.active_calls = 0
        self.connection_duration = 0

        # Initialize Redis connection or cluster
        if self.use_cluster and self.startup_nodes:
            self.redis_client = self._initialize_cluster(pool_size, pool_args)
        else:
            self.redis_client = self._initialize_pool(pool_size, pool_args)

        self.logger.debug(f"RedisConnection initialized for {self.redis_url}")
        self._update_pool_connection_duration()

    def _initialize_pool(
        self, pool_size: int, pool_args: Union[Dict[str, Any], None]
    ) -> Redis:
        """Initialize a Redis connection pool."""
        merged_args = self._merge_pool_args(
            DEFAULT_POOL_OPTIONS, pool_args, VALID_POOL_ARGS
        )
        return Redis.from_url(self.redis_url, max_connections=pool_size, **merged_args)

    def _initialize_cluster(
        self, pool_size: int, pool_args: Union[Dict[str, Any], None]
    ) -> RedisCluster:
        """Initialize a Redis cluster connection."""
        merged_args = self._merge_pool_args(
            DEFAULT_CLUSTER_POOL_OPTIONS, pool_args, VALID_CLUSTER_ARGS
        )
        return RedisCluster(
            startup_nodes=self.startup_nodes, max_connections=pool_size, **merged_args
        )

    def _merge_pool_args(
        self, defaults: dict, custom: Union[dict, None], valid_keys: set
    ) -> dict:
        """Merge default and custom arguments, validating keys."""
        merged_args = defaults.copy()
        if custom:
            invalid_keys = set(custom.keys()) - valid_keys
            if invalid_keys:
                raise InvalidPoolArguments(
                    f"Invalid pool arguments: {', '.join(invalid_keys)}"
                )
            merged_args.update(custom)
        return merged_args

    async def wait_for_ready(
        self, timeout_sec: float = 10, step_sec: float = 0.25, max_retries: int = 5
    ):
        """
        Waits until the Redis connection is ready, or until a timeout occurs.

        Args:
            timeout_sec (float): Maximum time to wait for the connection (default: 10 seconds).
            step_sec (float): Interval between retry attempts (default: 0.25 seconds).
            max_retries (int): Maximum number of retry attempts before failure (default: 5).

        Returns:
            float: Time taken to establish the connection.

        Raises:
            NoHealthyPoolsException: If the timeout is exceeded or the maximum retries are reached.
        """
        start_time = time.time()
        attempt = 0

        while True:
            try:
                # Attempt to ping the Redis client
                await self.redis_client.ping()
                self.health_status = True
                self.connection_duration = time.time() - start_time
                self.logger.info(
                    f"Redis connection ready in {self.connection_duration:.2f}s for {self.redis_url}"
                )
                return self.connection_duration
            except RedisConnectionError as e:
                update_failed_connections_attempts(self.redis_url)
                self.health_status = False
                self.logger.warning(
                    f"Redis connection unavailable for {self.redis_url}  redis_client={self.redis_client}: {e}"
                )
                attempt += 1

                # Check if the maximum retries or timeout is exceeded
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout_sec or attempt >= max_retries:
                    raise NoHealthyPoolsException(
                        f"Timeout exceeded ({timeout_sec}s) or max retries reached ({max_retries}) while waiting for {self.redis_url}"
                    ) from e

                # Exponential backoff logic
                await asyncio.sleep(step_sec * (2**attempt))

    def get_client(self) -> Redis:
        """Get the Redis client."""
        return self.redis_client

    async def health_check(self):
        """Check the health of the Redis connection."""
        try:
            await self.redis_client.ping()
            self.health_status = True
        except Exception as e:
            self.health_status = False
            self.logger.error(f"Health check failed for {self.redis_url}. error: {e}")

    async def close(self):
        """Close the Redis connection."""
        await self.redis_client.aclose()
        self.health_status = False
        self.logger.info(f"Connection closed for {self.redis_url}")

    def _update_pool_connection_duration(self):
        """Update connection duration for metrics or logs."""
        self.logger.debug(f"Connection duration updated: {self.connection_duration}s")
