#!/bin/bash

set -xe

# Build cluster creation command
echo "Creating Redis cluster..."
# Inside create_cluster.sh
docker exec redis-cluster-0 redis-cli --cluster create redis-cluster-0:6379 redis-cluster-1:6379 redis-cluster-2:6379 --cluster-replicas 0 --cluster-yes

# sleep 2

# Test connectivity using Redis PING command
echo "Testing connectivity between Redis cluster nodes..."
docker exec redis-cluster-0 redis-cli -h redis-cluster-1 -p 6379 ping
docker exec redis-cluster-0 redis-cli -h redis-cluster-2 -p 6379 ping
docker exec redis-cluster-1 redis-cli -h redis-cluster-0 -p 6379 ping
docker exec redis-cluster-1 redis-cli -h redis-cluster-2 -p 6379 ping
docker exec redis-cluster-2 redis-cli -h redis-cluster-1 -p 6379 ping
docker exec redis-cluster-2 redis-cli -h redis-cluster-0 -p 6379 ping

# docker ps -a      
# docker inspect $(docker ps -q)

echo "Cluster created successfully."
