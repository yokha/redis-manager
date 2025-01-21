
## **RedisConnection Class API**

The `RedisConnection` class represents an individual connection to a Redis server. It manages connection initialization, health status, and lifecycle.

### **Initialization**

```python
RedisConnection(
    redis_url: str,
    pool_size=DEFAULT_VALUES["max_connection_size"],
    pool_args=None,
    use_cluster=DEFAULT_VALUES["use_redis_cluster"],
    startup_nodes=None,
    logger=None,
)
```

#### **Parameters**
- `redis_url` (str): Redis server URL.
- `pool_size` (int): Maximum connections in the pool.
- `pool_args` (dict): Custom connection pool arguments.
- `use_cluster` (bool): Whether to use Redis cluster mode.
- `startup_nodes` (list): Cluster startup nodes.
- `logger` (logging.Logger): Optional custom logger instance.

---

### **Methods**

#### **wait_for_ready**
Waits for the Redis connection to become ready.

```python
async wait_for_ready(timeout_sec=10, step_sec=0.25, max_retries=5) -> float
```

#### **health_check**
Performs a health check on the Redis connection.

```python
async health_check()
```

#### **get_client**
Retrieves the Redis client instance.

```python
def get_client() -> Redis
```

#### **close**
Closes the Redis connection.

```python
async close()
```

---