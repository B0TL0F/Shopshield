FROM python:3.12.16-slim-bookworm AS check
ARG SERVICE
WORKDIR /build
COPY common.py .
COPY services/${SERVICE}.py service.py
RUN python -m py_compile common.py service.py

FROM python:3.12.16-slim-bookworm AS runtime
ARG SERVICE
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 CONTAINER=1 SERVICE=${SERVICE}
WORKDIR /app
COPY --from=check --chown=10001:10001 /build/common.py /build/service.py ./
USER 10001:10001
EXPOSE 8080
CMD ["python", "common.py"]
