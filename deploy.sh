#!/bin/sh
set -e
cd "$(dirname "$0")"
docker compose up -d --build 2>&1 | tail -20
sleep 12
echo "--- ps ---"
docker ps --filter name=tgflow --format '{{.Names}} | {{.Status}} | {{.Ports}}'
echo "--- health ---"
curl -s --noproxy '*' -o /dev/null -w "HTTP=%{http_code}\n" http://127.0.0.1:18319/api/status
echo "--- logs ---"
docker logs --tail=15 tgflow 2>&1
