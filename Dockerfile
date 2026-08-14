FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates zstd \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENV OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    OLLAMA_MODEL=gemma4:e4b \
    OLLAMA_MODELS=/data/ollama-models \
    PORT=10000

EXPOSE 10000

ENTRYPOINT ["./entrypoint.sh"]
