VOLUMES := $(shell docker volume ls --format '{{.Name}}' | grep redis-cluster)

# Bring up the Docker Compose services and wait for Redis to be ready
docker-up:
	@docker-compose up -d --build --remove-orphans --force-recreate redis redis-cluster-0 redis-cluster-1 redis-cluster-2  >/dev/null 2>&1
	@$(MAKE) --no-print-directory wait-for-redis
	@$(MAKE) create-cluster

# Tear down the Docker Compose services
docker-down:
	@docker-compose down --remove-orphans -v >/dev/null 2>&1

# Stop the services and remove named volumes
docker-clean: docker-down
	@if [ -n "$(VOLUMES)" ]; then \
	    echo "Removing volumes: $(VOLUMES)"; \
	    docker volume rm -f $(VOLUMES) >/dev/null 2>&1 || true; \
	else \
	    echo "No volumes to remove."; \
	fi

# Stop, remove volumes, and start fresh, waiting for Redis to be ready
docker-reset: docker-clean docker-up

# Show logs for the Docker Compose services
docker-logs:
	docker-compose logs -f

# Show logs for a specific service
docker-logs-%:
	docker-compose logs -f $(patsubst docker-logs-%, %, $@)

# Wait for Redis readiness
wait-for-redis:
	@echo "Waiting for Redis to be ready..."
	@until docker exec redis-cluster-0 redis-cli ping | grep PONG; do \
	    echo "Redis is not ready yet. Retrying in 2 seconds..."; \
	    sleep 2; \
	done
	@echo "Redis is ready."

# Create Redis cluster
create-cluster:
	@bash ./create_redis_cluster.sh >/dev/null 2>&1

docker-test-runner:
	@docker-compose run --no-deps --rm test-runner
