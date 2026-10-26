"""
シーン生成モジュール。

generate_scene() が1シーンの本文を生成して返す。
内部で verify.verify_scene() を呼び、矛盾があれば最大MAX_RETRIESまで再試行する。
"""

import sys
from pathlib import Path

import api
import character
import config
import ledger
import state
import verify
from display import system_print
from prompt import build_scene_prompt

MAX_RETRIES = 2
OUTPUT_DIR = Path(__file__).parent / "output"


# ──────────────────────────────────────────────
# ビート注入（narrative-interactのbeat.pyを参考）
# ──────────────────────────────────────────────

def _pop_next_beat(beat_queue: list, beat_ptr: int) -> tuple[str, int]:
    """
    次のビートを取り出してテキストに変換する。
    戻り値: (注入文字列, 新しいbeat_ptr)
    """
    if beat_ptr >= len(beat_queue):
        return "", beat_ptr

    beat = beat_queue[beat_ptr]
    b_type = beat.get("type", "twist")
    content = beat.get("content", "")
    cost = beat.get("cost", "")

    templates = {
        "misconception": (
            f"このシーンで「{content}」という出来事を起こすこと。"
            "具体的な行動・台詞・物体の変化として描写すること（内面描写・説明文で代替しないこと）。"
            "その意味や教訓を地の文やNPCが言葉にしないこと。"
        ),
        "failure": (
            f"このシーンで「{content}」という失敗を発生させること。"
            "主人公が何かを試み、具体的な行動の結果として失敗が起きること（説明で済まさないこと）。"
            "失敗の原因や意味を地の文で解説しないこと。"
        ),
        "twist": (
            f"このシーンで「{content}」という展開を世界の側から起こすこと。"
            "人物・物・状況のいずれかが具体的に動くことで読者に伝わるようにすること。"
            "その意味を地の文やNPCが言葉にしないこと。"
        ),
        "choice": (
            f"このシーンで「{content}」という選択の局面を描くこと。代償は「{cost}」。"
            "主人公が実際に何かをしようとする場面として描くこと。選択肢を箇条書きで列挙しないこと。"
        ),
    }

    injection = templates.get(b_type, f"このシーンで「{content}」を描くこと。")
    return injection, beat_ptr + 1


# ──────────────────────────────────────────────
# シーン生成
# ──────────────────────────────────────────────

def generate_scene(scene_id: str | None = None) -> str:
    """
    現在のstateを読んで1シーン生成し、本文を返す。
    台帳・キャラシートの更新は呼び出し元（main.py）が行う。
    """
    st = state.get()
    sheets = state.get_sheets()

    genre          = st.get("genre", "")
    title          = st.get("title", "")
    length         = st.get("length", "short")
    style_note     = st.get("style_note", "")
    pov_char       = st.get("pov_char", "")
    chapter_no     = st.get("chapter_no")
    scene_no       = st.get("scene_no", 1)
    remaining      = st.get("remaining_scenes", 1)
    prev_tail      = st.get("prev_tail", "")
    beat_queue     = st.get("beat_queue", [])
    beat_ptr       = st.get("beat_ptr", 0)
    plot           = state.get_plot()

    if scene_id is None:
        scene_id = f"scene_{scene_no:04d}"

    # ビート注入
    beat_injection, new_beat_ptr = _pop_next_beat(beat_queue, beat_ptr)

    # このシーンのビート概要（章アウトラインから）
    scene_beat = _get_scene_beat(plot, chapter_no, scene_no)

    # 登場人物のコンテキスト
    char_names = list(sheets.keys())
    char_context = character.build_context(sheets)

    # 台帳から関連事実
    use_ledger = config.LENGTH_SETTINGS.get(
        {"flash": "ショートショート", "short": "短編", "medium": "中編", "long": "長編"}.get(length, length), {}
    ).get("use_ledger", False)

    ledger_facts = ""
    open_threads = ""
    if use_ledger:
        ledger_facts = ledger.build_context_for_scene(char_names)
        unresolved = ledger.unresolved_foreshadow()
        if unresolved:
            open_threads = "\n".join(f"- {fs['content']}" for fs in unresolved)

    # 結末・クライマックス（ショートショートは常に渡す、他は残り3シーン以下で渡す）
    ending     = plot.get("ending", "")
    climax     = plot.get("climax", {})
    climax_peak = climax.get("peak", "") if isinstance(climax, dict) else ""
    pass_goal  = (length == "flash") or (remaining <= 3)

    # プロンプト組み立て
    full_prompt = build_scene_prompt(
        genre=genre,
        title=title,
        style_note=style_note,
        pov_char=pov_char,
        scene_beat=scene_beat,
        char_context=char_context,
        prev_tail=prev_tail,
        ledger_facts=ledger_facts,
        open_threads=open_threads,
        chapter_no=chapter_no,
        scene_no=scene_no,
        remaining_scenes=remaining,
        beat_injection=beat_injection,
        ending=ending if pass_goal else "",
        climax_peak=climax_peak if pass_goal else "",
    )

    messages = [
        {"role": "system", "content": full_prompt},
        {"role": "user",   "content": "このシーンを書いてください。"},
    ]

    length_key = {"flash": "ショートショート", "short": "短編", "medium": "中編", "long": "長編"}.get(length, "短編")
    max_tokens = config.LENGTH_SETTINGS.get(length_key, {}).get("max_tokens", 2048)
    use_verify = config.LENGTH_SETTINGS.get(length_key, {}).get("use_verify", False)

    total_scenes = st.get("total_scenes_written", 0) + remaining  # 概算
    # 生成ループ（矛盾があればリトライ）
    for attempt in range(1, MAX_RETRIES + 1):
        label = f"シーン{scene_no} 執筆中"
        if attempt > 1:
            label = f"シーン{scene_no} 再生成 (試行{attempt}/{MAX_RETRIES})"
        scene_text = api.chat(messages, max_tokens=max_tokens, spinner_label=label)

        if scene_text.startswith("[ERROR"):
            system_print(f"生成エラー: {scene_text}")
            return ""

        if not use_verify:
            # 検証不要（ショートショート）はそのまま返す
            state.update({"beat_ptr": new_beat_ptr})
            check_repetition(scene_text, scene_no)
            _check_end_marker(scene_text, scene_no, max_tokens)
            return scene_text.replace("[END]", "").rstrip()

        # 矛盾チェック
        diff, errors = verify.verify_scene(scene_text, scene_id, char_names)

        if not errors:
            # OK: beat_ptrを進める
            state.update({"beat_ptr": new_beat_ptr})
            check_repetition(scene_text, scene_no)
            _check_end_marker(scene_text, scene_no, max_tokens)
            if config.DEBUG_MODE:
                print(f"[scene] scene_id={scene_id} OK diff_chars={len(diff.get('characters', []))}", file=sys.stderr)
            return scene_text.replace("[END]", "").rstrip()

        # 矛盾あり: エラーをメッセージに追加してリトライ
        error_msg = "前回の出力に以下の矛盾がありました。修正して書き直してください:\n" + "\n".join(f"- {e}" for e in errors)
        if attempt < MAX_RETRIES:
            messages = messages[:2] + [
                {"role": "assistant", "content": scene_text},
                {"role": "user",      "content": error_msg},
            ]
            system_print(f"矛盾を検出、書き直します: {'; '.join(errors)}")

    # 最終試行でも矛盾が残った場合は最後の生成結果を使う
    system_print("矛盾が残りましたが最終試行の結果を使用します")
    state.update({"beat_ptr": new_beat_ptr})
    _check_end_marker(scene_text, scene_no, max_tokens)
    return scene_text.replace("[END]", "").rstrip()


