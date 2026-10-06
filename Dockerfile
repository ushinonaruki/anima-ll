# AnIma-ll 本体のイメージ
#
#   runtime : 本体を動かす（既定）
#   dev     : テストを動かす（runtime ＋ pytest ＋ tests/）

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依存とパッケージ（ソースが変わらなければキャッシュが効く順に置く）
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# 脳の設計図。compose では手元の config/ をマウントして上書きする
COPY config ./config

CMD ["python", "-m", "anima_ll"]


FROM runtime AS dev

RUN pip install ".[dev]"
COPY tests ./tests

CMD ["pytest"]
