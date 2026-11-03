# Use Debian 13 rather than the Debian 12 base flagged in Trivy_logs.
# Refresh and rescan on each build; CI scans are advisory during flow testing.
FROM python:3.12.16-slim-trixie AS check
ARG SERVICE
WORKDIR /build
COPY common.py .
COPY services/${SERVICE}.py service.py
RUN python -m py_compile common.py service.py

FROM python:3.12.16-slim-trixie AS runtime
ARG SERVICE
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 CONTAINER=1 SERVICE=${SERVICE}
WORKDIR /app
COPY --from=check --chown=10001:10001 /build/common.py /build/service.py ./
USER 10001:10001
EXPOSE 8080
CMD ["python", "common.py"]
