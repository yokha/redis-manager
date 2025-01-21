
## **RedisManager Class API**

The `RedisManager` class provides a high-level interface for managing Redis connections across multiple nodes or clusters. It handles connection pooling, periodic health checks, and idle connection cleanup.

### **Initialization**

```python
RedisManager(
    connection_pools_per_node_at_start=1,
    max_connection_size=DEFAULT_VALUES["max_connection_size"],
    pool_args=None,
    use_cluster=DEFAULT_VALUES["use_redis_cluster"],
    startup_nodes=None,
    health_check_interval=DEFAULT_VALUES["health_check_interval"],
    cleanup_interval=DEFAULT_VALUES["cleanup_interval"],
    max_idle_time=DEFAULT_VALUES["max_idle_time"],
)
```

#### **Parameters**
- `connection_pools_per_node_at_start` (int): Initial number of pools per node.
- `max_connection_size` (int): Maximum connections per pool.
- `pool_args` (dict): Custom connection pool arguments.
- `use_cluster` (bool): Whether to use Redis cluster mode.
- `startup_nodes` (list): Startup nodes for Redis Cluster.
- `health_check_interval` (float): Interval for periodic health checks.
- `cleanup_interval` (float): Interval for cleaning idle connections.
- `max_idle_time` (float): Maximum idle time for connections before cleanup.

---

### **Methods**

#### **add_node_pool**
Adds a new Redis node to the pool.

```python
async add_node_pool(node_redis_url: str, timeout_sec: float = None)
```

#### **get_client**
Provides a context-managed Redis client for the specified node.

```python
@asynccontextmanager
async def get_client(node_redis_url: str, timeout_sec: float = None)
```

#### **fetch_pool_status**
Fetches the current status of all connection pools.

```python
async fetch_pool_status() -> dict
```

#### **start_health_checks**
Starts the periodic health check task.

```python
def start_health_checks()
```

#### **stop_health_checks**
Stops the periodic health check task.

```python
def stop_health_checks()
```

#### **start_cleanup**
Starts the periodic idle connection cleanup task.

```python
def start_cleanup()
```

#### **stop_cleanup**
Stops the periodic cleanup task.

```python
def stop_cleanup()
```

#### **close_node_pools**
Closes all connection pools for a specific node.

```python
async close_node_pools(node_redis_url: str)
```

#### **close_all_pools**
Closes all connection pools for all nodes.

```python
async close_all_pools()
```
---


## **Example Usage**

```python
import asyncio
from redis_manager.redis_manager import RedisManager, NoHealthyPoolsException

async def main():
    manager = RedisManager(connection_pools_per_node_at_start=2)

    # Add a Redis node to the manager
    await manager.add_node_pool("redis://localhost")

    # Start cleanup
    manager.start_cleanup()

    # Perform operations using a connection from the pool
    async with manager.get_client("redis://localhost") as client:
        await client.ping()

    # Stop tasks and close pools
    manager.stop_health_checks()
    manager.stop_cleanup()
    await manager.close_all_pools()

# Run the example
asyncio.run(main())
```
---