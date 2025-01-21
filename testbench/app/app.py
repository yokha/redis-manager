from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from redis_manager.redis_manager import RedisManager
import random
import logging
import asyncio
import logging


class MetricsFilter(logging.Filter):
    def filter(self, record):
        return "GET /metrics HTTP/1.1" not in record.getMessage()

# Apply the filter to the root logger
logging.getLogger("uvicorn.access").addFilter(MetricsFilter())

# Set up basic logging configuration
logging.basicConfig(
    level=logging.INFO,  # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Ensure logs are sent to the console
    ]
)

app = FastAPI(title="RedisManager Stress Test")

node_redis_url = "redis://redis:6379"
redis_manager = RedisManager(connection_pools_per_node_at_start=1, max_connection_size=50, health_check_interval=10, cleanup_interval=30, max_idle_time=25)

# Configuration
INITIAL_NUM_CLIENTS = 20
# Track benchmark metrics
tasks_running = 0
tasks_failed = 0
tasks_completed = 0
tasks_lock = asyncio.Lock()  # Lock for atomic updates to task counters

# Instrument Prometheus metrics
Instrumentator().instrument(app).expose(app)


@app.on_event("startup")
async def startup_event():
    """Initialize RedisManager with a node pool on startup."""
    try:
        await redis_manager.add_node_pool(node_redis_url=node_redis_url, timeout_sec=5)
        redis_manager.start_cleanup()
        asyncio.create_task(run_benchmark())
    except Exception as e:
        logging.info(f"[Startup] Failed to initialize RedisManager: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Close RedisManager pools gracefully on shutdown."""
    try:
        await RedisManager.stop_cleanup()
        await redis_manager.stop_health_checks()
        await redis_manager.close_all_pools()
        logging.info("[Shutdown] RedisManager pools closed successfully.")
    except Exception as e:
        logging.error(f"[Shutdown] Error closing RedisManager: {e}")


async def simulate_job(client_id: int, iteration: int):
    """Simulate a fake job with a Redis client."""
    global tasks_running, tasks_failed, tasks_completed
    async with tasks_lock:
        tasks_running += 1
    try:
        async with redis_manager.get_client(node_redis_url) as client:
            key = f"iteration_{iteration}_client_{client_id}"
            value = f"Hello from client {client_id}"

            # Perform SET operation
            await client.set(key, value)
            logging.info(f"[Iteration {iteration}] [Client {client_id}] Set key: {key}")

            # Simulate random workload
            await asyncio.sleep(random.choice([2, 3, 6, 10]))

            # Clean up the key
            await client.delete(key)
            logging.info(f"[Iteration {iteration}] [Client {client_id}] Deleted key: {key}")
            async with tasks_lock:
                tasks_completed += 1
    except Exception as e:
        async with tasks_lock:
            tasks_failed += 1
        logging.error(f"[Iteration {iteration}] [Client {client_id}] Error: {str(e)}")
    finally:
        async with tasks_lock:
            tasks_running -= 1


async def run_benchmark():
    """Run the RedisManager benchmark in a loop."""
    iteration = 1
    num_clients = INITIAL_NUM_CLIENTS
    await asyncio.sleep(15)
    while True:
        n = num_clients + random.choice([300, 500])
        if n >= 1000:
            num_clients = 1
        else:
            num_clients = n
        logging.info(f"--- Starting benchmark iteration {iteration} num_clients={num_clients} ---")

        # Launch parallel tasks
        tasks = [simulate_job(client_id=i, iteration=iteration) for i in range(num_clients)]
        try:
            await asyncio.gather(*tasks, return_exceptions=False)
        except Exception as e:
            logging.error(f"Critical error during benchmark iteration {iteration}: {str(e)}")

        # Print statistics
        async with tasks_lock:
            logging.info(f"--- Iteration {iteration} Completed ---")
            logging.info(f"Tasks Running: {tasks_running}, Completed: {tasks_completed}, Failed: {tasks_failed}")

        # Pause before the next iteration
        if num_clients != 1:
            await asyncio.sleep(11)
        else:
            await asyncio.sleep(70) # Pool will shrink
        iteration += 1
