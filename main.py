"""
novel-forge エントリポイント。

使い方:
  python main.py                  # 対話モード（ジャンル・タイトル・長さを入力）
  python main.py --debug          # デバッグモード有効
  python main.py --load <path>    # セーブデータからの再開

生成の流れ:
  1. ジャンル・タイトル・長さを入力（または自動生成）
  2. プロット生成
  3. キャラクターシート構築
  4. 設計フェーズ確認（ユーザーが確認して続行）
  5. シーンを順次生成・保存
  6. 完了後レポート出力
"""

import argparse
import sys

import config
import character
import ledger
import plot as plot_mod
import save as save_mod
import scene as scene_mod
import state
import verify
from display import (
    char_summary, error_print, header_print, info_print,
    plot_summary, scene_print, system_print, warn_print,
)

# ──────────────────────────────────────────────
# 長さの選択肢
# ──────────────────────────────────────────────

LENGTH_OPTIONS = [
    ("1", "ショートショート", "flash",  "〜4,000字"),
    ("2", "短編",            "short",  "〜3万字"),
    ("3", "中編",            "medium", "〜8万字"),
    ("4", "長編",            "long",   "10万字〜"),
]


def _choose_length() -> str:
    print("\n長さを選択してください:")
    for num, label, _, chars in LENGTH_OPTIONS:
        print(f"  {num}. {label}（{chars}）")
    while True:
        choice = input("番号を入力 [1-4]: ").strip()
        for num, _, key, _ in LENGTH_OPTIONS:
            if choice == num:
                return key
        print("1〜4で入力してください。")


def _estimate_scenes(length: str) -> int:
    # flash=3: ショートショートは3シーン章立て（1シーン≒2,000字 × 3 = 〜6,000字）
    return {"flash": 3, "short": 12, "medium": 30, "long": 60}.get(length, 12)


# ──────────────────────────────────────────────
# 設計フェーズ
# ──────────────────────────────────────────────

def setup_phase(genre: str, title: str, length: str) -> bool:
    """
    プロット生成・キャラシート構築・ユーザー確認を行う。
    キャンセル時は False を返す。
    """
    # プロット生成
    plot = plot_mod.generate(genre, title, length)
    if not plot:
        error_print("プロット生成に失敗しました。")
        return False

    # キャラクターシート構築
    sheets = character.build_sheets(plot)

    # 台帳初期化
    ledger.init()

    # ビートキュー構築
    beat_queue = _build_beat_queue(plot)

    # 状態初期化
    state.init(
        genre=genre,
        title=title,
        length=length,
        plot=plot,
        character_sheets=sheets,
    )
    state.update({
        "beat_queue": beat_queue,
        "remaining_scenes": _estimate_scenes(length),
    })

    # 設計フェーズ確認
    header_print(f"『{title}』（{genre}）")
    plot_summary(plot)
    char_summary(sheets)

    print("このプロット・キャラクターで執筆を開始しますか？")
    print("  y : 開始する")
    print("  n : プロットを作り直す")
    print("  q : 終了")

    while True:
        ans = input("> ").strip().lower()
        if ans == "y":
            return True
        elif ans == "n":
            return setup_phase(genre, title, length)  # 再生成
        elif ans == "q":
            return False
        print("y / n / q で入力してください。")


def _build_beat_queue(plot: dict) -> list:
    """プロットのbeatsをtiming順にソートしてキューを返す。"""
    TIMING_ORDER = {"序盤": 0, "中盤": 1, "クライマックス直前": 2, "クライマックス": 3}
    beats = plot.get("beats", [])
    queue = [b for b in beats if isinstance(b, dict)]
    queue.sort(key=lambda b: TIMING_ORDER.get(b.get("timing", "中盤"), 99))
    return queue


# ──────────────────────────────────────────────
# 執筆ループ
# ──────────────────────────────────────────────

