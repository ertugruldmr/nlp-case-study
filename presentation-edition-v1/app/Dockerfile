# Build context = the repository root (v0/ + presentation-edition-v1/ together):
#
#   docker build -f presentation-edition-v1/app/Dockerfile -t ftlink-app .
#   docker run --rm -p 8199:8199 ftlink-app
#
# or, equivalently:
#
#   docker compose -f presentation-edition-v1/app/compose.yaml up --build
#
# NOTE: authored on a machine without a container runtime; the image build is
# untested locally and should be smoke-tested once before any live demo from Docker.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-tur \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /work
COPY v0/ v0/
COPY presentation-edition-v1/app/ presentation-edition-v1/app/

WORKDIR /work/presentation-edition-v1/app
RUN uv sync --no-dev

# Bake the model weights and the precomputed scenario outputs into the image so
# the demo serves instantly and works fully offline. Precompute is the longest
# build step (~10 min CPU); drop this line for a slim image that computes lazily.
RUN uv run ftlink-precompute

EXPOSE 8199
# Loopback only: this API has no authentication by design. Binding 0.0.0.0 would
# expose unauthenticated upload and run endpoints to every interface on the host
# network. Publish the port as 127.0.0.1:8199:8199 if you need it from the host.
CMD ["uv", "run", "uvicorn", "ftlink_app.api:app", "--host", "127.0.0.1", "--port", "8199"]
