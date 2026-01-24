#!/bin/bash

# エラーが起きたら即座に停止させる（安全策）
set -e
set -u

echo "[INFO] Initializing system nodes..."

# Ollamaサーバーをバックグラウンドで起動
ollama serve &

# サーバーの起動待ち
until curl -sf "http://localhost:${OLLAMA_PORT_CONTAINER}/api/version" > /dev/null; do
    sleep 1
done

# Llamaの構成
echo "FROM /models/${GGUF}.gguf" | cat - /Modelfile > /tmp/CombinedModelfile
ollama create "${MODEL_NAME}" -f /tmp/CombinedModelfile

echo "[SUCCESS] Brain node '${MODEL_NAME}' is online."

# サーバープロセスを維持
wait