def _get_scene_beat(plot: dict, chapter_no: int | None, scene_no: int) -> str:
    """章アウトラインから現在シーンのビート概要を取得する。"""
    if chapter_no is None:
        return ""
    for ch in plot.get("chapter_outlines", []):
        if isinstance(ch, dict) and ch.get("chapter") == chapter_no:
            return ch.get("summary", "")
    return ""


# ──────────────────────────────────────────────
# 本文の保存・末尾取得
# ──────────────────────────────────────────────

def _check_end_marker(scene_text: str, scene_no: int, max_tokens: int) -> None:
    """
    [END]マーカーの有無でmax_tokens到達を判定してログに出す。
    修正はしない。気づきのための簡易チェック。
    """
    from display import warn_print
    has_end = "[END]" in scene_text
    # 文字数からトークン数を粗く推定（日本語は1字≒1.5token）
    approx_tokens = int(len(scene_text) * 1.5)
    if not has_end and approx_tokens >= max_tokens * 0.9:
        warn_print(f"シーン{scene_no} ⚠ [END]なし・推定{approx_tokens}tok（上限{max_tokens}tok）→ max_tokens到達で途切れた可能性")
    elif not has_end:
        warn_print(f"シーン{scene_no} ⚠ [END]なし（LLMが書ききれなかった可能性）")
    # [END]ありなら正常完了（ログなし）


def check_repetition(scene_text: str, scene_no: int) -> None:
    """
    同じ文頭（10字）が近傍（前後5段落）に複数出現したら警告を出す。
    修正はしない。気づきのための簡易チェック。
    """
    paragraphs = [p.strip() for p in scene_text.split("\n") if p.strip() and not p.strip().startswith("「")]
    warnings = []
    seen: dict[str, int] = {}
    for i, para in enumerate(paragraphs):
        key = para[:10]
        if key in seen and i - seen[key] <= 5:
            warnings.append(f"  段落{seen[key]+1}と段落{i+1}で類似した書き出し: 「{key}…」")
        seen[key] = i
    if warnings:
        from display import warn_print
        warn_print(f"シーン{scene_no} 繰り返し疑い:")
        for w in warnings:
            warn_print(w)


def append_to_output(title: str, scene_text: str) -> None:
    """生成した本文をoutput/に追記保存する。"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')[:40]
    out_path = OUTPUT_DIR / f"{safe_title}.txt"
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(scene_text)
        f.write("\n\n")


def get_tail(text: str, chars: int = 800) -> str:
    """本文の末尾N字を返す（次のシーンのprev_tailとして渡す用）。"""
    return text[-chars:] if len(text) > chars else text