def writing_loop() -> None:
    st = state.get()
    title = st.get("title", "untitled")
    length = st.get("length", "short")
    total_scenes = _estimate_scenes(length)
    sheets = state.get_sheets()
    length_key = {"flash": "ショートショート", "short": "短編",
                  "medium": "中編", "long": "長編"}.get(length, "短編")
    use_ledger = config.LENGTH_SETTINGS.get(length_key, {}).get("use_ledger", False)

    header_print(f"執筆開始：『{title}』")

    scene_no = st.get("scene_no", 1)

    while True:
        st = state.get()
        scene_no = st.get("scene_no", 1)
        remaining = st.get("remaining_scenes", 1)

        if remaining <= 0:
            system_print("残りシーン数が0になりました。完了します。")
            break

        scene_id = f"scene_{scene_no:04d}"

        # シーン生成
        scene_text = scene_mod.generate_scene(scene_id)

        if not scene_text:
            error_print("シーン生成に失敗しました。終了します。")
            break

        # 本文表示
        print(f"\n\033[90m── シーン{scene_no} ──\033[0m\n")
        scene_print(scene_text)

        # ファイル保存
        scene_mod.append_to_output(title, scene_text)

        # 台帳・キャラシート更新
        if use_ledger:
            diff, _ = verify.verify_scene(scene_text, scene_id, list(sheets.keys()))
            if diff:
                ledger.ingest_diff(scene_id, diff)
                sheets = character.update_from_diff(sheets, diff)
                state.set_sheets(sheets)

        # prev_tail 更新
        tail = scene_mod.get_tail(scene_text)
        state.update({
            "scene_no": scene_no + 1,
            "remaining_scenes": remaining - 1,
            "prev_tail": tail,
        })

        # 自動セーブ
        save_mod.autosave()

        # 章末の再計画（中編・長編のみ）
        if length in ("medium", "long"):
            _maybe_replan(scene_no, total_scenes)

        # 終了判定（ショートショート・短編は残りシーン数で終了）
        if remaining - 1 <= 0:
            break

    # 完了
    header_print("執筆完了")
    report = verify.final_report()
    if report:
        info_print(report)

    out_path = scene_mod.OUTPUT_DIR / f"{title[:40]}.txt"
    info_print(f"本文: {out_path}")
    save_mod.save("final")


def _maybe_replan(scene_no: int, total_scenes: int) -> None:
    """
    中編・長編で章の節目に達したらプロットの残り章を再計画する。
    現在は10シーンごとに発動する簡易実装。
    """
    if scene_no % 10 != 0:
        return
    st = state.get()
    plot = state.get_plot()
    chapters = plot.get("chapter_outlines", [])
    chapter_no = st.get("chapter_no", 1)
    system_print(f"第{chapter_no}章完了。残り章アウトラインを確認中...")
    # TODO: 章アウトラインの再生成（adaptive再プロット相当）
    #   現時点ではスキップして続行。次フェーズで実装。
    state.update({"chapter_no": chapter_no + 1})


# ──────────────────────────────────────────────
# ロードからの再開
# ──────────────────────────────────────────────

def load_and_resume(path: str) -> None:
    try:
        save_mod.load(path)
    except Exception as e:
        error_print(f"ロードに失敗しました: {e}")
        sys.exit(1)
    st = state.get()
    header_print(f"再開：『{st.get('title', '?')}』シーン{st.get('scene_no', '?')}から")
    writing_loop()


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="novel-forge: ローカルLLM小説執筆システム")
    parser.add_argument("--debug", action="store_true", help="デバッグモードを有効にする")
    parser.add_argument("--load",  metavar="PATH",      help="セーブデータからの再開")
    args = parser.parse_args()

    if args.debug:
        config.DEBUG_MODE = True
        system_print("デバッグモード有効")

    # ロードモード
    if args.load:
        load_and_resume(args.load)
        return

    # 新規作成
    header_print("novel-forge へようこそ")

    genre = input("ジャンルを入力してください（例: ミステリー、SF、ホラー）: ").strip()
    if not genre:
        genre = "現代ドラマ"

    title = input("タイトルを入力してください: ").strip()
    if not title:
        title = "無題"

    length = _choose_length()

    # 設計フェーズ（プロットが気に入るまでループ）
    while True:
        ok = setup_phase(genre, title, length)
        if ok:
            break
        # n を選んだ場合は setup_phase 内で再帰するが、
        # q を選んだ場合はここに戻ってくる
        print("終了します。")
        return

    # 執筆ループ
    writing_loop()


if __name__ == "__main__":
    main()
