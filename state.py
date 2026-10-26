"""
セッション状態管理モジュール。
フルスナップショット管理。更新は update() 経由のみ。
"""

_state: dict = {}


def init(
    genre: str,
    title: str,
    length: str,
    plot: dict,
    character_sheets: dict,
    style_note: str = "",
    pov_char: str = "",
) -> None:
    global _state
    _state = {
        # 作品基本情報
        "genre": genre,
        "title": title,
        "length": length,
        "style_note": style_note,
        "pov_char": pov_char,

        # プロット
        "plot": plot,

        # キャラクターシート
        "character_sheets": character_sheets,

        # 進行状態
        "chapter_no": 1,
        "scene_no": 1,
        "total_scenes_written": 0,

        # ビート管理
        "beat_queue": [],     # plotから構築したビート待ち行列
        "beat_ptr": 0,        # 次に注入するビートのインデックス

        # 本文の最後尾（整合性保持のために保持）
        "prev_tail": "",

        # 残りシーン数（長さによる目安）
        "remaining_scenes": _estimate_scenes(length),
    }


def get() -> dict:
    return _state


def update(partial: dict) -> None:
    _state.update(partial)


def get_plot() -> dict:
    return _state.get("plot", {})


def get_sheets() -> dict:
    return _state.get("character_sheets", {})


def set_sheets(sheets: dict) -> None:
    _state["character_sheets"] = sheets


def load_from(data: dict) -> None:
    global _state
    _state = data


def _estimate_scenes(length: str) -> int:
    return {
        "flash":  3,
        "short":  12,
        "medium": 30,
        "long":   60,
    }.get(length, 12)


# 長さの日本語ラベル
LENGTH_LABEL = {
    "flash":  "ショートショート",
    "short":  "短編",
    "medium": "中編",
    "long":   "長編",
}
