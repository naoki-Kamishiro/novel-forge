"""
LM Studio API 呼び出しモジュール。
chat()       : 通常の本文生成
chat_json()  : JSON出力が必要な生成（プロット・キャラ・抽出など）
"""

import json
import sys
import time
import datetime
import threading
from pathlib import Path

import requests

import config

# ──────────────────────────────────────────────
# スピナー
# ──────────────────────────────────────────────

class _Spinner:
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str):
        self._label   = label
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._t0      = time.time()

    def _run(self):
        i = 0
        while not self._stop.is_set():
            elapsed = time.time() - self._t0
            frame   = self._FRAMES[i % len(self._FRAMES)]
            print(f"\r\033[90m{frame} {self._label}  {elapsed:5.1f}s\033[0m",
                  end="", file=sys.stderr, flush=True)
            i += 1
            time.sleep(0.1)

    def start(self):
        self._thread.start()

    def stop(self, result_line: str = ""):
        self._stop.set()
        self._thread.join()
        elapsed = time.time() - self._t0
        # 行をクリアして結果を表示
        clear = "\r" + " " * 60 + "\r"
        if result_line:
            print(f"{clear}\033[90m✓ {result_line}  {elapsed:.1f}s\033[0m",
                  file=sys.stderr, flush=True)
        else:
            print(clear, end="", file=sys.stderr, flush=True)

# デバッグログの出力先
_LOG_DIR = Path(__file__).parent / "debug"
_LOG_DIR.mkdir(exist_ok=True)
_log_stem: str = datetime.date.today().isoformat()  # デフォルトは日付


def set_log_name(genre: str, title: str) -> None:
    """ログファイル名をジャンル・タイトルで設定する（main.pyからタイトル確定後に呼ぶ）。"""
    global _log_stem
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')[:20]
    _log_stem = f"{safe(genre)}_{safe(title)}"


def _debug_log(label: str, content: str) -> None:
    if not config.DEBUG_MODE:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{label}]\n{content}\n{'='*60}\n"
    print(line, file=sys.stderr)
    log_file = _LOG_DIR / f"{_log_stem}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def chat(
    messages: list,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    spinner_label: str = "生成中",
) -> str:
    """通常の本文生成。文字列を返す。エラー時は [ERROR: ...] を返す。"""
    temp = temperature if temperature is not None else config.TEMPERATURE
    tok  = max_tokens  if max_tokens  is not None else config.MAX_TOKENS

    _debug_log("REQUEST", json.dumps(messages, ensure_ascii=False, indent=2))

    spinner = _Spinner(spinner_label)
    spinner.start()

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
            timeout=300,
        )
        resp.raise_for_status()
        data     = resp.json()
        content  = data["choices"][0]["message"]["content"]
        usage    = data.get("usage", {})
        in_tok   = usage.get("prompt_tokens", 0)
        out_tok  = usage.get("completion_tokens", 0)
        chars    = len(content)
        result_line = f"{spinner_label} 完了  入力:{in_tok}tok  出力:{out_tok}tok  {chars}字"
    except requests.exceptions.Timeout:
        content     = "[ERROR: タイムアウト]"
        result_line = "タイムアウト"
    except requests.exceptions.ConnectionError:
        content     = "[ERROR: LM Studio に接続できません。起動しているか確認してください]"
        result_line = "接続エラー"
    except Exception as e:
        content     = f"[ERROR: {e}]"
        result_line = f"エラー: {e}"

    elapsed = time.time() - t0
    spinner.stop(result_line)
    _debug_log("RESPONSE", f"({elapsed:.1f}s)\n{content}")
    return content


def chat_json(
    messages: list,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    spinner_label: str = "JSON生成中",
) -> str:
    """JSON出力が必要な生成。chat() と同じく文字列を返す（parse は呼び出し元で行う）。"""
    temp = temperature if temperature is not None else config.JSON_TEMPERATURE
    tok  = max_tokens  if max_tokens  is not None else config.JSON_MAX_TOKENS
    return chat(messages, temperature=temp, max_tokens=tok, spinner_label=spinner_label)


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
