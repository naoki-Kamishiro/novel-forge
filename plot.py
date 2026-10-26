"""
プロット生成モジュール。

生成する構造:
  - protagonist   : 主人公（名前・外見・傷・表層目標・深層目標）
  - characters    : 登場人物リスト
  - acts          : 幕構成（ショートショート/短編は省略）
  - chapters      : 章アウトライン（中編・長編）
  - ending        : 結末（最初に固定し、以後変えない）
  - climax        : クライマックス概要
  - themes        : テーマ（地の文では言わせない管理用）
  - beats         : ビートリスト（misconception / failure / twist / choice）

長さ別の生成深度:
  flash  (ショートショート) : protagonist + characters + ending + climax のみ
  short  (短編)             : 上記 + beats
  medium (中編)             : 上記 + acts + chapter_outlines
  long   (長編)             : 上記 + acts + chapter_outlines + subplots
"""

import json
import re
import sys
from json_repair import repair_json

from api import chat_json
from display import system_print
import config

MAX_RETRIES = 3

# 必須キー（長さによって変わる）
_REQUIRED_BASE = ("protagonist", "characters", "ending", "climax")
_REQUIRED_BEATS = ("beats",)
_REQUIRED_ACTS  = ("acts", "chapter_outlines")


def generate(genre: str, title: str, length: str) -> dict:
    """
    length: "flash" | "short" | "medium" | "long"
    """
    system_print("プロットを生成中...")
    system_prompt = _build_system(length)
    user_prompt   = _build_user(genre, title, length)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    required = list(_REQUIRED_BASE)
    if length in ("flash", "short", "medium", "long"):
        required += list(_REQUIRED_BEATS)
    if length in ("medium", "long"):
        required += list(_REQUIRED_ACTS)

    for attempt in range(1, MAX_RETRIES + 1):
        label = "プロット生成中" if attempt == 1 else f"プロット再生成 ({attempt}/{MAX_RETRIES})"
        raw    = chat_json(messages, max_tokens=2048, spinner_label=label)
        result = _parse(raw)
        if result and all(result.get(k) for k in required):
            return _finalize(result, length)
        if attempt < MAX_RETRIES:
            missing = [k for k in required if not (result or {}).get(k)]
            system_print(f"不足フィールド: {', '.join(missing)}")

    system_print("プロット生成に失敗しました。最低限の構造で続行します。")
    return _fallback(genre, title)


# ──────────────────────────────────────────────
# プロンプト構築
# ──────────────────────────────────────────────

def _build_system(length: str) -> str:
    depth_note = {
        "flash": "ショートショート（〜4,000字）向けプロット。protagonist・characters・ending・climax・beats（1〜2件）を生成してください。1シーンで完結する短い物語です。",
        "short": "短編（〜3万字）向けプロット。protagonist・characters・ending・climax・beatsを生成してください。",
        "medium": "中編（〜8万字）向けプロット。全フィールドを生成してください。",
        "long":  "長編（10万字〜）向けプロット。全フィールドに加えてsubplotsも生成してください。",
    }[length]

    # 長さ別にフォーマットを出し分ける
    fmt_base = """\
{{
  "protagonist": {{
    "name": "主人公の名前",
    "appearance": "外見の特徴（外から見える事実のみ）",
    "wound": "過去の傷・トラウマ",
    "goal_surface": "表層目標（本人が意識している目標）",
    "goal_deep": "深層目標（本人が気づいていない本当の欲求）"
  }},
  "characters": [
    {{
      "name": "キャラ名",
      "role": "役割（敵対・協力・中立など）",
      "appearance": "外見",
      "speech_style": "口調・話し方",
      "secret": "隠していること・動機"
    }}
  ],
  "ending": "結末の一文（ネタバレ含む管理用）",
  "climax": {{
    "setting": "クライマックスの場所・状況",
    "conflict_type": "対立の種類",
    "peak": "最高潮の出来事"
  }},
  "themes": ["テーマ1", "テーマ2"],
  "beats": [
    {{
      "type": "misconception|failure|twist|choice",
      "timing": "序盤|中盤|クライマックス直前|クライマックス",
      "content": "何が起きるか",
      "cost": "代償（choiceの場合）"
    }}
  ]
}}"""

    fmt_acts = """
  "acts": [
    {{
      "act": 1,
      "label": "幕の名前",
      "summary": "この幕で起きること"
    }}
  ],
  "chapter_outlines": [
    {{
      "chapter": 1,
      "act": 1,
      "title": "章タイトル",
      "summary": "この章で起きること",
      "end_state": "章末の状態"
    }}
  ]"""

    fmt_subplots = """
  "subplots": [
    {{
      "name": "サブプロット名",
      "summary": "概要",
      "resolution": "回収方法"
    }}
  ]"""

    if length == "flash":
        fmt = fmt_base
    elif length == "short":
        fmt = fmt_base
    elif length == "medium":
        # acts/chapter_outlinesをbeatsの後に挿入
        fmt = fmt_base.rstrip("}}") + "," + fmt_acts + "\n}}"
    else:  # long
        fmt = fmt_base.rstrip("}}") + "," + fmt_acts + "," + fmt_subplots + "\n}}"

    return f"""あなたは小説のプロット設計者です。
ジャンルとタイトルを受け取り、以下のJSON形式でプロットを出力してください。
説明文は不要です。JSONのみ出力してください。

{depth_note}

出力フォーマット:
{fmt}"""


