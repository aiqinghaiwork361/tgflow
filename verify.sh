#!/bin/sh
set -e
cd /vol2/1000/share/file/tgflow
docker build \
  --build-arg PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/ \
  -t tgflow:local .
echo "--- core in container ---"
docker run --rm tgflow:local
echo "--- e2e in container ---"
docker run --rm --entrypoint python tgflow:local tests/test_e2e.py
