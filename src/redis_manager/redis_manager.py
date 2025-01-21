"""
Redis Connection Pool Manager

This class provides a Redis connection pool manager to maintain healthy
Redis connections across multiple nodes. It includes features such as 
periodic health checks, connection pooling, and dynamic management of
Redis nodes.

Configuration:
    The manager leverages default values and customizable settings from 
    `config.py`. Default pool options (`DEFAULT_POOL_OPTIONS`) and 
    cluster options (`DEFAULT_CLUSTER_POOL_OPTIONS`) are provided for 
    Redis connections. Metric names for Prometheus integration are 
    configurable via the `METRIC_NAMES` dictionary or environment 
    variables. Additional settings like `DEFAULT_VALUES` allow tuning 
    for connection size, health check intervals, and cleanup behavior.

Features:
    - Automatic connection pool management for multiple Redis nodes.
    - Periodic health checks to ensure connection reliability 
      (must be explicitly started).
    - Idle connection cleanup to optimize resource usage 
      (must be explicitly started).
    - Metrics reporting for Prometheus to monitor connection pool 
      health and usage.

Usage:
    1. Initialize the RedisManager with desired options or rely on 
       defaults from `config.py`.
    2. Add Redis node URLs to the pool using `add_node_pool`.
    3. Periodic health checks start automatically
    4- Periodic cleanup task start on choice by calling `start_cleanup()`
    4. Retrieve connections from the pool for Redis operations using 
       `get_client`.
    5. Stop health checks and cleanup tasks before initiating shutdown.
    6. Ensure graceful shutdown by calling `close_all_pools`.

Example:
    import asyncio
    from redis_manager.redis_manager import RedisManager, \
        NoHealthyPoolsException

    async def main():
        # Initialize the RedisManager
        manager = RedisManager(
            connection_pools_per_node_at_start=2,
            max_connection_size=DEFAULT_VALUES["max_connection_size"],
            health_check_interval=DEFAULT_VALUES["health_check_interval"],
            cleanup_interval=DEFAULT_VALUES["cleanup_interval"],
            max_idle_time=DEFAULT_VALUES["max_idle_time"]
        )

        # Add a Redis node to the manager
        await manager.add_node_pool("redis://localhost")

        # Start cleanup task
        redis_manager.start_cleanup()

        # Perform Redis operations using a connection from the pool
        try:
            async with manager.get_client("redis://localhost", 
                                          timeout_sec=10) as client:
                await client.ping()  # Example operation
        except NoHealthyPoolsException as ex:
            print(f"Error: No healthy connections available - {ex}")
        except ValueError as ve:
            print(f"Invalid configuration: {ve}")

        # Gracefully stop tasks and close pools
        manager.stop_health_checks()
        manager.stop_cleanup()
        await manager.close_all_pools()

    # Run the example
    asyncio.run(main())
"""

import time
import logging
import asyncio
from collections import defaultdict
from typing import Dict, List, Union
from contextlib import asynccontextmanager
from redis.asyncio.cluster import ClusterNode
from .redis_connection import RedisConnection, NoHealthyPoolsException
from .prometheus_metrics import (
    update_pool_metrics,
    update_connection_latency,
)
from .config import DEFAULT_VALUES


