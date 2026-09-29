FROM python:3.13-slim

WORKDIR /app
COPY nyaa_season_proxy.py nyaa_proxy_runtime_patch.py manager_server.py ./
COPY index.html styles.css app.js ./

RUN useradd --system --uid 10001 --create-home proxy \
    && mkdir -p /data \
    && chown -R proxy:proxy /app /data
USER proxy

ENV HOST=0.0.0.0 \
    PORT=8787 \
    RULES_PATH=/data/custom-rules.json \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8787
VOLUME ["/data"]
CMD ["python", "manager_server.py"]
