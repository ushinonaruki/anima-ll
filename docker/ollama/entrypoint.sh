#!/bin/bash

# エラーが起きたら即座に停止させる（安全策）
set -e
set -u

# 環境変数をセット
export OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT_CONTAINER}"

# Ollamaサーバーをバックグラウンドで起動
ollama serve &

# サーバーの起動待ち
until curl -sf "http://localhost:${OLLAMA_PORT_CONTAINER}/api/version" > /dev/null; do
    sleep 1
done

# Llamaの構成
ollama create "${MODEL_NAME}" -f <(echo "FROM /models/${GGUF_FILE}")

# サーバープロセスを維持
wait
