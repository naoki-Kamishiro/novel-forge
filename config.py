LM_STUDIO_URL = "http://localhost:1234/v1"  # LM StudioのローカルサーバーURL
API_KEY       = "lm-studio"               # LM Studioは認証不要なので任意の文字列でOK
TEMPERATURE   = 0.85                      # 本文生成のランダム性
SAVE_DIR      = "saves"                   # セーブデータの保存ディレクトリ

# 長さ別の目標文字数とシーンあたり出力トークン
LENGTH_SETTINGS = {
    "ショートショート": {
        "label":          "ショートショート",
        "target_chars":   4_000,
        "max_tokens":     2048,   # 一発〜3シーンで完結
        "use_ledger":     False,
        "use_verify":     False,
    },
    "短編": {
        "label":          "短編",
        "target_chars":   30_000,
        "max_tokens":     2048,
        "use_ledger":     True,
        "use_verify":     True,
    },
    "中編": {
        "label":          "中編",
        "target_chars":   80_000,
        "max_tokens":     2048,
        "use_ledger":     True,
        "use_verify":     True,
    },
    "長編": {
        "label":          "長編",
        "target_chars":   150_000,
        "max_tokens":     2048,
        "use_ledger":     True,
        "use_verify":     True,
    },
}

DEBUG_MODE = False  # --debug で有効化
