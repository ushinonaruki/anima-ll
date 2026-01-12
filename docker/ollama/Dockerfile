FROM ollama/ollama:0.13.5

ARG MODEL_BASE
ARG MODEL_NAME
ARG OLLAMA_PORT

ENV MODEL_BASE=${MODEL_BASE}
ENV MODEL_NAME=${MODEL_NAME}
ENV OLLAMA_PORT=${OLLAMA_PORT}
ENV TZ=Asia/Tokyo
# ollama serve プロセス用
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_KEEP_ALIVE=24h

COPY entrypoint.sh /entrypoint.sh
COPY Modelfile /Modelfile

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