def _build_user(genre: str, title: str, length: str) -> str:
    length_label = {
        "flash": "ショートショート",
        "short": "短編",
        "medium": "中編",
        "long": "長編",
    }[length]
    return f"ジャンル：{genre}\nタイトル：{title}\n長さ：{length_label}\n\nプロットをJSONで出力してください。"


# ──────────────────────────────────────────────
# パース・修復
# ──────────────────────────────────────────────

def _parse(raw: str) -> dict:
    if raw.startswith("[ERROR"):
        system_print(f"API エラー: {raw}")
        return {}

    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip().strip("`")

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    try:
        repaired = repair_json(cleaned)
        result = json.loads(repaired)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    system_print("プロットのJSON解析に失敗しました")
    return {}


def _finalize(plot: dict, length: str) -> dict:
    """型の正規化と欠落補完。"""
    # protagonist
    if not isinstance(plot.get("protagonist"), dict):
        raw = plot.get("protagonist", "")
        plot["protagonist"] = {
            "name": str(raw) if raw else "主人公",
            "appearance": "", "wound": "", "goal_surface": "", "goal_deep": "",
        }

    # characters
    chars = plot.get("characters", [])
    if not isinstance(chars, list):
        chars = []
    plot["characters"] = [c if isinstance(c, dict) else {"name": str(c)} for c in chars]

    # climax
    if not isinstance(plot.get("climax"), dict):
        plot["climax"] = {"setting": "", "conflict_type": "", "peak": ""}

    # beats
    if "beats" not in plot or not isinstance(plot["beats"], list):
        plot["beats"] = []
    for b in plot["beats"]:
        if isinstance(b, dict):
            b.setdefault("type", "twist")
            b.setdefault("timing", "中盤")
            b.setdefault("content", "")
            b.setdefault("cost", "")

    # acts / chapter_outlines
    for key in ("acts", "chapter_outlines", "subplots", "themes"):
        if not isinstance(plot.get(key), list):
            plot[key] = []

    # デバッグ出力
    if config.DEBUG_MODE:
        import json as _json
        print(f"[plot._finalize]\n{_json.dumps(plot, ensure_ascii=False, indent=2)}", file=sys.stderr)

    return plot


def _fallback(genre: str, title: str) -> dict:
    return {
        "protagonist": {"name": "主人公", "appearance": "", "wound": "", "goal_surface": "", "goal_deep": ""},
        "characters": [],
        "ending": "",
        "climax": {"setting": "", "conflict_type": "", "peak": ""},
        "themes": [],
        "beats": [],
        "acts": [],
        "chapter_outlines": [],
        "subplots": [],
    }
