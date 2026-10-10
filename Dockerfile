FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 netscope
USER netscope

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('NETSCOPE_PORT','8000'), timeout=2)"

LABEL org.opencontainers.image.source="https://github.com/SHAIL-xx/netscope"
LABEL org.opencontainers.image.description="Website health checker with Prometheus metrics and a dashboard"

ENTRYPOINT ["netscope", "--host", "0.0.0.0"]
