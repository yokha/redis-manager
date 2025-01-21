import pytest_asyncio
from redis.cluster import ClusterNode
from redis_manager.redis_manager import RedisManager


@pytest_asyncio.fixture
async def redis_pool_manager_fixture(node_redis_url, use_cluster):
    """Fixture to initialize RedisConnectionPoolManager for Redis and Redis Cluster."""
    if use_cluster:
        # redis_cluster_host = "127.0.0.1"  # Docker container name
        redis_cluster_nodes = [
            ClusterNode("redis-cluster-0", port=6379),
            ClusterNode("redis-cluster-1", port=6379),
            ClusterNode("redis-cluster-2", port=6379),
        ]
    else:
        redis_cluster_nodes = None  # For standard Redis, cluster nodes are not used

    # Initialize the RedisConnectionPoolManager with appropriate settings
    manager = RedisManager(
        connection_pools_per_node_at_start=2,
        max_connection_size=10,
        use_cluster=use_cluster,
        startup_nodes=redis_cluster_nodes if use_cluster else None,
        health_check_interval=1,
    )

    # Add the shard pool for either Redis or Redis Cluster
    await manager.add_node_pool(node_redis_url)
    yield manager
    await manager.close_all_pools()
