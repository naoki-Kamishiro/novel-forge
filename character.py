"""
キャラクター状態管理モジュール。

キャラクターデータは2層構造:
  fixed  : 名前・外見・口調・過去など変わらない属性（プロット生成時に確定）
  state  : 現在地・所持品・知っていること・関係性など変化する属性（シーンごとに更新）

update_from_diff() でシーン後の差分JSONを受け取り、stateだけ書き換える。
"""

import copy
import json
import sys
from typing import Any

import config


# ──────────────────────────────────────────────
# 初期化
# ──────────────────────────────────────────────

def build_sheets(plot: dict) -> dict:
    """
    プロットからキャラクターシート辞書を構築する。
    戻り値: { "主人公名": sheet_dict, "キャラ名": sheet_dict, ... }
    """
    sheets: dict[str, dict] = {}

    prot = plot.get("protagonist", {})
    prot_name = prot.get("name", "主人公")
    sheets[prot_name] = _make_sheet(
        name=prot_name,
        role="protagonist",
        appearance=prot.get("appearance", ""),
        speech_style="",
        wound=prot.get("wound", ""),
        goal_surface=prot.get("goal_surface", ""),
        goal_deep=prot.get("goal_deep", ""),
        secret="",
    )

    for c in plot.get("characters", []):
        if not isinstance(c, dict):
            continue
        name = c.get("name", "")
        if not name or name == prot_name:
            continue
        sheets[name] = _make_sheet(
            name=name,
            role=c.get("role", ""),
            appearance=c.get("appearance", ""),
            speech_style=c.get("speech_style", ""),
            wound="",
            goal_surface="",
            goal_deep="",
            secret=c.get("secret", ""),
        )

    return sheets


def _make_sheet(
    name: str,
    role: str,
    appearance: str,
    speech_style: str,
    wound: str,
    goal_surface: str,
    goal_deep: str,
    secret: str,
) -> dict:
    return {
        "fixed": {
            "name": name,
            "role": role,
            "appearance": appearance,
            "speech_style": speech_style,
            "wound": wound,
            "goal_surface": goal_surface,
            "goal_deep": goal_deep,
            "secret": secret,
        },
        "state": {
            "location": "",
            "items": [],
            "knowledge": [],     # 知っている事実のリスト
            "relations": {},     # { 相手名: 関係の現状 }
            "alive": True,
        },
    }


# ──────────────────────────────────────────────
# 更新
# ──────────────────────────────────────────────

def update_from_diff(sheets: dict, diff: dict) -> dict:
    """
    シーン後の差分JSONを受け取り、該当キャラのstateを更新する。

    diff フォーマット:
    {
      "characters": [
        {
          "name": "キャラ名",
          "location": "移動先（変化あれば）",
          "items_gained": ["アイテム名"],
          "items_lost":   ["アイテム名"],
          "knowledge":    ["新たに知った事実"],
          "relations":    {"相手名": "関係の変化"},
          "alive":        true | false
        }
      ]
    }
    """
    updated = copy.deepcopy(sheets)

    for entry in diff.get("characters", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if name not in updated:
            # 新キャラが登場した場合は簡易シートを作成
            updated[name] = _make_sheet(name=name, role="", appearance="",
                                        speech_style="", wound="", goal_surface="",
                                        goal_deep="", secret="")

        state = updated[name]["state"]

        if "location" in entry and entry["location"]:
            state["location"] = entry["location"]

        for item in entry.get("items_gained", []):
            if item not in state["items"]:
                state["items"].append(item)

        for item in entry.get("items_lost", []):
            state["items"] = [i for i in state["items"] if i != item]

        for fact in entry.get("knowledge", []):
            if fact not in state["knowledge"]:
                state["knowledge"].append(fact)

        relations = entry.get("relations", {})
        if not isinstance(relations, dict):
            relations = {}
        for target, rel in relations.items():
            state["relations"][target] = rel

        if "alive" in entry:
            state["alive"] = bool(entry["alive"])

    if config.DEBUG_MODE:
        print(f"[character.update_from_diff] diff={json.dumps(diff, ensure_ascii=False)}", file=sys.stderr)

    return updated


# ──────────────────────────────────────────────
# コンテキスト組み立て用
# ──────────────────────────────────────────────

def build_context(sheets: dict, names: list[str] | None = None) -> str:
    """
    シーン生成プロンプトに渡すキャラクター情報を文字列で返す。
    names を指定するとそのキャラだけ、None なら全員。
    """
    targets = names if names is not None else list(sheets.keys())
    lines: list[str] = []

    for name in targets:
        sheet = sheets.get(name)
        if not sheet:
            continue
        f = sheet["fixed"]
        s = sheet["state"]

        parts = [f"【{name}】（初出は「{name}」、以降は代名詞・役職・関係性で自然に呼んで良い）"]
        if f.get("appearance"):
            parts.append(f"外見: {f['appearance']}")
        if f.get("speech_style"):
            parts.append(f"口調: {f['speech_style']}")
        if f.get("wound"):
            parts.append(f"傷: {f['wound']}")
        if f.get("goal_surface"):
            parts.append(f"表層目標: {f['goal_surface']}")
        if s.get("location"):
            parts.append(f"現在地: {s['location']}")
        if s.get("items"):
            parts.append(f"所持品: {', '.join(s['items'])}")
        if s.get("knowledge"):
            parts.append(f"知っていること: {'; '.join(s['knowledge'])}")
        if s.get("relations"):
            rel_str = ", ".join(f"{k}→{v}" for k, v in s["relations"].items())
            parts.append(f"関係: {rel_str}")
        if not s.get("alive", True):
            parts.append("※ 死亡")

        lines.append("\n".join(parts))

    return "\n\n".join(lines)
