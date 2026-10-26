"""
台帳モジュール。

要約せず「事実1件＝1レコード」で管理する。
シーンをまたいだ矛盾検出の根拠になる。

レコード形式:
{
  "id":       "scene_0001_fact_001",
  "scene_id": "scene_0001",
  "type":     "location|item|knowledge|relation|alive|prop",
  "subject":  "主語（キャラ名・固有名詞）",
  "fact":     "事実の一文",
  "tags":     ["タグ"],
}

typeの意味:
  location  : キャラがどこにいるか
  item      : キャラが何を持っているか（lost/gainedは sign で区別）
  knowledge : キャラが何を知っているか
  relation  : キャラ間の関係
  alive     : 生死
  prop      : 固有名詞・世界設定の事実（場所の性質、アイテムの効果など）
  foreshadow: 伏線（回収済みフラグを持つ）
"""

import json
import os
import sys
from datetime import datetime
from typing import Literal

import config

_records: list[dict] = []
_foreshadow: list[dict] = []  # 伏線台帳（別管理）
_scene_counter: int = 0


# ──────────────────────────────────────────────
# 初期化・ロード・セーブ
# ──────────────────────────────────────────────

def init() -> None:
    global _records, _foreshadow, _scene_counter
    _records = []
    _foreshadow = []
    _scene_counter = 0


def load(data: dict) -> None:
    global _records, _foreshadow, _scene_counter
    _records = data.get("records", [])
    _foreshadow = data.get("foreshadow", [])
    _scene_counter = data.get("scene_counter", 0)


def dump() -> dict:
    return {
        "records": _records,
        "foreshadow": _foreshadow,
        "scene_counter": _scene_counter,
    }


# ──────────────────────────────────────────────
# レコード追加
# ──────────────────────────────────────────────

def _next_scene_id() -> str:
    return f"scene_{_scene_counter:04d}"


def add_record(
    scene_id: str,
    record_type: str,
    subject: str,
    fact: str,
    tags: list[str] | None = None,
) -> None:
    idx = len(_records) + 1
    rec = {
        "id":       f"{scene_id}_fact_{idx:03d}",
        "scene_id": scene_id,
        "type":     record_type,
        "subject":  subject,
        "fact":     fact,
        "tags":     tags or [],
    }
    _records.append(rec)
    if config.DEBUG_MODE:
        print(f"[ledger.add] {rec}", file=sys.stderr)


def add_foreshadow(scene_id: str, content: str, planned_resolution: str) -> None:
    _foreshadow.append({
        "id":                  f"fs_{len(_foreshadow)+1:03d}",
        "planted_scene":       scene_id,
        "content":             content,
        "planned_resolution":  planned_resolution,
        "resolved":            False,
        "resolved_scene":      "",
    })


def mark_resolved(foreshadow_id: str, scene_id: str) -> None:
    for fs in _foreshadow:
        if fs["id"] == foreshadow_id:
            fs["resolved"] = True
            fs["resolved_scene"] = scene_id
            break


# ──────────────────────────────────────────────
# diffからの一括登録
# ──────────────────────────────────────────────

def ingest_diff(scene_id: str, diff: dict) -> None:
    """
    verify.py / scene.py が抽出したdiffを受け取り、台帳に登録する。
    diff は character.update_from_diff と同じフォーマット。
    """
    for entry in diff.get("characters", []):
        name = entry.get("name", "")
        if not name:
            continue

        if entry.get("location"):
            add_record(scene_id, "location", name,
                       f"{name}は{entry['location']}にいる")

        for item in entry.get("items_gained", []):
            add_record(scene_id, "item", name,
                       f"{name}は「{item}」を持っている", tags=["gained"])

        for item in entry.get("items_lost", []):
            add_record(scene_id, "item", name,
                       f"{name}は「{item}」を失った", tags=["lost"])

        for fact in entry.get("knowledge", []):
            add_record(scene_id, "knowledge", name,
                       f"{name}は知っている：{fact}")

        for target, rel in entry.get("relations", {}).items():
            add_record(scene_id, "relation", name,
                       f"{name}→{target}：{rel}")

        if "alive" in entry and not entry["alive"]:
            add_record(scene_id, "alive", name,
                       f"{name}は死亡した", tags=["dead"])

    for prop in diff.get("world_facts", []):
        add_record(scene_id, "prop", prop.get("subject", "世界"),
                   prop.get("fact", ""), tags=prop.get("tags", []))

    for fs in diff.get("foreshadow_planted", []):
        add_foreshadow(scene_id, fs.get("content", ""),
                       fs.get("planned_resolution", ""))

    for fs_id in diff.get("foreshadow_resolved", []):
        mark_resolved(fs_id, scene_id)


