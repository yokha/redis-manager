import logging
from unittest.mock import AsyncMock, call, patch
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.asyncio.cluster import ClusterNode
from redis_manager.redis_connection import (
    RedisConnection,
    NoHealthyPoolsException,
    InvalidPoolArguments,
)


@pytest.mark.asyncio
@patch("redis_manager.redis_connection.Redis.ping", new_callable=AsyncMock)
async def test_wait_for_ready_success(mock_ping):
    mock_ping.return_value = True

    conn = RedisConnection(redis_url="redis://localhost", pool_size=5)
    duration = await conn.wait_for_ready(timeout_sec=10)
    assert conn.health_status is True
    assert duration > 0


@pytest.mark.asyncio
@patch("redis_manager.redis_connection.Redis.ping", new_callable=AsyncMock)
async def test_wait_for_ready_timeout(mock_ping):
    mock_ping.side_effect = RedisConnectionError

    conn = RedisConnection(redis_url="redis://localhost", pool_size=5)
    with pytest.raises(NoHealthyPoolsException):
        await conn.wait_for_ready(timeout_sec=2)


@pytest.mark.asyncio
@patch("redis_manager.redis_connection.Redis.ping", new_callable=AsyncMock)
async def test_health_check(mock_ping):
    mock_ping.return_value = True

    conn = RedisConnection(redis_url="redis://localhost", pool_size=5)
    await conn.health_check()
    assert conn.health_status is True

    mock_ping.side_effect = RedisConnectionError
    await conn.health_check()
    assert conn.health_status is False


@pytest.mark.asyncio
@patch("redis_manager.redis_connection.Redis.aclose", new_callable=AsyncMock)
async def test_close(mock_aclose):
    conn = RedisConnection(redis_url="redis://localhost", pool_size=5)
    await conn.close()
    mock_aclose.assert_called_once()
    assert conn.health_status is False


def test_invalid_pool_arguments():
    invalid_args = {"invalid_key": "value"}
    with pytest.raises(InvalidPoolArguments):
        RedisConnection(
            redis_url="redis://localhost", pool_size=5, pool_args=invalid_args
        )


def test_merge_pool_args_invalid_keys():
    """Test _merge_pool_args raises InvalidPoolArguments for invalid keys."""
    defaults = {"valid_key": "default_value"}
    custom = {"invalid_key": "value"}
    valid_keys = {"valid_key"}

    conn = RedisConnection(redis_url="redis://localhost")
    with pytest.raises(
        InvalidPoolArguments, match="Invalid pool arguments: invalid_key"
    ):
        conn._merge_pool_args(defaults, custom, valid_keys)


def test_merge_pool_args_invalid_arguments():
    """Test _merge_pool_args raises InvalidPoolArguments for invalid keys."""
    defaults = {"key1": "default_value"}
    custom_args = {"invalid_key": "value"}
    valid_keys = {"key1"}

    with pytest.raises(
        InvalidPoolArguments, match="Invalid pool arguments: invalid_key"
    ):
        RedisConnection._merge_pool_args(None, defaults, custom_args, valid_keys)


def test_update_pool_connection_duration():
    """Test _update_pool_connection_duration indirectly via logging."""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.DEBUG)

    with patch.object(logger, "debug") as mock_debug:
        conn = RedisConnection(redis_url="redis://localhost", logger=logger)
        conn._update_pool_connection_duration()

        # Assert the specific call we are interested in
        expected_message = "Connection duration updated: 0s"
        assert call(expected_message) in mock_debug.call_args_list


@pytest.mark.asyncio
async def test_health_check_failure():
    """Test health_check sets health_status to False on failure."""
    with patch(
        "redis_manager.redis_connection.Redis.ping", new_callable=AsyncMock
    ) as mock_ping:
        mock_ping.side_effect = RedisConnectionError("Ping failed")
        conn = RedisConnection(redis_url="redis://localhost")
        await conn.health_check()
        assert conn.health_status is False


def test_merge_pool_args_invalid_keys_refined():
    """Test _merge_pool_args for invalid custom pool arguments."""
    defaults = {"valid_key": "default_value"}
    custom = {"invalid_key": "some_value"}
    valid_keys = {"valid_key"}

    conn = RedisConnection(redis_url="redis://localhost")
    with pytest.raises(
        InvalidPoolArguments, match="Invalid pool arguments: invalid_key"
    ):
        conn._merge_pool_args(defaults, custom, valid_keys)


def test_merge_pool_args_valid_keys():
    """Test _merge_pool_args correctly merges valid arguments."""
    defaults = {"valid_key": "default_value"}
    custom = {"valid_key": "custom_value"}
    valid_keys = {"valid_key"}

    conn = RedisConnection(redis_url="redis://localhost")
    result = conn._merge_pool_args(defaults, custom, valid_keys)
    assert result == {"valid_key": "custom_value"}


@pytest.mark.asyncio
async def test_health_check_failure_refined():
    """Test health_check sets health_status to False on failure."""
    conn = RedisConnection(redis_url="redis://localhost")

    with patch.object(
        conn.redis_client,
        "ping",
        AsyncMock(side_effect=RedisConnectionError("Ping failed")),
    ):
        await conn.health_check()

    assert conn.health_status is False


@pytest.mark.asyncio
async def test_health_check_failure_debug():
    """Test health_check sets health_status to False on failure."""
    conn = RedisConnection(redis_url="redis://localhost")

    with patch.object(
        conn.redis_client,
        "ping",
        AsyncMock(side_effect=RedisConnectionError("Ping failed")),
    ):
        await conn.health_check()

    assert conn.health_status is False


@pytest.mark.asyncio
async def test_health_check_success():
    """Test health_check sets health_status to True on success."""
    conn = RedisConnection(redis_url="redis://localhost")

    with patch.object(conn.redis_client, "ping", AsyncMock(return_value=True)):
        await conn.health_check()

    assert conn.health_status is True
