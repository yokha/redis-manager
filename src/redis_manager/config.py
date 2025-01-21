import socket
import os


DEFAULT_POOL_OPTIONS = {
    # "connection_class": None,  # Set in runtime to avoid circular import
    "socket_keepalive": True,
    "socket_keepalive_options": {
        (
            socket.TCP_KEEPIDLE
            if hasattr(socket, "TCP_KEEPIDLE")
            else socket.TCP_KEEPALIVE
        ): 60,  # KEEPIDLE for Linux, KEEPALIVE for macOS
        socket.TCP_KEEPINTVL: 10,
        socket.TCP_KEEPCNT: 3,
    },
    "decode_responses": True,
    "retry_on_timeout": True,
    "health_check_interval": 60,
    "socket_connect_timeout": 5,
}

DEFAULT_CLUSTER_POOL_OPTIONS = {
    "decode_responses": True,
    "health_check_interval": 60,
    "socket_connect_timeout": 5,
    "socket_keepalive": True,
    "ssl": False,  # Use an environment variable for default
}

VALID_POOL_ARGS = set(DEFAULT_POOL_OPTIONS.keys())
VALID_CLUSTER_ARGS = {
    "require_full_coverage",
    "read_from_replicas",
    "reinitialize_steps",
    "cluster_error_retry_attempts",
    "connection_error_retry_attempts",
    *VALID_POOL_ARGS,  # Reuse keys
}

# Prometheus Metric Names
METRIC_NAMES = {
    "redis_pool_size": os.getenv("REDIS_POOL_SIZE_METRIC", "redis_pool_size"),
    "redis_pool_active": os.getenv("REDIS_POOL_ACTIVE_METRIC", "redis_pool_active"),
    "redis_pool_idle": os.getenv("REDIS_POOL_IDLE_METRIC", "redis_pool_idle"),
    "redis_pool_healthy": os.getenv("REDIS_POOL_HEALTHY_METRIC", "redis_pool_healthy"),
    "redis_pool_unhealthy": os.getenv(
        "REDIS_POOL_UNHEALTHY_METRIC", "redis_pool_unhealthy"
    ),
    "redis_connections_created": os.getenv(
        "REDIS_CONNECTIONS_CREATED_METRIC", "redis_connections_created"
    ),
    "redis_failed_connections": os.getenv(
        "REDIS_FAILED_CONNECTIONS_METRIC", "redis_failed_connections"
    ),
    "redis_connection_latency_seconds": os.getenv(
        "REDIS_CONNECTION_LATENCY_METRIC", "redis_connection_latency_seconds"
    ),
    "redis_idle_cleanup_events": os.getenv(
        "REDIS_IDLE_CLEANUP_METRIC", "redis_idle_cleanup_events"
    ),
}

DEFAULT_VALUES = {
    "max_connection_size": int(os.getenv("MAX_CONNECTION_SIZE", "50")),
    "use_redis_cluster": bool(os.getenv("USE_REDIS_CLUSTER", "False")),
    "health_check_interval": float(os.getenv("HEALTH_CHECK_INTERVAL", "60")),
    "cleanup_interval": float(os.getenv("CLEANUP_INTERVAL", "120")),
    "max_idle_time": float(os.getenv("MAX_IDLE_TIME", "180")),
}