# ──────────────────────────────────────────────
# 検索
# ──────────────────────────────────────────────

def query(subject: str | None = None, record_type: str | None = None) -> list[dict]:
    """subjectとtypeで絞り込む。Noneは全件。"""
    result = _records
    if subject:
        result = [r for r in result if r["subject"] == subject]
    if record_type:
        result = [r for r in result if r["type"] == record_type]
    return result


def latest_location(name: str) -> str:
    """キャラの最新所在地を返す。なければ空文字。"""
    recs = [r for r in _records if r["subject"] == name and r["type"] == "location"]
    return recs[-1]["fact"] if recs else ""


def is_dead(name: str) -> bool:
    """キャラが死亡済みかどうか。"""
    return any(r for r in _records
               if r["subject"] == name and r["type"] == "alive" and "dead" in r["tags"])


def get_knowledge(name: str) -> list[str]:
    """キャラが知っている事実のリスト。"""
    return [r["fact"] for r in _records
            if r["subject"] == name and r["type"] == "knowledge"]


def unresolved_foreshadow() -> list[dict]:
    """未回収の伏線リスト。"""
    return [fs for fs in _foreshadow if not fs["resolved"]]


def build_context_for_scene(relevant_names: list[str]) -> str:
    """
    シーン生成プロンプトに渡す台帳サマリを文字列で返す。
    relevant_names に含まれるキャラに関係する事実のみ絞り込む。
    """
    lines: list[str] = []

    for name in relevant_names:
        loc = latest_location(name)
        if loc:
            lines.append(f"・{loc}")
        items_gained = [r for r in _records if r["subject"] == name
                        and r["type"] == "item" and "gained" in r["tags"]]
        items_lost_facts = [r["fact"] for r in _records if r["subject"] == name
                            and r["type"] == "item" and "lost" in r["tags"]]
        # 持っているアイテム = gained - lost に含まれるもの
        held = [r["fact"].split("「")[1].split("」")[0]
                for r in items_gained
                if "「" in r["fact"] and "」" in r["fact"]
                and r["fact"].split("「")[1].split("」")[0] not in
                   [f.split("「")[1].split("」")[0] for f in items_lost_facts if "「" in f]]
        if held:
            lines.append(f"・{name}の所持品: {', '.join(held)}")

        facts = get_knowledge(name)
        if facts:
            lines.append(f"・{name}が知っていること: {'; '.join(facts[-5:])}")  # 直近5件

        if is_dead(name):
            lines.append(f"・{name}は死亡済み")

    unresolved = unresolved_foreshadow()
    if unresolved:
        lines.append("【未回収の伏線】")
        for fs in unresolved:
            lines.append(f"  - {fs['content']}（planted: {fs['planted_scene']}）")

    return "\n".join(lines) if lines else ""


def report() -> str:
    """完成後の全体チェック用レポートを返す。"""
    lines = [f"=== 台帳レポート ({len(_records)} 件) ==="]

    unresolved = unresolved_foreshadow()
    if unresolved:
        lines.append(f"\n【未回収の伏線 {len(unresolved)}件】")
        for fs in unresolved:
            lines.append(f"  - {fs['content']} (planted: {fs['planted_scene']})")

    dead = [r["subject"] for r in _records if r["type"] == "alive" and "dead" in r["tags"]]
    if dead:
        lines.append(f"\n【死亡キャラ】{', '.join(set(dead))}")

    return "\n".join(lines)
