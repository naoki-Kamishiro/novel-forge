"""
矛盾検出・シーン後検証モジュール。

verify_scene() が1シーン書き終えるたびに呼ばれる。
  1. LLMに本文→diff(JSON)を抽出させる
  2. diffと台帳を照合して矛盾を検出
  3. 矛盾があればエラーリストを返す（呼び出し元がリトライを判断）

抽出するdiffフォーマット:
{
  "characters": [
    {
      "name": "キャラ名",
      "location": "移動先（変化あれば）",
      "items_gained": [""],
      "items_lost":   [""],
      "knowledge":    ["新たに知った事実"],
      "relations":    {"相手名": "関係の変化"},
      "alive":        true
    }
  ],
  "world_facts": [
    { "subject": "対象", "fact": "事実", "tags": [] }
  ],
  "foreshadow_planted": [
    { "content": "張った伏線", "planned_resolution": "回収予定" }
  ],
  "foreshadow_resolved": ["fs_001"]
}
"""

import json
import re
import sys

from json_repair import repair_json
from api import chat_json
import ledger
import config

MAX_RETRIES = 2

# ──────────────────────────────────────────────
# diff 抽出
# ──────────────────────────────────────────────

_EXTRACT_SYSTEM = """\
あなたは小説の本文を読み、登場人物の状態変化を抽出するシステムです。
以下のJSON形式のみを出力してください。説明文は不要です。

{
  "characters": [
    {
      "name": "キャラ名",
      "location": "移動した場合のみ記入（変化なければ空文字）",
      "items_gained": ["入手したアイテム"],
      "items_lost":   ["失ったアイテム"],
      "knowledge":    ["このシーンで新たに知った事実（一文で）"],
      "relations":    {"相手名": "関係の変化（一文で）"},
      "alive":        true
    }
  ],
  "world_facts": [
    { "subject": "場所・物・概念", "fact": "確定した事実", "tags": [] }
  ],
  "foreshadow_planted": [
    { "content": "張られた伏線（一文）", "planned_resolution": "想定される回収方法" }
  ],
  "foreshadow_resolved": []
}

注意:
- 変化がないフィールドは空（[] or ""）にすること
- 死亡したキャラは alive: false にすること
- 登場しないキャラは含めないこと"""


def extract_diff(scene_text: str, character_names: list[str]) -> dict:
    """本文からdiffを抽出する。失敗時は空dict。"""
    names_str = "、".join(character_names) if character_names else "（なし）"
    user_msg = (
        f"登場人物: {names_str}\n\n"
        f"【本文】\n{scene_text}\n\n"
        "上記の本文を読み、登場人物の状態変化をJSONで抽出してください。"
    )
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        label = "diff抽出中" if attempt == 1 else f"diff再抽出 ({attempt}/{MAX_RETRIES})"
        raw = chat_json(messages, max_tokens=1024, spinner_label=label)
        diff = _parse_diff(raw)
        if diff is not None:
            if config.DEBUG_MODE:
                print(f"[verify.extract_diff] attempt={attempt} diff={json.dumps(diff, ensure_ascii=False)}", file=sys.stderr)
            return diff
        if attempt < MAX_RETRIES:
            pass  # リトライ

    if config.DEBUG_MODE:
        print("[verify.extract_diff] 全試行失敗、空dictを返す", file=sys.stderr)
    return {}


def _parse_diff(raw: str) -> dict | None:
    if raw.startswith("[ERROR"):
        return None
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
    return None


# ──────────────────────────────────────────────
# 矛盾チェック
# ──────────────────────────────────────────────

def check_consistency(diff: dict) -> list[str]:
    """
    diffと台帳を照合して矛盾のリストを返す。
    空リスト = 矛盾なし。
    """
    errors: list[str] = []

    for entry in diff.get("characters", []):
        name = entry.get("name", "")
        if not name:
            continue

        # 死亡済みキャラの再登場
        if ledger.is_dead(name) and entry.get("alive", True):
            errors.append(f"矛盾: {name} はすでに死亡しているが、このシーンで生きている")

        # 失ったアイテムをまた失う
        for item in entry.get("items_lost", []):
            held = ledger.query(name, "item")
            gained_items = [r["fact"].split("「")[1].split("」")[0]
                            for r in held if "gained" in r["tags"] and "「" in r["fact"]]
            lost_items   = [r["fact"].split("「")[1].split("」")[0]
                            for r in held if "lost" in r["tags"] and "「" in r["fact"]]
            currently_held = [i for i in gained_items if i not in lost_items]
            if item not in currently_held:
                errors.append(f"矛盾: {name} は「{item}」を持っていないが、失ったと記述されている")

        # 知識チェック（知らないはずの情報を知っている場合は検出困難なのでスキップ）

    if config.DEBUG_MODE and errors:
        print(f"[verify.check_consistency] errors={errors}", file=sys.stderr)

    return errors


# ──────────────────────────────────────────────
# メイン関数
# ──────────────────────────────────────────────

def verify_scene(
    scene_text: str,
    scene_id: str,
    character_names: list[str],
) -> tuple[dict, list[str]]:
    """
    シーン本文を受け取り、diffの抽出と矛盾チェックを行う。

    戻り値: (diff, errors)
      diff   : 抽出された状態変化（台帳・キャラシート更新に使う）
      errors : 矛盾のリスト（空 = OK）
    """
    diff = extract_diff(scene_text, character_names)
    if not diff:
        # 抽出失敗はエラーにしない（台帳更新をスキップして続行）
        return {}, []

    errors = check_consistency(diff)
    return diff, errors


# ──────────────────────────────────────────────
# 完成後レポート
# ──────────────────────────────────────────────

def final_report() -> str:
    """全シーン完了後の整合性レポートを返す（修正は行わない）。"""
    return ledger.report()
