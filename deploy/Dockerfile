# FastAPI 镜像（Render 部署，docs/07-deployment-guide.md §1.3）
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# 直接显式安装运行时依赖，避免 pip install .（hatchling 打包 + pyproject 解析）在旧 pip 上的坑
COPY src ./src
COPY config ./config
ENV PYTHONPATH=/app/src
RUN pip install --no-cache-dir \
    fastapi uvicorn pandas numpy akshare litellm "psycopg2-binary" pyyaml pydantic httpx

EXPOSE 8000
# FC 自定义容器监听 FC_SERVER_PORT（默认 9000）；Render 等平台用 PORT
CMD ["sh", "-c", "uvicorn value_agent.main:app --host 0.0.0.0 --port ${FC_SERVER_PORT:-${PORT:-8000}}"]
