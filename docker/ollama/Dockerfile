FROM ollama/ollama:0.13.5

ENV MODEL_BASE=llama3.1:8b
ENV MODEL_NAME=anima-ll
ENV OLLAMA_PORT=11434
ENV TZ=Asia/Tokyo
# ollama serve プロセス用
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_KEEP_ALIVE=24h

COPY entrypoint.sh /entrypoint.sh
COPY Modelfile /Modelfile

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
