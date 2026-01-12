import importlib
import os
import sys
from pathlib import Path

# --- プロジェクトルートを検索パスに追加 ---
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_env_strict(key, cast=str):
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError
    try:
        return cast(value)
    except ValueError:
        raise ValueError


def get_lang_strict(parent, key):
    try:
        # 指定された言語のモジュールを動的にインポート
        LANG = os.getenv("LANG", "ja")
        target = importlib.import_module(f"lang.{LANG}.{parent}")
        value = getattr(target, key, None)
    except ImportError:
        raise ImportError
    if value is None:
        raise KeyError
    return value


# --- 共通設定 ---
MODEL_NAME = get_env_strict("MODEL_NAME")
MODEL_BASE = get_env_strict("MODEL_BASE")

# --- 接続設定 ---
OLLAMA_PORT = get_env_strict("OLLAMA_PORT", int)
REQUEST_TIMEOUT = get_env_strict("REQUEST_TIMEOUT", float)

# --- サンプリング設定 ---
CPU_SAMPLE_INTERVAL = get_env_strict("CPU_SAMPLE_INTERVAL", float)

# --- フォーマット定数 ---
BYTES_TO_MB = get_env_strict("BYTES_TO_MB", int)
ENCODING = get_env_strict("ENCODING")
TIME_FORMAT = get_env_strict("TIME_FORMAT")

# --- 開発者コマンド ---
COMMAND_END = get_env_strict("COMMAND_END")

# --- Lang: UI ---
UI_ANIMA_LABEL = get_lang_strict("ui", "ANIMA_LABEL")
UI_BOOT = get_lang_strict("ui", "BOOT")
UI_CLOSING = get_lang_strict("ui", "CLOSING")
UI_ERR_CONN = get_lang_strict("ui", "ERR_CONN")
UI_ERR_EOF = get_lang_strict("ui", "ERR_EOF")
UI_ERR_GENERIC = get_lang_strict("ui", "ERR_GENERIC")
UI_ERR_INTERRUPT = get_lang_strict("ui", "ERR_INTERRUPT")
UI_INPUT_LABEL = get_lang_strict("ui", "INPUT_LABEL")
