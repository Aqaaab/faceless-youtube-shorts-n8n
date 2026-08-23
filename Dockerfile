# n8n + complete media toolchain for the Shorts renderer.
# The renderer uses Kokoro TTS, Pexels, ffmpeg and jq.
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        python3 \
        python3-venv \
        python3-pip \
        jq \
        curl \
        ca-certificates \
        tini \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-noto-extra \
        fonts-noto-cjk \
        espeak-ng \
        libsndfile1 \
        libportaudio2 \
        portaudio19-dev \
    # Kokoro CLI requires Python 3.11/3.12; keep it isolated from n8n.
    && python3 -m venv /opt/kokoro-venv \
    && /opt/kokoro-venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/kokoro-venv/bin/pip install --no-cache-dir kokoro-tts \
    && mkdir -p /opt/kokoro \
    && curl -fL --retry 5 --retry-delay 3 --connect-timeout 30 --max-time 900 \
       -o /opt/kokoro/kokoro-v1.0.onnx \
       "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx" \
    && curl -fL --retry 5 --retry-delay 3 --connect-timeout 30 --max-time 900 \
       -o /opt/kokoro/voices-v1.0.bin \
       "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin" \
    && test -s /opt/kokoro/kokoro-v1.0.onnx \
    && test -s /opt/kokoro/voices-v1.0.bin \
    && ln -sf /opt/kokoro-venv/bin/kokoro-tts /usr/local/bin/kokoro-tts \
    # n8n itself
    && npm install -g n8n --omit=dev \
    && npm cache clean --force \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Media engine + runtime dirs
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.sh \
    && mkdir -p /data /home/node/.n8n \
    && chown -R node:node /data /home/node/.n8n /scripts /opt/kokoro /opt/kokoro-venv

ENV KOKORO_BIN=/usr/local/bin/kokoro-tts
ENV KOKORO_PATH=/opt/kokoro
ENV KOKORO_MODEL=/opt/kokoro/kokoro-v1.0.onnx
ENV KOKORO_VOICES=/opt/kokoro/voices-v1.0.bin
ENV N8N_USER_FOLDER=/home/node/.n8n

USER node
WORKDIR /home/node
EXPOSE 5678

# tini reaps ffmpeg/Kokoro child processes spawned by Execute Command.
ENTRYPOINT ["tini", "--"]
CMD ["n8n", "start"]
