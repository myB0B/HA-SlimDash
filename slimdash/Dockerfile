# The Supervisor no longer always provides BUILD_FROM: official multi-architecture
# Alpine image by default (amd64 / aarch64).
ARG BUILD_FROM=alpine:3.22
FROM ${BUILD_FROM}

# Python + aiohttp from the Alpine packages: small image, no compilation.
# Pillow: type 0 (view drawn as a PNG image for e-readers, see app/eink.py).
RUN apk add --no-cache python3 py3-aiohttp py3-pillow tzdata

ENV PYTHONDONTWRITEBYTECODE=1
COPY app /app
WORKDIR /app

CMD [ "python3", "-u", "/app/slimdash.py" ]
