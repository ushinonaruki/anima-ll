# models/

ローカル LLM の GGUF ファイルを置く場所。**中身は Git 管理しない**（この README だけ管理する）。

```text
models/Llama-3.2-3B-Instruct-Q5_K_M.gguf
```

- compose が、このフォルダを Ollama コンテナの `/models` に読み取り専用でマウントする
- Ollama コンテナは起動時に、ここの GGUF からモデル `anima-llm` を登録する（初回だけ）
- 別のファイル名を使うときは、環境変数 `ANIMA_GGUF` にファイル名を指定する（例: `.env` に `ANIMA_GGUF=xxx.gguf`）
