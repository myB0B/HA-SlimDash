# Le Supervisor ne fournit plus forcément BUILD_FROM : image Alpine officielle
# multi-architecture par défaut (amd64 / aarch64).
ARG BUILD_FROM=alpine:3.22
FROM ${BUILD_FROM}

# Python + aiohttp depuis les paquets Alpine : image petite, pas de compilation.
# Pillow : type 0 (vue dessinée en image PNG pour les liseuses, voir app/eink.py).
RUN apk add --no-cache python3 py3-aiohttp py3-pillow tzdata

ENV PYTHONDONTWRITEBYTECODE=1
COPY app /app
WORKDIR /app

CMD [ "python3", "-u", "/app/slimdash.py" ]
