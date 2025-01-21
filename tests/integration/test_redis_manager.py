import logging
import pytest

from redis_manager.redis_connection import NoHealthyPoolsException

logging.basicConfig(level=logging.DEBUG)


# Parametrize individual test cases
@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_add_node_pool_success(node_redis_url, redis_pool_manager_fixture):
    """Test adding a node pool successfully for both Redis and Redis Cluster."""
    # Add a node pool by the URL and type (Redis vs. Redis Cluster)
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    assert node_redis_url in manager._pools
    assert (
        len(manager._pools[node_redis_url])
        == manager.connection_pools_per_node_at_start
    )


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_add_existing_node_pool(redis_pool_manager_fixture, node_redis_url):
    """Test adding an existing node pool (should do nothing)."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    initial_pool_count = len(manager._pools[node_redis_url])
    await manager.add_node_pool(node_redis_url)
    assert len(manager._pools[node_redis_url]) == initial_pool_count


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_redis_health_check(node_redis_url, redis_pool_manager_fixture):
    """Test health check of Redis and Redis Cluster pools."""
    manager = redis_pool_manager_fixture
    # # Fixiture healt_ check interval is set to 1s
    # await asyncio.sleep(1)

    # Ensure that the pool's health status is ok
    for pool in manager._pools[node_redis_url]:
        assert pool.health_status is True


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_redis_ping(node_redis_url, redis_pool_manager_fixture):
    """Test ping command to Redis or Redis Cluster."""
    pool_manager = redis_pool_manager_fixture

    # Fetch a client from the pool and perform a ping operation
    async with pool_manager.get_client(node_redis_url) as client:
        assert await client.ping() is True


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_get_client_success(redis_pool_manager_fixture, node_redis_url):
    """Test getting a healthy connection from the pool."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    async with manager.get_client(node_redis_url) as client:
        assert await client.ping() is True


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_value_error_when_pool_does_not_exist(redis_pool_manager_fixture):
    """Test raising ValueError when attempting to get a pool that does not exist."""
    manager = redis_pool_manager_fixture
    with pytest.raises(ValueError, match="Invalid node Redis URL"):
        async with manager.get_client("redis://non-existent-url:6379"):
            pass


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_recover_unhealthy_pools(redis_pool_manager_fixture, node_redis_url):
    """Test recovering unhealthy pools."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    manager._pools[node_redis_url][0].health_status = False
    await manager._recover_unhealthy_pools()
    assert manager._pools[node_redis_url][0].health_status is True


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_close_node_pools(redis_pool_manager_fixture, node_redis_url):
    """Test closing shard pools."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    await manager.close_node_pools(node_redis_url)
    assert node_redis_url not in manager._pools


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_close_all_pools(redis_pool_manager_fixture, node_redis_url):
    """Test closing all pools."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    await manager.close_all_pools()
    assert len(manager._pools) == 0


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_fetch_pool_status(redis_pool_manager_fixture, node_redis_url):
    """Test fetching the pool status."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    status = await manager.fetch_pool_status()
    assert node_redis_url in status
    assert (
        status[node_redis_url]["total_pools"]
        == manager.connection_pools_per_node_at_start
    )


@pytest.mark.parametrize(
    "node_redis_url,use_cluster",
    [
        ("redis://redis:6379", False),  # Standard Redis
        ("redis-cluster-0:6379", True),  # Redis Cluster
        ("redis-cluster-1:6379", True),  # Redis Cluster
        ("redis-cluster-2:6379", True),  # Redis Cluster
    ],
)
@pytest.mark.asyncio
async def test_pool_timeout_on_get(redis_pool_manager_fixture, node_redis_url):
    """Test timeout when trying to get a connection from the pool."""
    manager = redis_pool_manager_fixture
    await manager.add_node_pool(node_redis_url)
    for pool in manager._pools[node_redis_url]:
        pool.health_status = False
    with pytest.raises(NoHealthyPoolsException):
        async with manager.get_client(node_redis_url):
            pass
