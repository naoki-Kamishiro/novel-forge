"""
LM Studio API 呼び出しモジュール。
chat()       : 通常の本文生成
chat_json()  : JSON出力が必要な生成（プロット・キャラ・抽出など）
"""

import json
import sys
import time
import datetime
from pathlib import Path

import requests

import config

# デバッグログの出力先
_LOG_DIR = Path(__file__).parent / "debug"
_LOG_DIR.mkdir(exist_ok=True)


def _debug_log(label: str, content: str) -> None:
    if not config.DEBUG_MODE:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{label}]\n{content}\n{'='*60}\n"
    print(line, file=sys.stderr)
    log_file = _LOG_DIR / f"{datetime.date.today()}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def chat(messages: list, *, temperature: float | None = None, max_tokens: int | None = None) -> str:
    """通常の本文生成。文字列を返す。エラー時は [ERROR: ...] を返す。"""
    temp = temperature if temperature is not None else config.TEMPERATURE
    tok  = max_tokens  if max_tokens  is not None else config.MAX_TOKENS

    _debug_log("REQUEST", json.dumps(messages, ensure_ascii=False, indent=2))

    t0 = time.time()
    try:
        resp = requests.post(
            f"{config.BASE_URL}/chat/completions",
            json={
                "model": config.MODEL,
                "messages": messages,
                "temperature": temp,
                "max_tokens": tok,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        content = "[ERROR: タイムアウト]"
    except requests.exceptions.ConnectionError:
        content = "[ERROR: LM Studio に接続できません。起動しているか確認してください]"
    except Exception as e:
        content = f"[ERROR: {e}]"

    elapsed = time.time() - t0
    _debug_log("RESPONSE", f"({elapsed:.1f}s)\n{content}")
    return content


def chat_json(messages: list, *, temperature: float | None = None, max_tokens: int | None = None) -> str:
    """JSON出力が必要な生成。chat() と同じく文字列を返す（parse は呼び出し元で行う）。"""
    temp = temperature if temperature is not None else config.JSON_TEMPERATURE
    tok  = max_tokens  if max_tokens  is not None else config.JSON_MAX_TOKENS
    return chat(messages, temperature=temp, max_tokens=tok)


def generate_genre_title() -> tuple[str, str]:
    """ランダムなジャンルとタイトルを生成する（バッチモード用）。"""
    messages = [
        {
            "role": "system",
            "content": (
                "あなたは日本の小説のジャンルとタイトルを考えるアシスタントです。\n"
                "以下のJSON形式で1件だけ出力してください。説明は不要です。\n"
                '{"genre": "ジャンル名", "title": "タイトル"}'
            ),
        },
        {
            "role": "user",
            "content": "ランダムなジャンルとタイトルを1件考えてください。",
        },
    ]
    raw = chat_json(messages)
    try:
        import re
        cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip().strip("`")
        data = json.loads(cleaned)
        return str(data.get("genre", "現代ドラマ")), str(data.get("title", "無題"))
    except Exception:
        return "現代ドラマ", "無題"
