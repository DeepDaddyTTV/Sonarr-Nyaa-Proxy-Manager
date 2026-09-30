FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/DeepDaddyTTV/Sonarr-Proxy-Manager" \
    org.opencontainers.image.description="Dockerized Torznab search proxy with a responsive Sonarr rule manager."

WORKDIR /app
COPY nyaa_season_proxy.py nyaa_proxy_runtime_patch.py manager_server.py proxy_integrations.py ./
COPY index.html login.html styles.css app.js auth.js site-icon.js ./
COPY assets/icons ./assets/icons

RUN mkdir -p /data \
    && chown -R proxy:proxy /app /data
USER proxy

ENV HOST=0.0.0.0 \
    PORT=8787 \
    RULES_PATH=/data/custom-rules.json \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8787
VOLUME ["/data"]
CMD ["python", "manager_server.py"]
