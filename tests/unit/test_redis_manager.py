import logging
import time
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from redis_manager.redis_manager import RedisManager
from redis_manager.redis_connection import NoHealthyPoolsException


@pytest.fixture
def mock_redis_connection():
    with patch("redis_manager.redis_manager.RedisConnection") as mock:
        # Configure the mock RedisConnection
        instance = MagicMock()
        instance.wait_for_ready = AsyncMock(
            return_value=None
        )  # Simulate successful readiness
        instance.health_check = AsyncMock(return_value=True)  # Simulate healthy pool
        instance.last_used = time.time() - 10  # Set realistic `last_used`
        instance.close = AsyncMock(return_value=None)  # Simulate successful close
        instance.health_status = True  # Simulate a healthy pool
        instance.active_calls = 0  # Start with no active calls
        instance.get_client = MagicMock(return_value="mock_client")  # Mock get_client
        mock.return_value = instance
        yield mock


@pytest.fixture
async def redis_manager_with_health_checks():
    manager = RedisManager(health_check_interval=1, cleanup_interval=1)
    manager.start_health_checks()
    manager.start_cleanup()
    yield manager
    manager.stop_health_checks()
    manager.stop_cleanup()
    await manager.close_all_pools()  # Ensure all resources are cleaned up


@pytest.mark.asyncio
async def test_add_node_pool_success(
    mock_redis_connection, redis_manager_with_health_checks
):
    """Test successfully adding a node pool."""
    manager = redis_manager_with_health_checks
    await manager.add_node_pool("redis://localhost")
    assert "redis://localhost" in manager._pools
    assert len(manager._pools["redis://localhost"]) == 1

    # Verify the mock's wait_for_ready was called
    mock_redis_connection.return_value.wait_for_ready.assert_called_once()


