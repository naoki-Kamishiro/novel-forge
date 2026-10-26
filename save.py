"""
セーブ・ロードモジュール。

セーブデータは saves/<title>_<scene_no>.json に保存する。
state / character_sheets / ledger の3つをまとめてダンプする。
"""

import json
import os
import sys
from pathlib import Path

import config
import ledger
import state
from display import system_print

SAVE_DIR = Path(__file__).parent / config.SAVE_DIR


def _safe_title(title: str) -> str:
    return "".join(c for c in title if c not in r'\/:*?"<>|')[:40]


def save(label: str | None = None) -> str:
    """
    現在のセッション状態をJSONに保存する。
    label が None のときは scene_no を使う。
    戻り値: 保存したファイルパス。
    """
    SAVE_DIR.mkdir(exist_ok=True)
    st = state.get()
    title = st.get("title", "untitled")
    scene_no = st.get("scene_no", 0)
    suffix = label if label else f"scene{scene_no:04d}"

    filename = f"{_safe_title(title)}_{suffix}.json"
    path = SAVE_DIR / filename

    data = {
        "state":   st,
        "ledger":  ledger.dump(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    system_print(f"セーブ完了: {path}")
    if config.DEBUG_MODE:
        print(f"[save] {path}", file=sys.stderr)

    return str(path)


def load(path: str) -> None:
    """
    JSONからセッション状態を復元する。
    state / ledger をそれぞれ復元する。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    state.load_from(data["state"])
    ledger.load(data.get("ledger", {}))

    st = state.get()
    system_print(f"ロード完了: {st.get('title', '?')} シーン{st.get('scene_no', '?')}")


def list_saves() -> list[str]:
    """セーブファイルの一覧を返す（新しい順）。"""
    if not SAVE_DIR.exists():
        return []
    files = sorted(SAVE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in files]


def autosave() -> None:
    """シーンごとの自動セーブ。"""
    save()
