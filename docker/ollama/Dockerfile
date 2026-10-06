# AnIma-ll 用の Ollama（ローカル LLM の実行環境）
#
# 起動時に、models/ の GGUF からモデル anima-llm を登録する（未登録のときだけ）。
# 再現性のため、動作を確認したら OLLAMA_VERSION を固定する（例: --build-arg OLLAMA_VERSION=0.x.y）。
# 起動ログの先頭に実際のバージョンが出る。

ARG OLLAMA_VERSION=latest
FROM ollama/ollama:${OLLAMA_VERSION}

COPY Modelfile.base /etc/anima/Modelfile.base
COPY entrypoint.sh /usr/local/bin/anima-ollama-entrypoint
RUN chmod +x /usr/local/bin/anima-ollama-entrypoint

ENTRYPOINT ["/usr/local/bin/anima-ollama-entrypoint"]
