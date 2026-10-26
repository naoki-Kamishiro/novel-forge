"""
表示ユーティリティ。
"""

import sys


def system_print(msg: str) -> None:
    """システムメッセージ（進捗・エラー等）を表示する。"""
    print(f"\033[90m[system] {msg}\033[0m", file=sys.stderr)


def scene_print(text: str) -> None:
    """生成された本文を表示する。"""
    print(text)


def header_print(msg: str) -> None:
    """セクション見出しを表示する。"""
    print(f"\n\033[1m{'='*50}\033[0m")
    print(f"\033[1m  {msg}\033[0m")
    print(f"\033[1m{'='*50}\033[0m\n")


def info_print(msg: str) -> None:
    """情報メッセージを表示する。"""
    print(f"\033[36m{msg}\033[0m")


def warn_print(msg: str) -> None:
    """警告メッセージを表示する。"""
    print(f"\033[33m[警告] {msg}\033[0m", file=sys.stderr)


def error_print(msg: str) -> None:
    """エラーメッセージを表示する。"""
    print(f"\033[31m[エラー] {msg}\033[0m", file=sys.stderr)


def plot_summary(plot: dict) -> None:
    """プロットのサマリを表示する（設計フェーズ確認用）。"""
    prot = plot.get("protagonist", {})
    print(f"\n\033[1m── プロット概要 ──\033[0m")
    print(f"主人公  : {prot.get('name', '?')}　目標: {prot.get('goal_surface', '?')}")
    print(f"結末    : {plot.get('ending', '?')}")
    climax = plot.get("climax", {})
    print(f"クライマックス: {climax.get('peak', '?')}")
    chars = plot.get("characters", [])
    if chars:
        names = ", ".join(c.get("name", "?") for c in chars if isinstance(c, dict))
        print(f"登場人物: {names}")
    beats = plot.get("beats", [])
    if beats:
        print(f"ビート  : {len(beats)}件")
    acts = plot.get("acts", [])
    if acts:
        print(f"幕構成  : {len(acts)}幕")
    chapters = plot.get("chapter_outlines", [])
    if chapters:
        print(f"章構成  : {len(chapters)}章")
    print()


def char_summary(sheets: dict) -> None:
    """キャラクターシートのサマリを表示する。"""
    print(f"\033[1m── キャラクター ──\033[0m")
    for name, sheet in sheets.items():
        f = sheet.get("fixed", {})
        role = f.get("role", "")
        role_str = f"（{role}）" if role else ""
        print(f"  {name}{role_str}")
    print()