class RedisManager:
    """Manages multiple Redis connection pools and performs health checks."""

    def __init__(
        self,
        connection_pools_per_node_at_start: int = 1,
        max_connection_size: int = DEFAULT_VALUES["max_connection_size"],
        pool_args: Union[Dict, None] = None,
        use_cluster: bool = DEFAULT_VALUES["use_redis_cluster"],
        startup_nodes: Union[List[ClusterNode], None] = None,
        health_check_interval: float = DEFAULT_VALUES["health_check_interval"],
        cleanup_interval: float = DEFAULT_VALUES["cleanup_interval"],
        max_idle_time: float = DEFAULT_VALUES["max_idle_time"],
    ):
        self.connection_pools_per_node_at_start = connection_pools_per_node_at_start
        self.max_connection_size = max_connection_size
        self._lock = asyncio.Lock()
        self._pools: Dict[str, List[RedisConnection]] = defaultdict(list)
        self._retry_stretch_factor = 1.25
        self._wait_for_ready_step = 1
        self._default_timeout_sec = 10
        self._pools_condition = defaultdict(lambda: asyncio.Condition())
        self.pool_args = pool_args
        self.use_cluster = use_cluster
        self.startup_nodes = startup_nodes
        self._health_check_task = None
        self._cleanup_task = None
        self._health_check_interval = health_check_interval
        self._cleanup_interval = cleanup_interval
        self._max_idle_time = max_idle_time
        self.health_status = None

        # Start health check
        self.start_health_checks()

    def _start_health_check_task(self):
        """Start the periodic health check task."""
        self._health_check_task = asyncio.create_task(self._periodic_health_check())

    def _start_cleanup_task(self):
        """Start the periodic cleanup task."""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_health_check(self):
        """Run periodic health checks."""
        while True:
            try:
                asyncio.get_running_loop()
                await self._recover_unhealthy_pools()
            except asyncio.CancelledError:
                break  # Exit gracefully when cancelled
            except Exception as e:
                logging.error(
                    f"Health check failed for {self.node_redis_url}. error: {e}"
                )
            await asyncio.sleep(self._health_check_interval)

    async def _periodic_cleanup(self):
        """Run periodic cleanup to remove idle connections."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self._lock:
                now = time.time()
                for node_redis_url, pools in self._pools.items():
                    active_pools = []
                    for pool in pools[self.connection_pools_per_node_at_start :]:
                        # Check if pool is idle and has no active calls
                        if (
                            pool.active_calls == 0
                            and now - pool.last_used > self._max_idle_time
                        ):
                            logging.info(
                                f"Removing idle connection for node: {node_redis_url}"
                            )
                            await pool.close()
                        else:
                            active_pools.append(pool)
                    self._pools[node_redis_url] = (
                        pools[: self.connection_pools_per_node_at_start] + active_pools
                    )
                    update_pool_metrics(
                        node_redis_url, self._pools[node_redis_url], self._max_idle_time
                    )

    async def _add_new_node_pools(
        self, node_redis_url: str, count: int, timeout_sec: float
    ):
        """Add new Redis connection pools for a node."""
        new_pools = [
            RedisConnection(
                redis_url=node_redis_url,
                pool_size=self.max_connection_size,
                use_cluster=self.use_cluster,
                startup_nodes=self.startup_nodes,
                pool_args=self.pool_args,
            )
            for _ in range(count)
        ]
        await asyncio.gather(
            *[pool.wait_for_ready(timeout_sec=timeout_sec) for pool in new_pools]
        )
        for pool in new_pools:
            pool.last_used = time.time()  # Initialize last used timestamp
        self._pools[node_redis_url].extend(new_pools)
        update_pool_metrics(
            node_redis_url, self._pools[node_redis_url], self._max_idle_time
        )

    def _check_timeout(self, start_time: float, timeout_sec: float):
        """Check if the timeout has been reached."""
        elapsed_time = time.time() - start_time
        remaining_time = timeout_sec - elapsed_time
        if remaining_time <= 0:
            raise NoHealthyPoolsException
        return remaining_time

    async def add_node_pool(
        self, node_redis_url: str, timeout_sec: Union[float, None] = None
    ):
        """Add initial Redis connection pools for a node."""
        if node_redis_url in self._pools:
            return
        if timeout_sec is None:
            timeout_sec = self._default_timeout_sec
        start_time = time.time()
        while True:
            self._check_timeout(start_time, timeout_sec)
            async with self._pools_condition[node_redis_url]:
                if node_redis_url in self._pools:
                    return
                self._check_timeout(start_time, timeout_sec)
                try:
                    await self._add_new_node_pools(
                        node_redis_url, self.connection_pools_per_node_at_start, 1
                    )
                    self._pools_condition[node_redis_url].notify_all()
                    return
                except Exception:
                    self._pools_condition[node_redis_url].notify_all()
                    remaining_time = self._check_timeout(start_time, timeout_sec)
                    try:
                        await asyncio.wait_for(
                            self._pools_condition[node_redis_url].wait(),
                            timeout=remaining_time,
                        )
                    except asyncio.TimeoutError:
                        raise NoHealthyPoolsException(
                            "Timeout while waiting for pools"
                        ) from None

    async def _recover_unhealthy_pools(self):
        """Try to recover unhealthy pools."""
        async with self._lock:
            for node_redis_url, pools in self._pools.items():
                # update_pool_metrics(node_redis_url, pools, self._max_idle_time)
                for pool in pools:
                    state = await pool.health_check()
                    if not pool.health_status:
                        new_pool = RedisConnection(
                            node_redis_url, self.max_connection_size
                        )
                        try:
                            await new_pool.wait_for_ready(
                                timeout_sec=5, step_sec=self._wait_for_ready_step
                            )
                        except NoHealthyPoolsException:
                            continue
                        if new_pool.health_status:
                            pool.pool = new_pool.pool
                            pool.health_status = True
                            logging.warning(
                                {
                                    "message": "Recovered successfully Redis connection pool",
                                    "pool_previous_state": state,
                                    "node_redis_server": node_redis_url,
                                }
                            )
                update_pool_metrics(node_redis_url, pools, self._max_idle_time)

    def is_health_check_running(self):
        return (
            self._health_check_task is not None and not self._health_check_task.done()
        )

    def is_cleanup_running(self):
        return self._cleanup_task is not None and not self._cleanup_task.done()

    def start_health_checks(self):
        if not self.is_health_check_running():
            self._start_health_check_task()

    def start_cleanup(self):
        if not self.is_cleanup_running():
            self._start_cleanup_task()

    def stop_health_checks(self):
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

    def stop_cleanup(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    @asynccontextmanager
    async def get_client(
        self, node_redis_url: str, timeout_sec: Union[float, None] = None
    ):
        """
        Asynchronously get a healthy Redis connection client from the pool for the given node URL.

        Args:
            node_redis_url (str): The URL of the Redis node server.
            timeout_sec (float, optional): The maximum time to wait for a connection to become ready.
                                           If None, it defaults to 10s.

        Yields:
            RedisConnection client: The Redis connection client ready for making operations.

        Raises:
            NoHealthyPoolsException: if no healthy connections are available for the node URL.
            ValueError: if node_redis_url wasn't added before to the pool.
        """
        if timeout_sec is None:
            timeout_sec = self._default_timeout_sec
        start_time = time.time()
        connection = None
        try:
            connection = await self._get_pool(node_redis_url, timeout_sec)
            latency = time.time() - start_time
            update_connection_latency(node_redis_url, latency)
            connection.last_used = time.time()  # Update last-used timestamp
            yield connection.get_client()
        finally:
            await self._release_pool(node_redis_url, connection)

    def _get_least_active_pool(self, node_redis_url: str):
        least_active_pool = None
        min_active_calls = float("inf")
        for pool in self._pools[node_redis_url]:
            if pool.health_status and pool.active_calls < min_active_calls:
                min_active_calls = pool.active_calls
                least_active_pool = pool
        if least_active_pool is None:
            raise NoHealthyPoolsException(
                "No healthy pools available for node Redis URL"
            )
        update_pool_metrics(
            node_redis_url, self._pools[node_redis_url], self._max_idle_time
        )
        return least_active_pool, min_active_calls

    async def _get_pool(self, node_redis_url: str, timeout_sec: float):
        """Get the healthy pool with the least active calls."""
        if node_redis_url not in self._pools:
            raise ValueError("Invalid node Redis URL")
        start_time = time.time()
        while True:
            self._check_timeout(start_time, timeout_sec)
            async with self._pools_condition[node_redis_url]:
                least_active_pool, min_active_calls = self._get_least_active_pool(
                    node_redis_url
                )
                if min_active_calls < self.max_connection_size:
                    least_active_pool.active_calls += 1
                    update_pool_metrics(
                        node_redis_url, self._pools[node_redis_url], self._max_idle_time
                    )
                    return least_active_pool

                self._check_timeout(start_time, timeout_sec)
                try:
                    await self._add_new_node_pools(node_redis_url, 1, 1)
                    self._pools_condition[node_redis_url].notify_all()
                    least_active_pool = self._pools[node_redis_url][-1]
                    logging.info(
                        {
                            "message": "Added new pool for node_redis_url to the pool",
                            "node_redis_server": node_redis_url,
                            "new_total_pools": len(self._pools[node_redis_url]),
                        }
                    )
                    least_active_pool.active_calls += 1
                    update_pool_metrics(
                        node_redis_url, self._pools[node_redis_url], self._max_idle_time
                    )
                    return least_active_pool
                except NoHealthyPoolsException:
                    self._pools_condition[node_redis_url].notify_all()
                    remaining_time = self._check_timeout(start_time, timeout_sec)
                    try:
                        await asyncio.wait_for(
                            self._pools_condition[node_redis_url].wait(),
                            timeout=remaining_time,
                        )
                    except asyncio.TimeoutError:
                        raise NoHealthyPoolsException(
                            "Timeout while waiting for pools"
                        ) from None

    async def _release_pool(self, node_redis_url: str, pool: RedisConnection):
        """Release the pool for a node redis url."""
        async with self._lock:
            for p in self._pools[node_redis_url]:
                if p == pool:
                    p.active_calls -= 1
                    update_pool_metrics(
                        node_redis_url, self._pools[node_redis_url], self._max_idle_time
                    )
                    break

    async def close_node_pools(self, node_redis_url: str):
        """Close pools for the node Redis server URL."""
        async with self._lock:
            if node_redis_url in self._pools:
                for pool in self._pools[node_redis_url]:
                    await pool.close()
                del self._pools[node_redis_url]

    async def close_all_pools(self):
        """Close all pools for all node Redis servers."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                logging.info("Health check task cancelled successfully.")
        async with self._lock:
            for pools in self._pools.values():
                for pool in pools:
                    await pool.close()
            self._pools.clear()

    async def _get_pool_state(self):
        """Get the state of the connection pool."""
        async with self._lock:
            pool_state = {}
            for shard_redis_url, pools in self._pools.items():
                shard_state = {
                    "total_pools": len(pools),
                    "healthy_pools": sum(pool.health_status for pool in pools),
                    "unhealthy_pools": len(pools)
                    - sum(pool.health_status for pool in pools),
                    "active_calls": {
                        i: pool.active_calls for i, pool in enumerate(pools)
                    },
                }
                pool_state[shard_redis_url] = shard_state
            return pool_state

    async def fetch_pool_status(self):
        """Fetch the state of the connection pool and return as a status dictionary."""
        state = await self._get_pool_state()
        status_info = {}
        for node_redis_url, node_state in state.items():
            node_info = {
                "total_pools": node_state["total_pools"],
                "healthy_pools": node_state["healthy_pools"],
                "unhealthy_pools": node_state["unhealthy_pools"],
                "pools": [],
            }
            for pool_index, active_calls in node_state["active_calls"].items():
                node_info["pools"].append(
                    {"index": pool_index, "active_calls": active_calls}
                )
            status_info[node_redis_url] = node_info
        return status_info

    async def _trace_pool_state(self):
        """Trace the state of the connection pool."""
        logging.info("---- trace pool state")
        state = await self._get_pool_state()
        for node_redis_url, node_state in state.items():
            logging.info(f"NodeURL: {node_redis_url}")
            logging.info(f"  Total Pools: {node_state['total_pools']}")
            logging.info(f"  Healthy Pools: {node_state['healthy_pools']}")
            logging.info(f"  Unhealthy Pools: {node_state['unhealthy_pools']}")
            for pool_index, active_calls in node_state["active_calls"].items():
                logging.info(f"  Pool {pool_index}:")
                logging.info(f"    Active Calls: {active_calls}")
            logging.info("")
