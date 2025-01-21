"""
Prometheus metrics definitions for Redis pool manager.

This module defines and initializes various Prometheus metrics used for monitoring the
performance.
"""

import time
from typing import List
from redis.asyncio import Redis
from prometheus_client import Counter, Gauge, Histogram
from .config import METRIC_NAMES

# Metrics Definitions
redis_pool_size = Gauge(
    METRIC_NAMES["redis_pool_size"],
    "Total number of connection pools",
    ["node_redis_url"],
)
redis_pool_active = Gauge(
    METRIC_NAMES["redis_pool_active"],
    "Number of active connections in the pool",
    ["node_redis_url"],
)
redis_pool_idle = Gauge(
    METRIC_NAMES["redis_pool_idle"],
    "Number of idle connections in the pool",
    ["node_redis_url"],
)
redis_pool_healthy = Gauge(
    METRIC_NAMES["redis_pool_healthy"], "Number of healthy pools", ["node_redis_url"]
)
redis_pool_unhealthy = Gauge(
    METRIC_NAMES["redis_pool_unhealthy"],
    "Number of unhealthy pools",
    ["node_redis_url"],
)
redis_connections_created = Counter(
    METRIC_NAMES["redis_connections_created"],
    "Total number of connections created",
    ["node_redis_url"],
)
redis_failed_connections = Counter(
    METRIC_NAMES["redis_failed_connections"],
    "Total number of failed connection attempts",
    ["node_redis_url"],
)
redis_connection_latency_seconds = Histogram(
    METRIC_NAMES["redis_connection_latency_seconds"],
    "Connection acquisition latency in seconds",
    ["node_redis_url"],
)
redis_idle_cleanup_events = Counter(
    METRIC_NAMES["redis_idle_cleanup_events"],
    "Total number of idle cleanup events",
    ["node_redis_url"],
)


def update_pool_metrics(node_redis_url: str, pools: List[Redis], max_idle_time: float):
    current_time = time.time()
    total_pools = len(pools)
    active_connections = sum(pool.active_calls for pool in pools)
    idle_connections = sum(
        1 for pool in pools if current_time - pool.last_used >= max_idle_time
    )
    healthy_pools = sum(pool.health_status for pool in pools)
    unhealthy_pools = len(pools) - healthy_pools
    redis_pool_size.labels(node_redis_url=node_redis_url).set(total_pools)
    redis_pool_active.labels(node_redis_url=node_redis_url).set(active_connections)
    redis_pool_healthy.labels(node_redis_url=node_redis_url).set(healthy_pools)
    redis_pool_unhealthy.labels(node_redis_url=node_redis_url).set(unhealthy_pools)
    redis_pool_idle.labels(node_redis_url=node_redis_url).set(idle_connections)


def update_connection_latency(node_redis_url: str, latency: float):
    redis_connection_latency_seconds.labels(node_redis_url=node_redis_url).observe(
        latency
    )


def update_failed_connections_attempts(node_redis_url: str):
    redis_failed_connections.labels(node_redis_url=node_redis_url).inc()
