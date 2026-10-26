BASE_URL      = "http://localhost:1234/v1"  # LM StudioのローカルサーバーURL
LM_STUDIO_URL = BASE_URL                   # 後方互換
API_KEY       = "lm-studio"               # LM Studioは認証不要なので任意の文字列でOK
MODEL         = "local"                    # LM Studioは常に "local" を指定
TEMPERATURE       = 0.85                  # 本文生成のランダム性
JSON_TEMPERATURE  = 0.5                   # JSON生成のランダム性（低めに固定）
MAX_TOKENS        = 2048                  # 本文生成の最大トークン数
JSON_MAX_TOKENS   = 2048                  # JSON生成の最大トークン数
SAVE_DIR      = "saves"                   # セーブデータの保存ディレクトリ

# 長さ別の目標文字数とシーンあたり出力トークン
LENGTH_SETTINGS = {
    "ショートショート": {
        "label":          "ショートショート",
        "target_chars":   4_000,
        "max_tokens":     4096,   # 1シーン完結のため余裕を持たせる（問題C対処）
        "use_ledger":     False,
        "use_verify":     False,
    },
    "短編": {
        "label":          "短編",
        "target_chars":   30_000,
        "max_tokens":     4096,
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
