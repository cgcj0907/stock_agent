# FastAPI 镜像（Render 部署，docs/07-deployment-guide.md §1.3）
# 国内构建直连 Docker Hub 常报 EOF/超时，可用镜像加速覆盖基础镜像：
#   docker build -f deploy/Dockerfile \
#     --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim \
#     -t registry.cn-chengdu.aliyuncs.com/zgy_20223090903005/value-agent:latest .
# Render 等海外平台保持默认 docker.io，无需任何改动。
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# 先装依赖再拷代码：只有依赖变化才重跑 pip（代码改动只触发秒级 COPY），
# 且显式装运行时依赖避免 pip install .（hatchling/pyproject 解析）在旧 pip 上的坑
ENV PYTHONPATH=/app/src
# 国内/香港网络用清华 PyPI 镜像，下载快且稳（也可换 aliyun：https://mirrors.aliyun.com/pypi/simple）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi uvicorn pandas numpy akshare litellm "psycopg2-binary" pyyaml pydantic httpx
COPY src ./src
COPY config ./config

EXPOSE 8000
# FC 自定义容器监听 FC_SERVER_PORT（默认 9000）；Render 等平台用 PORT
CMD ["sh", "-c", "uvicorn value_agent.main:app --host 0.0.0.0 --port ${FC_SERVER_PORT:-${PORT:-8000}}"]
