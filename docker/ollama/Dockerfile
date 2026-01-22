FROM ollama/ollama:0.13.5

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
COPY Modelfile /Modelfile

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
