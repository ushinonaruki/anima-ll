#!/bin/sh
# Ollama を起動し、モデル anima-llm が未登録なら models/ の GGUF から登録する。
# GGUF がなくても Ollama 自体は起動したままにする（本体は Kernel のエラーとして扱い、動き続ける）。
set -eu

MODEL_NAME="${ANIMA_MODEL_NAME:-anima-llm}"
GGUF="/models/${ANIMA_GGUF:-Llama-3.2-3B-Instruct-Q5_K_M.gguf}"
SOURCE_RECORD="/root/.ollama/anima-${MODEL_NAME}.source"

echo "[ollama] $(ollama --version 2>/dev/null || echo 'version unknown')"

ollama serve &
SERVE_PID=$!
trap 'kill -TERM "$SERVE_PID" 2>/dev/null' TERM INT

i=0
until ollama list >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "[ollama] サーバーが起動しませんでした"
    exit 1
  fi
  sleep 1
done

register() {
  echo "[ollama] ${GGUF} から ${MODEL_NAME} を登録します（初回のみ。数分かかることがあります）"
  { echo "FROM ${GGUF}"; cat /etc/anima/Modelfile.base; } > /tmp/Modelfile
  ollama create "$MODEL_NAME" -f /tmp/Modelfile
  echo "$GGUF" > "$SOURCE_RECORD"
  echo "[ollama] ${MODEL_NAME} を登録しました"
}

if [ ! -f "$GGUF" ]; then
  echo "[ollama] モデルファイルが見つかりません: ${GGUF}"
  echo "[ollama] anima-ll/models/ に GGUF を置いてから、docker compose restart ollama を実行してください"
elif ! ollama show "$MODEL_NAME" >/dev/null 2>&1; then
  register
elif [ "$(cat "$SOURCE_RECORD" 2>/dev/null || true)" != "$GGUF" ]; then
  echo "[ollama] GGUF が変わったので登録し直します"
  register
else
  echo "[ollama] ${MODEL_NAME} は登録済みです（${GGUF}）"
fi

wait "$SERVE_PID"
