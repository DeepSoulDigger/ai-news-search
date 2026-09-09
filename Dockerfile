# 人工智能报道检索平台 · 服务器版镜像
# 构建:  docker build -t ai-news-search .
# 运行:  见 docker-compose.yml(推荐)或
#        docker run -d --name ai-news-search -p 8765:8765 \
#          -v $(pwd)/data:/app/data -v $(pwd)/config.json:/app/config.json:ro ai-news-search
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 源码与默认配置(数据与配置均可被挂载覆盖)
COPY src/ /app/src/
COPY config.json /app/config.json

# 镜像不含 data,由卷挂载提供;先建目录保证未挂载时也能空跑
RUN mkdir -p /app/data

EXPOSE 8765

# 非 root 运行
RUN useradd -r -s /usr/sbin/nologin appuser && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/config', timeout=2)" || exit 1

CMD ["python", "src/serve.py"]
