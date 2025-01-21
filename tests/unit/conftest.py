import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from redis_manager.redis_manager import RedisManager


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