@pytest.mark.asyncio
async def test_add_node_pool_existing_node(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test adding a node pool that already exists."""
    manager = redis_manager_with_health_checks
    await manager.add_node_pool("redis://localhost")
    await manager.add_node_pool("redis://localhost")  # add twice

    initial_pool_count = len(manager._pools["redis://localhost"])

    # Add the same node again
    await manager.add_node_pool("redis://localhost")
    assert len(manager._pools["redis://localhost"]) == initial_pool_count

    # Assert that the pool was not recreated
    mock_redis_connection.assert_called_once_with(
        redis_url="redis://localhost",
        pool_size=manager.max_connection_size,
        use_cluster=manager.use_cluster,
        startup_nodes=manager.startup_nodes,
        pool_args=manager.pool_args,
    )


@pytest.mark.asyncio
async def test_get_client_success(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test getting a client from a node pool."""
    manager = redis_manager_with_health_checks
    await manager.add_node_pool("redis://localhost")

    async with manager.get_client("redis://localhost") as client:
        assert client == "mock_client"

    # Assert that `get_client` was called
    mock_redis_connection.return_value.get_client.assert_called_once()


@pytest.mark.asyncio
async def test_add_node_pool_unhelthy_connection(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test getting a client when no healthy pools are available."""
    # Mock connection to always fail health checks
    mock_connection = MagicMock()
    mock_connection.wait_for_ready = AsyncMock(side_effect=NoHealthyPoolsException)
    mock_redis_connection.return_value = mock_connection

    manager = redis_manager_with_health_checks

    # Attempt to add a node pool and expect it to raise NoHealthyPoolsException
    with pytest.raises(
        NoHealthyPoolsException, match="Timeout while waiting for pools"
    ):
        await manager.add_node_pool("redis://localhost")


@pytest.mark.asyncio
async def test_close_node_pools(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test closing specific node pools."""
    mock_pool = mock_redis_connection.return_value
    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    await manager.close_node_pools("redis://localhost")
    assert "redis://localhost" not in manager._pools
    mock_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_all_pools(redis_manager_with_health_checks, mock_redis_connection):
    """Test closing all pools."""
    mock_connection = MagicMock()
    mock_connection.close = AsyncMock()
    mock_connection.wait_for_ready = AsyncMock()
    mock_redis_connection.return_value = mock_connection

    manager = redis_manager_with_health_checks
    await manager.add_node_pool("redis://localhost")
    await manager.close_all_pools()
    assert len(manager._pools) == 0
    mock_connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_runs(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test periodic health checks."""
    mock_pool = mock_redis_connection.return_value

    # Simulate the health_check method updating health_status
    async def health_check_side_effect():
        if not hasattr(mock_pool, "_call_count"):
            mock_pool._call_count = 0
        if mock_pool._call_count == 0:
            mock_pool.health_status = True
        else:
            mock_pool.health_status = False
        mock_pool._call_count += 1

    mock_pool.health_check = AsyncMock(side_effect=health_check_side_effect)

    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    await asyncio.sleep(2)  # Let health checks run at least once
    manager.stop_health_checks()

    # Assert the final health_status
    assert mock_pool.health_status is False


@pytest.mark.asyncio
async def test_start_and_stop_health_checks(redis_manager_with_health_checks):
    """Test starting and stopping health checks."""
    manager = redis_manager_with_health_checks
    # Ensure the health check task starts automatically
    assert manager._health_check_task is not None
    assert not manager._health_check_task.done()

    # Stop health checks
    manager.stop_health_checks()
    assert manager._health_check_task is None


@pytest.mark.asyncio
async def test_recover_unhealthy_pools(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test recovering unhealthy pools."""
    mock_pool = mock_redis_connection.return_value

    async def health_check_side_effect():
        if not hasattr(mock_pool, "_call_count"):
            mock_pool._call_count = 0
        if mock_pool._call_count == 0:
            mock_pool.health_status = False
        else:
            mock_pool.health_status = True
        mock_pool._call_count += 1

    mock_pool.health_check = AsyncMock(side_effect=health_check_side_effect)

    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    await manager._recover_unhealthy_pools()

    mock_pool.health_check.assert_called_once()  # Ensure health check was called
    assert mock_pool.health_status is True  # Check recovery


@pytest.mark.asyncio
async def test_recover_unhealthy_pools_success(
    redis_manager_with_health_checks, mocker
):
    """Test _recover_unhealthy_pools successfully recovers a pool."""
    # Mock the original unhealthy pool
    mock_unhealthy_pool = mocker.MagicMock()
    mock_unhealthy_pool.health_status = False
    mock_unhealthy_pool.health_check = mocker.AsyncMock(return_value=False)
    mock_unhealthy_pool.close = mocker.AsyncMock(return_value=None)  # Mock awaitable
    mock_unhealthy_pool.last_used = (
        time.time() - 100
    )  # Simulate last used 100 seconds ago

    # Mock the new healthy pool
    mock_new_pool = mocker.MagicMock()
    mock_new_pool.health_status = True
    mock_new_pool.pool = "new_pool_instance"
    mock_new_pool.wait_for_ready = mocker.AsyncMock(return_value=None)  # Mock awaitable
    mock_new_pool.close = mocker.AsyncMock(return_value=None)  # Mock awaitable
    mock_new_pool.last_used = time.time() - 100  # Simulate last used 100 seconds ago

    # Patch RedisConnection to return the new pool
    mocker.patch(
        "redis_manager.redis_manager.RedisConnection", return_value=mock_new_pool
    )

    # Set up the manager and add the unhealthy pool
    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_unhealthy_pool]

    # Call _recover_unhealthy_pools
    await manager._recover_unhealthy_pools()

    # Assert health_check was called on the unhealthy pool
    mock_unhealthy_pool.health_check.assert_called_once()

    # Assert a new pool was created and wait_for_ready was called
    mock_new_pool.wait_for_ready.assert_called_once_with(
        timeout_sec=5, step_sec=manager._wait_for_ready_step
    )

    # Assert the original pool's attributes were updated
    assert mock_unhealthy_pool.pool == "new_pool_instance"
    assert mock_unhealthy_pool.health_status is True


@pytest.mark.asyncio
async def test_get_client_no_healthy_pool(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test getting a client when no healthy pool is available."""
    mock_pool = mock_redis_connection.return_value
    mock_pool.health_status = False

    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    with pytest.raises(NoHealthyPoolsException):
        async with manager.get_client("redis://localhost"):
            pass


@pytest.mark.asyncio
async def test_fetch_pool_status(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test fetching pool status."""
    mock_pool = mock_redis_connection.return_value
    mock_pool.active_calls = 2

    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    # Mock `_get_pool_state` to return expected structure
    manager._get_pool_state = AsyncMock(
        return_value={
            "redis://localhost": {
                "total_pools": 1,
                "healthy_pools": 1,
                "unhealthy_pools": 0,
                "active_calls": {0: 2},
            }
        }
    )

    status = await manager.fetch_pool_status()

    assert status["redis://localhost"]["total_pools"] == 1
    assert status["redis://localhost"]["healthy_pools"] == 1
    assert status["redis://localhost"]["unhealthy_pools"] == 0


@pytest.mark.asyncio
async def test_add_node_pool_invalid(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test adding a node pool with invalid parameters."""
    mock_redis_connection.return_value.wait_for_ready = AsyncMock(
        side_effect=NoHealthyPoolsException("Timeout while waiting for pools")
    )
    manager = redis_manager_with_health_checks

    with pytest.raises(NoHealthyPoolsException):
        await manager.add_node_pool("redis://invalid-url")  # Line 152


@pytest.mark.asyncio
async def test_fetch_pool_status_empty(redis_manager_with_health_checks):
    """Test fetching pool status when there are no pools."""
    manager = redis_manager_with_health_checks
    status = await manager.fetch_pool_status()
    assert status == {}


@pytest.mark.asyncio
async def test_add_node_pool_retry_failure(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test retry logic when retries exhaust."""
    mock_redis_connection.return_value.wait_for_ready = AsyncMock(
        side_effect=[Exception("Retry failure")] * 3
    )

    manager = redis_manager_with_health_checks
    manager.connection_pools_per_node_at_start = 2

    with pytest.raises(NoHealthyPoolsException):
        await manager.add_node_pool("redis://localhost")


@pytest.mark.asyncio
async def test_close_node_pool_not_exist(redis_manager_with_health_checks):
    """Test closing a node pool that does not exist."""
    manager = redis_manager_with_health_checks
    await manager.close_node_pools("redis://nonexistent-node")
    # Ensure no exceptions and state remains consistent
    assert "redis://nonexistent-node" not in manager._pools


@pytest.mark.asyncio
async def test_periodic_cleanup(redis_manager_with_health_checks):
    """Test periodic cleanup of idle connections."""
    # Simulate three pools with different states
    active_pool1 = MagicMock(last_used=time.time() - 100, active_calls=1)  # Active
    active_pool2 = MagicMock(last_used=time.time() - 301, active_calls=1)  # Active
    idle_pool2 = MagicMock(last_used=time.time() - 400, active_calls=0)  # Idle
    idle_pool3 = MagicMock(last_used=time.time() - 600, active_calls=0)  # Idle

    # Mock close method for pools
    active_pool1.close = AsyncMock()
    active_pool2.close = AsyncMock()
    idle_pool2.close = AsyncMock()
    idle_pool3.close = AsyncMock()
    active_pool1.health_check = AsyncMock(return_value=True)
    active_pool2.health_check = AsyncMock(return_value=True)
    idle_pool2.health_check = AsyncMock(return_value=True)
    idle_pool3.health_check = AsyncMock(return_value=True)

    # Add pools to the manager
    manager = redis_manager_with_health_checks
    manager.connection_pools_per_node_at_start = (
        1  # Cleanup always keep the pools at start
    )
    manager._pools["redis://localhost"] = [
        active_pool1,
        active_pool2,
        idle_pool2,
        idle_pool3,
    ]

    # Allow cleanup to run
    await asyncio.sleep(manager._cleanup_interval + 1)
    manager.stop_cleanup()  # Stop the periodic cleanup task

    # Check that idle pools are removed
    assert (
        len(manager._pools["redis://localhost"]) == 2
    )  # Only active_pool1 and active_pool2 should remain
    assert active_pool1 in manager._pools["redis://localhost"]
    assert active_pool2 in manager._pools["redis://localhost"]

    # Verify that close was called for idle pools
    active_pool1.close.assert_not_called()  # Active pool should not be closed
    active_pool2.close.assert_not_called()
    idle_pool2.close.assert_called_once()
    idle_pool3.close.assert_called_once()


@pytest.mark.asyncio
async def test_check_timeout_raises_exception(redis_manager_with_health_checks):
    """Test _check_timeout raises NoHealthyPoolsException when timeout is exceeded."""
    manager = redis_manager_with_health_checks
    start_time = time.time() - 5  # Simulate that 5 seconds have already elapsed
    timeout_sec = 3  # Set timeout to 3 seconds

    with pytest.raises(NoHealthyPoolsException):
        manager._check_timeout(start_time, timeout_sec)


@pytest.mark.asyncio
async def test_recover_unhealthy_pools_with_unrecoverable_node(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test _recover_unhealthy_pools handles NoHealthyPoolsException gracefully."""
    mock_pool = mock_redis_connection.return_value

    # Simulate a pool that always fails health checks
    async def health_check_side_effect():
        mock_pool.health_status = False  # Set to unhealthy after health check
        return False

    async def wait_for_ready_side_effect(*args, **kwargs):
        raise NoHealthyPoolsException("Test exception: Node is not recoverable.")

    mock_pool.health_check = AsyncMock(side_effect=health_check_side_effect)
    mock_pool.wait_for_ready = AsyncMock(side_effect=wait_for_ready_side_effect)

    manager = redis_manager_with_health_checks
    manager._pools["redis://localhost"] = [mock_pool]

    # Call _recover_unhealthy_pools and ensure it does not raise exceptions
    await manager._recover_unhealthy_pools()

    # Assert the health check was called
    mock_pool.health_check.assert_called_once()

    # Assert wait_for_ready was called and raised NoHealthyPoolsException
    mock_pool.wait_for_ready.assert_called_once()

    # Ensure the pool's health_status remains unchanged (False)
    assert not mock_pool.health_status


@pytest.mark.asyncio
async def test_is_health_check_running(redis_manager_with_health_checks):
    """Test is_health_check_running method."""
    manager = redis_manager_with_health_checks

    # Ensure the health check task starts automatically
    assert manager._health_check_task is not None
    assert not manager._health_check_task.done()

    # Assert is_health_check_running returns True when the task is running
    assert manager.is_health_check_running() is True

    # Stop health checks
    manager.stop_health_checks()

    # Assert is_health_check_running returns False after stopping the task
    assert manager.is_health_check_running() is False

    # Check behavior when the task is not initialized
    manager._health_check_task = None
    assert manager.is_health_check_running() is False


@pytest.mark.asyncio
async def test_start_health_checks(redis_manager_with_health_checks):
    """Test start_health_checks method."""
    manager = redis_manager_with_health_checks

    # Ensure the health check task starts automatically
    initial_task = manager._health_check_task
    assert initial_task is not None
    assert not initial_task.done()

    # Call start_health_checks when the task is already running
    manager.start_health_checks()
    # Ensure the same task is still running (no new task is created)
    assert manager._health_check_task is initial_task

    # Stop the current health check task
    manager.stop_health_checks()
    assert manager._health_check_task is None

    # Call start_health_checks again to restart the task
    manager.start_health_checks()
    new_task = manager._health_check_task
    assert new_task is not None
    assert new_task != initial_task  # Ensure a new task is created
    assert not new_task.done()

    # Clean up
    manager.stop_health_checks()


@pytest.mark.asyncio
async def test_get_pool_invalid_node(redis_manager_with_health_checks):
    """Test _get_pool method with an invalid node URL."""
    manager = redis_manager_with_health_checks

    # Attempt to get a pool for a node URL not in _pools
    with pytest.raises(ValueError, match="Invalid node Redis URL"):
        await manager._get_pool("redis://invalid-node", timeout_sec=10)


@pytest.mark.asyncio
async def test_get_pool_add_new_node_success(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test _get_pool successfully adding a new pool."""
    manager = redis_manager_with_health_checks
    node_redis_url = "redis://localhost"

    # Add initial pool
    await manager.add_node_pool(node_redis_url)

    # Mock that all existing pools are at max connection size
    for pool in manager._pools[node_redis_url]:
        pool.active_calls = manager.max_connection_size

    # Trigger adding a new pool
    pool = await manager._get_pool(node_redis_url, timeout_sec=10)

    # Assert the new pool is added
    assert (
        len(manager._pools[node_redis_url]) > manager.connection_pools_per_node_at_start
    )

    # Verify that `wait_for_ready` was called twice
    assert mock_redis_connection.return_value.wait_for_ready.call_count == 2


@pytest.mark.asyncio
async def test_get_pool_state(redis_manager_with_health_checks, mock_redis_connection):
    """Test _get_pool_state returns the correct pool state."""
    manager = redis_manager_with_health_checks
    node_redis_url = "redis://localhost"

    # Create mock pools with individual attributes
    mock_pool_1 = MagicMock()
    mock_pool_2 = MagicMock()

    # Configure mock pools
    mock_pool_1.health_status = True
    mock_pool_1.active_calls = 2
    mock_pool_1.close = AsyncMock()

    mock_pool_2.health_status = False
    mock_pool_2.active_calls = 0
    mock_pool_2.close = AsyncMock()

    # Assign pools to manager
    manager._pools[node_redis_url] = [mock_pool_1, mock_pool_2]

    # Call _get_pool_state
    pool_state = await manager._get_pool_state()

    # Validate the results
    assert node_redis_url in pool_state
    node_state = pool_state[node_redis_url]

    assert node_state["total_pools"] == 2
    assert node_state["healthy_pools"] == 1
    assert node_state["unhealthy_pools"] == 1
    assert node_state["active_calls"] == {0: 2, 1: 0}


@pytest.mark.asyncio
async def test_no_healthy_pools_exception_handling(
    redis_manager_with_health_checks, mock_redis_connection
):
    """Test handling of NoHealthyPoolsException and subsequent timeout."""
    manager = redis_manager_with_health_checks
    node_redis_url = "redis://localhost"

    # Mock the RedisConnection to simulate NoHealthyPoolsException
    mock_redis_connection.return_value.wait_for_ready = AsyncMock(
        side_effect=NoHealthyPoolsException("No healthy pools available")
    )

    # Set up a condition where the _pools_condition.wait times out
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(
            NoHealthyPoolsException, match="Timeout while waiting for pools"
        ):
            await manager.add_node_pool(node_redis_url)

    # Ensure the appropriate calls were made
    mock_redis_connection.assert_called_once_with(
        redis_url=node_redis_url,
        pool_size=manager.max_connection_size,
        use_cluster=manager.use_cluster,
        startup_nodes=manager.startup_nodes,
        pool_args=manager.pool_args,
    )
    assert node_redis_url not in manager._pools


@pytest.mark.asyncio
async def test_trace_pool_state(redis_manager_with_health_checks, caplog):
    """Test tracing the state of the connection pool."""
    # Mock Condition.wait in your test setup
    with patch("asyncio.Condition.wait", new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = None  # Simulate successful wait
        manager = redis_manager_with_health_checks
        mock_pool_state = {
            "redis://localhost": {
                "total_pools": 2,
                "healthy_pools": 1,
                "unhealthy_pools": 1,
                "active_calls": {
                    0: 5,
                    1: 0,
                },
            }
        }

        # Mock `_get_pool_state` to return a known state
        manager._get_pool_state = AsyncMock(return_value=mock_pool_state)

        # Capture logging output
        with caplog.at_level(logging.INFO):
            await manager._trace_pool_state()

        # Verify the log messages
        assert "---- trace pool state" in caplog.text
        assert "NodeURL: redis://localhost" in caplog.text
        assert "  Total Pools: 2" in caplog.text
        assert "  Healthy Pools: 1" in caplog.text
        assert "  Unhealthy Pools: 1" in caplog.text
        assert "  Pool 0:" in caplog.text
        assert "    Active Calls: 5" in caplog.text
        assert "  Pool 1:" in caplog.text
        assert "    Active Calls: 0" in caplog.text
