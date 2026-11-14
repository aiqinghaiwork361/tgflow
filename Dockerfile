FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TGFLOW_HOME=/app \
    TGFLOW_PORT=18319 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

COPY requirements.txt .
# CN network: pypi direct is slow/blocked -> use Aliyun mirror.
# BuildKit does NOT inherit the daemon proxy, so pass it explicitly.
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
RUN pip install --no-cache-dir -i ${PIP_INDEX} -r requirements.txt

COPY tgflow ./tgflow
COPY examples ./examples
COPY tests ./tests
COPY plugins ./plugins

RUN mkdir -p /app/data /app/tgflow/web/templates \
 && touch /app/tgflow.log

EXPOSE 18319
CMD ["python", "-m", "tgflow.web.app"]
