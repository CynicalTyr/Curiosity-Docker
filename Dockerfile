# Curiosity-Docker sidecar — fast mode only (AGPL upstream isolated in the image).
ARG SOCIAL_ANALYZER_SHA=1ba0905e00d054aab833eb3693739c354db09e0f

FROM python:3.12-slim-bookworm

ARG SOCIAL_ANALYZER_SHA
ENV SOCIAL_ANALYZER_ROOT=/opt/social-analyzer \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/qeeqbox/social-analyzer.git "${SOCIAL_ANALYZER_ROOT}" \
    && cd "${SOCIAL_ANALYZER_ROOT}" \
    && git checkout "${SOCIAL_ANALYZER_SHA}" \
    && pip install --no-cache-dir -r requirements.txt

COPY shim_server.py /opt/shim/shim_server.py
COPY LICENSE.notice /opt/shim/LICENSE.notice

WORKDIR /opt/shim
EXPOSE 8095

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python3 -c "import os,urllib.request; k=os.environ.get('USERNAME_DISCOVERY_API_KEY',''); urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8095/health', headers={'X-API-Key': k}))" || exit 1

CMD ["python3", "shim_server.py"]
