#!/bin/bash

# Ollamaサーバーをバックグラウンドで起動
ollama serve &

# サーバーの起動待ち
echo "--- Ollamaサーバーの起動を待機中 ---"
until curl -s localhost:${OLLAMA_PORT} > /dev/null; do
    sleep 1
done
echo "--- サーバーが応答しました ---"

# Llamaの構成
echo "--- ${MODEL_NAME} の意識を構成中 ---"
ollama pull ${MODEL_BASE}
echo "FROM ${MODEL_BASE}" | cat - /Modelfile > /tmp/CombinedModelfile
ollama create ${MODEL_NAME} -f /tmp/CombinedModelfile
echo "--- ${MODEL_NAME} が目覚めました ---"

# サーバープロセスを維持
wait
