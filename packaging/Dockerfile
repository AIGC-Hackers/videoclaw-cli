# Multi-stage CLI image for the `claw` binary.
#
# This image is parallel to the existing FastAPI image at the repo root —
# the existing /Dockerfile keeps `uvicorn :8000` for the optional `server`
# extra. Build this CLI image explicitly via:
#
#   docker build -t videoclaw-cli -f packaging/Dockerfile .
#   docker run --rm videoclaw-cli claw --version
#
# Stage 1 builds the wheel using the overlay; Stage 2 is a minimal runtime
# layer that only carries the wheel + its runtime dependencies.

# ---- Stage 1: build wheel ----
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1

RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /src
COPY . /src

# Build wheel using the overlay's source-exclude rules.
RUN uv build --wheel --out-dir /dist

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a non-root user for the CLI process.
RUN useradd --create-home --shell /bin/bash claw
USER claw
WORKDIR /home/claw

COPY --from=build /dist/*.whl /tmp/
RUN pip install --user --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
ENV PATH=/home/claw/.local/bin:$PATH

# Default to printing the version — orchestrators override with `claw drama …`
# or `claw --json doctor` for health checks.
ENTRYPOINT ["claw"]
CMD ["--version"]
