# FastAPI 镜像（Render 部署，docs/07-deployment-guide.md §1.3）
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .

# 免费数据源（AkShare：新浪/东财/百度）
RUN pip install --no-cache-dir akshare

EXPOSE 8000
# FC 自定义容器监听 FC_SERVER_PORT（默认 9000）；Render 等平台用 PORT
CMD ["sh", "-c", "uvicorn value_agent.main:app --host 0.0.0.0 --port ${FC_SERVER_PORT:-${PORT:-8000}}"]
