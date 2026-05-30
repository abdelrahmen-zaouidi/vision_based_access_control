# dlib + opencv need system libs that aren't in the slim image, so we
# install them in a builder layer and copy the wheels into the runtime.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libgl1 \
        libglib2.0-0 \
        libboost-all-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY access_control/requirements.txt ./access_control/requirements.txt
RUN pip install --upgrade pip && pip install -r access_control/requirements.txt

COPY access_control ./access_control

# Drop root for runtime.
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/access_control/uploads \
    && chown -R app:app /app
USER app

WORKDIR /app/access_control

EXPOSE 5000

# Bind to all interfaces in the container; the host publishes the port.
# SECRET_KEY is intentionally not set here - the runtime command must
# supply it (see README quickstart).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "app:create_app()"]
