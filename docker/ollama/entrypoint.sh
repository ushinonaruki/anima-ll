#!/bin/sh
# Ollama を起動し、モデル anima-llm が未登録なら models/ の GGUF から登録する。
# GGUF がなくても Ollama 自体は起動したままにする（本体は Kernel のエラーとして扱い、動き続ける）。
# 登録したときの GGUF の SHA-256 を記録し、同じファイル名のまま中身が差し替えられても登録し直す。
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
  echo "[ollama] ${GGUF} から ${MODEL_NAME} を登録します（数分かかることがあります）"
  { echo "FROM ${GGUF}"; cat /etc/anima/Modelfile.base; } > /tmp/Modelfile
  ollama create "$MODEL_NAME" -f /tmp/Modelfile
  echo "$1" > "$SOURCE_RECORD"
  echo "[ollama] ${MODEL_NAME} を登録しました（sha256 ${1}）"
}

if [ ! -f "$GGUF" ]; then
  echo "[ollama] モデルファイルが見つかりません: ${GGUF}"
  echo "[ollama] anima-ll/models/ に GGUF を置いてから、docker compose restart ollama を実行してください"
else
  echo "[ollama] ${GGUF} の SHA-256 を計算しています"
  DIGEST="$(sha256sum "$GGUF" | cut -d ' ' -f 1)"
  if ! ollama show "$MODEL_NAME" >/dev/null 2>&1; then
    register "$DIGEST"
  elif [ "$(cat "$SOURCE_RECORD" 2>/dev/null || true)" != "$DIGEST" ]; then
    echo "[ollama] GGUF の中身が登録時と違うので登録し直します"
    register "$DIGEST"
  else
    echo "[ollama] ${MODEL_NAME} は登録済みです（sha256 ${DIGEST}）"
  fi
fi

wait "$SERVE_PID"
