FROM python:3.12-slim

WORKDIR /app

# 依赖
RUN pip install --no-cache-dir flask gunicorn requests

# 源码（每次构建新版本时重新 COPY）
COPY . .

# 媒体上传目录
RUN mkdir -p /app/uploads /app/data

# 环境变量默认值（可运行时覆盖）
ENV CONFIG_FILE=/data/config.json \
    UPLOAD_DIR=/app/uploads \
    DATA_DIR=/app/data \
    LEASE_FILE=/tmp/dhcp.leases \
    MAX_UPLOAD_MB=500 \
    CLEANUP_DAYS=30 \
    ADMIN_SUBNET=192.168.2.

# 不允许覆盖的 key（通过 CONFIG_FILE 动态配置）
# BARK_KEY 由 push.py 读取 config.json，不再用环境变量

EXPOSE 80 443

# 启动脚本（双端口：HTTP 8090 + HTTPS 8091）
# 挂载说明：
#   -v /path/to/board/certs:/certs        （证书目录，含 board.crt / board.key）
#   -v /path/to/board/uploads:/app/uploads  （媒体文件持久化）
#   -v /path/to/board/data:/app/data        （SQLite DB + config.json 持久化，重启不丢配置）
#   -v /tmp/dhcp.leases:/tmp/dhcp.leases:ro （只读，访客 MAC 解析）
#   -v /path/to/board/start.sh:/app/start.sh:ro （gunicorn 启动命令，可覆盖）
CMD ["sh", "/app/start.sh"]
