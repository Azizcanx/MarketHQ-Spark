# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Knowledge Base V1
====================================

Amaç:
    MarketHQ içerisinde test edilen stratejileri,
    strateji hipotezlerini, backtest sonuçlarını ve
    walk-forward sonuçlarını kalıcı olarak saklamak.

Bu sistem:
    - Gerçek emir göndermez.
    - Broker bağlantısı yapmaz.
    - Strateji sonuçlarını araştırma amacıyla saklar.
    - Kaynak bilgisi ile test sonucunu birbirinden ayırır.

Ana prensip:

    "Kaynakta söylendi"
            !=
    "MarketHQ tarafından doğrulandı"

Bir strateji ancak backtest + walk-forward gibi
testlerden geçtikten sonra daha yüksek güven seviyesine
taşınabilir.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent

KNOWLEDGE_BASE_DIR = (
    PROJECT_ROOT / "knowledge_base"
)

KNOWLEDGE_BASE_FILE = (
    KNOWLEDGE_BASE_DIR
    / "strategies.json"
)


# =========================================================
# CONSTANTS
# =========================================================

VALID_STATUSES = {
    "HYPOTHESIS",
    "TESTING",
    "VALIDATION",
    "PROMISING",
    "REJECTED",
    "ARCHIVED",
}


VALID_SOURCE_TYPES = {
    "manual",
    "youtube",
    "article",
    "book",
    "research",
    "interview",
    "backtest",
    "walk_forward",
    "market_hq",
    "unknown",
}


# =========================================================
# DEFAULT DATABASE
# =========================================================

DEFAULT_DATABASE = {
    "version": 1,
    "created_at": None,
    "updated_at": None,
    "strategies": [],
}


# =========================================================
# HELPERS
# =========================================================

def utc_now() -> str:
    """
    UTC ISO timestamp döndürür.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Güvenli float dönüşümü.
    """

    try:

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):

        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Güvenli integer dönüşümü.
    """

    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def clean_text(
    value: Any,
    default: str = "",
) -> str:
    """
    Metni güvenli şekilde temizler.
    """

    if value is None:
        return default

    return str(
        value
    ).strip()


def ensure_directory() -> None:
    """
    Knowledge Base klasörünü oluşturur.
    """

    KNOWLEDGE_BASE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# =========================================================
# DATABASE LOAD / SAVE
# =========================================================

def create_empty_database() -> dict[str, Any]:
    """
    Yeni boş Knowledge Base oluşturur.
    """

    now = utc_now()

    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "strategies": [],
    }


def load_database() -> dict[str, Any]:
    """
    Knowledge Base JSON dosyasını yükler.

    Dosya yoksa otomatik oluşturur.
    """

    ensure_directory()

    if not KNOWLEDGE_BASE_FILE.exists():

        database = (
            create_empty_database()
        )

        save_database(
            database
        )

        return database

    try:

        with open(
            KNOWLEDGE_BASE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            database = json.load(
                file
            )

        if not isinstance(
            database,
            dict,
        ):

            raise ValueError(
                "Knowledge Base formatı geçersiz."
            )

        if "strategies" not in database:

            database[
                "strategies"
            ] = []

        return database

    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:

        print(
            "⚠️ Knowledge Base okunamadı:"
            f" {exc}"
        )

        return create_empty_database()


def save_database(
    database: dict[str, Any],
) -> None:
    """
    Knowledge Base'i diske kaydeder.
    """

    ensure_directory()

    database[
        "updated_at"
    ] = utc_now()

    temporary_file = (
        KNOWLEDGE_BASE_FILE.with_suffix(
            ".tmp"
        )
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            database,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_file.replace(
        KNOWLEDGE_BASE_FILE
    )


# =========================================================
# STRATEGY ID
# =========================================================

def generate_strategy_id() -> str:
    """
    Benzersiz strateji ID üretir.
    """

    return (
        "STR-"
        + uuid.uuid4().hex[:10].upper()
    )


# =========================================================
# STRATEGY OBJECT
# =========================================================

def create_strategy(
    name: str,
    description: str = "",
    source_type: str = "manual",
    source_name: str = "",
    source_url: str = "",
    source_author: str = "",
    market: str = "Unknown",
    symbols: list[str] | None = None,
    tags: list[str] | None = None,
    hypothesis: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """
    Yeni strateji kaydı oluşturur.

    Bu aşamadaki strateji yalnızca HYPOTHESIS'tir.
    Henüz doğrulanmış kabul edilmez.
    """

    source_type = clean_text(
        source_type,
        "unknown",
    ).lower()

    if source_type not in VALID_SOURCE_TYPES:
        source_type = "unknown"

    strategy = {
        "strategy_id": generate_strategy_id(),

        "name": clean_text(
            name,
            "Unnamed Strategy",
        ),

        "description": clean_text(
            description
        ),

        "status": "HYPOTHESIS",

        "source": {
            "type": source_type,
            "name": clean_text(
                source_name
            ),
            "url": clean_text(
                source_url
            ),
            "author": clean_text(
                source_author
            ),
        },

        "market": clean_text(
            market,
            "Unknown",
        ),

        "symbols": list(
            symbols or []
        ),

        "tags": list(
            tags or []
        ),

        "hypothesis": clean_text(
            hypothesis
        ),

        "parameters": {},

        "rules": {
            "entry": [],
            "exit": [],
            "risk": [],
            "filters": [],
        },

        "tests": {
            "backtests": [],
            "walk_forward": [],
        },

        "learning": {
            "confidence": 0.0,
            "successful_tests": 0,
            "failed_tests": 0,
            "validation_passes": 0,
            "validation_failures": 0,
            "observations": [],
        },

        "notes": clean_text(
            notes
        ),

        "created_at": utc_now(),

        "updated_at": utc_now(),
    }

    return strategy


# =========================================================
# STRATEGY CRUD
# =========================================================

def add_strategy(
    strategy: dict[str, Any],
) -> str:
    """
    Stratejiyi Knowledge Base'e ekler.

    Dönen değer:
        strategy_id
    """

    database = load_database()

    strategy_id = clean_text(
        strategy.get(
            "strategy_id"
        )
    )

    if not strategy_id:

        strategy_id = (
            generate_strategy_id()
        )

        strategy[
            "strategy_id"
        ] = strategy_id

    strategy[
        "updated_at"
    ] = utc_now()

    database[
        "strategies"
    ].append(
        strategy
    )

    save_database(
        database
    )

    return strategy_id


def get_strategy(
    strategy_id: str,
) -> dict[str, Any] | None:
    """
    Strategy ID ile strateji bulur.
    """

    database = load_database()

    strategy_id = clean_text(
        strategy_id
    )

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            == strategy_id
        ):

            return strategy

    return None


def get_all_strategies() -> list[
    dict[str, Any]
]:
    """
    Tüm stratejileri döndürür.
    """

    database = load_database()

    return database[
        "strategies"
    ]


def update_strategy(
    strategy_id: str,
    updates: dict[str, Any],
) -> bool:
    """
    Mevcut stratejiyi günceller.
    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        strategy.update(
            updates
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


def delete_strategy(
    strategy_id: str,
) -> bool:
    """
    Stratejiyi Knowledge Base'den siler.

    Not:
        Test geçmişi önemli olduğu için normal kullanımda
        silmek yerine ARCHIVED yapmak daha sağlıklıdır.
    """

    database = load_database()

    original_count = len(
        database[
            "strategies"
        ]
    )

    database[
        "strategies"
    ] = [
        strategy
        for strategy in database[
            "strategies"
        ]
        if strategy.get(
            "strategy_id"
        )
        != strategy_id
    ]

    if len(
        database[
            "strategies"
        ]
    ) == original_count:

        return False

    save_database(
        database
    )

    return True


# =========================================================
# PARAMETERS
# =========================================================

def set_strategy_parameters(
    strategy_id: str,
    parameters: dict[str, Any],
) -> bool:
    """
    Stratejinin teknik parametrelerini kaydeder.
    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        strategy[
            "parameters"
        ] = dict(
            parameters
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# RULES
# =========================================================

def add_rule(
    strategy_id: str,
    rule_type: str,
    rule: str,
) -> bool:
    """
    Stratejiye giriş/çıkış/risk/filter kuralı ekler.
    """

    valid_types = {
        "entry",
        "exit",
        "risk",
        "filters",
    }

    rule_type = clean_text(
        rule_type
    ).lower()

    if rule_type not in valid_types:
        return False

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        rules = strategy.setdefault(
            "rules",
            {},
        )

        rules.setdefault(
            rule_type,
            [],
        )

        rules[
            rule_type
        ].append(
            clean_text(
                rule
            )
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# BACKTEST RESULT
# =========================================================

def add_backtest_result(
    strategy_id: str,
    symbol: str,
    result: dict[str, Any],
) -> bool:
    """
    Backtest sonucunu stratejiye ekler.

    Sonuç yalnızca gözlem olarak saklanır.
    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        metrics = result.get(
            "metrics",
            result,
        )

        backtest_record = {
            "timestamp": utc_now(),

            "symbol": clean_text(
                symbol
            ),

            "total_trades": safe_int(
                metrics.get(
                    "total_trades",
                    0,
                )
            ),

            "winning_trades": safe_int(
                metrics.get(
                    "winning_trades",
                    0,
                )
            ),

            "losing_trades": safe_int(
                metrics.get(
                    "losing_trades",
                    0,
                )
            ),

            "win_rate_percent": safe_float(
                metrics.get(
                    "win_rate_percent",
                    0.0,
                )
            ),

            "profit_factor": safe_float(
                metrics.get(
                    "profit_factor",
                    0.0,
                )
            ),

            "net_pnl": safe_float(
                metrics.get(
                    "net_pnl",
                    0.0,
                )
            ),

            "return_percent": safe_float(
                metrics.get(
                    "total_return_percent",
                    metrics.get(
                        "return_percent",
                        0.0,
                    ),
                )
            ),

            "max_drawdown_percent": safe_float(
                metrics.get(
                    "max_drawdown_percent",
                    0.0,
                )
            ),

            "raw_summary": {
                "status": "BACKTEST",
            },
        }

        strategy.setdefault(
            "tests",
            {},
        ).setdefault(
            "backtests",
            [],
        ).append(
            backtest_record
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# WALK-FORWARD RESULT
# =========================================================

def add_walk_forward_result(
    strategy_id: str,
    symbol: str,
    result: dict[str, Any],
) -> bool:
    """
    Walk-forward sonucunu stratejiye ekler.
    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        aggregate = result.get(
            "aggregate",
            {},
        )

        record = {
            "timestamp": utc_now(),

            "symbol": clean_text(
                symbol
            ),

            "fold_count": safe_int(
                aggregate.get(
                    "fold_count",
                    0,
                )
            ),

            "positive_folds": safe_int(
                aggregate.get(
                    "positive_folds",
                    0,
                )
            ),

            "negative_folds": safe_int(
                aggregate.get(
                    "negative_folds",
                    0,
                )
            ),

            "inconclusive_folds": safe_int(
                aggregate.get(
                    "inconclusive_folds",
                    0,
                )
            ),

            "validation_trades": safe_int(
                aggregate.get(
                    "validation_trades",
                    0,
                )
            ),

            "validation_win_rate": safe_float(
                aggregate.get(
                    "validation_win_rate",
                    0.0,
                )
            ),

            "validation_return": safe_float(
                aggregate.get(
                    "validation_return_sum",
                    0.0,
                )
            ),

            "validation_net_pnl": safe_float(
                aggregate.get(
                    "validation_net_pnl",
                    0.0,
                )
            ),

            "best_fold_return": safe_float(
                aggregate.get(
                    "best_fold_return",
                    0.0,
                )
            ),

            "worst_fold_return": safe_float(
                aggregate.get(
                    "worst_fold_return",
                    0.0,
                )
            ),

            "average_fold_return": safe_float(
                aggregate.get(
                    "average_fold_return",
                    0.0,
                )
            ),

            "average_fold_dd": safe_float(
                aggregate.get(
                    "average_fold_dd",
                    0.0,
                )
            ),

            "parameter_stability": result.get(
                "parameter_stability",
                {},
            ),

            "folds": result.get(
                "folds",
                [],
            ),
        }

        strategy.setdefault(
            "tests",
            {},
        ).setdefault(
            "walk_forward",
            [],
        ).append(
            record
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# LEARNING OBSERVATIONS
# =========================================================

def add_observation(
    strategy_id: str,
    observation: str,
    observation_type: str = "general",
) -> bool:
    """
    Strateji hakkında öğrenilmiş bir gözlem ekler.

    Örnek:

        "SMA 10/100 kombinasyonu fold'ların çoğunda seçildi."

    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        observation_record = {
            "timestamp": utc_now(),

            "type": clean_text(
                observation_type,
                "general",
            ),

            "text": clean_text(
                observation
            ),
        }

        strategy.setdefault(
            "learning",
            {},
        ).setdefault(
            "observations",
            [],
        ).append(
            observation_record
        )

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# CONFIDENCE
# =========================================================

def calculate_confidence(
    strategy: dict[str, Any],
) -> float:
    """
    Strateji için araştırma güven skoru üretir.

    Bu bir kârlılık tahmini değildir.

    Yalnızca:
        - test sayısı
        - validation
        - pozitif / negatif fold
        - validation return

    gibi araştırma sinyallerini özetler.

    Skor:
        0 - 100
    """

    tests = strategy.get(
        "tests",
        {},
    )

    backtests = tests.get(
        "backtests",
        [],
    )

    walk_forwards = tests.get(
        "walk_forward",
        [],
    )

    score = 0.0

    # -----------------------------------------------------
    # Backtest evidence
    # -----------------------------------------------------

    if backtests:

        score += min(
            len(backtests) * 5.0,
            20.0,
        )

    # -----------------------------------------------------
    # WFO evidence
    # -----------------------------------------------------

    if walk_forwards:

        latest = walk_forwards[-1]

        fold_count = safe_int(
            latest.get(
                "fold_count",
                0,
            )
        )

        positive_folds = safe_int(
            latest.get(
                "positive_folds",
                0,
            )
        )

        negative_folds = safe_int(
            latest.get(
                "negative_folds",
                0,
            )
        )

        validation_return = safe_float(
            latest.get(
                "validation_return",
                0.0,
            )
        )

        if fold_count > 0:

            positive_ratio = (
                positive_folds
                / fold_count
            )

            negative_ratio = (
                negative_folds
                / fold_count
            )

            score += (
                positive_ratio
                * 35.0
            )

            score -= (
                negative_ratio
                * 15.0
            )

        if validation_return > 0:
            score += min(
                validation_return * 5.0,
                20.0,
            )

        elif validation_return < 0:
            score -= min(
                abs(validation_return)
                * 5.0,
                20.0,
            )

    score = max(
        0.0,
        min(
            100.0,
            score,
        ),
    )

    return round(
        score,
        2,
    )


# =========================================================
# UPDATE LEARNING STATUS
# =========================================================

def update_learning_status(
    strategy_id: str,
) -> bool:
    """
    Test sonuçlarına göre stratejinin araştırma durumunu
    günceller.

    Bu fonksiyon "kârlı olacak" iddiasında bulunmaz.
    """

    database = load_database()

    for strategy in database[
        "strategies"
    ]:

        if (
            strategy.get(
                "strategy_id"
            )
            != strategy_id
        ):
            continue

        confidence = calculate_confidence(
            strategy
        )

        tests = strategy.get(
            "tests",
            {},
        )

        walk_forwards = tests.get(
            "walk_forward",
            [],
        )

        learning = strategy.setdefault(
            "learning",
            {},
        )

        learning[
            "confidence"
        ] = confidence

        if walk_forwards:

            latest = walk_forwards[-1]

            positive = safe_int(
                latest.get(
                    "positive_folds",
                    0,
                )
            )

            negative = safe_int(
                latest.get(
                    "negative_folds",
                    0,
                )
            )

            validation_return = safe_float(
                latest.get(
                    "validation_return",
                    0.0,
                )
            )

            if (
                positive > negative
                and validation_return > 0
            ):

                strategy[
                    "status"
                ] = "PROMISING"

            elif (
                negative > positive
                and validation_return < 0
            ):

                strategy[
                    "status"
                ] = "REJECTED"

            else:

                strategy[
                    "status"
                ] = "VALIDATION"

        else:

            strategy[
                "status"
            ] = "TESTING"

        strategy[
            "updated_at"
        ] = utc_now()

        save_database(
            database
        )

        return True

    return False


# =========================================================
# SEARCH
# =========================================================

def search_strategies(
    query: str,
) -> list[
    dict[str, Any]
]:
    """
    İsim, açıklama, hypothesis, tag ve notlarda arama yapar.
    """

    query = clean_text(
        query
    ).lower()

    if not query:
        return []

    strategies = get_all_strategies()

    matches = []

    for strategy in strategies:

        searchable = " ".join(
            [
                clean_text(
                    strategy.get(
                        "name"
                    )
                ),

                clean_text(
                    strategy.get(
                        "description"
                    )
                ),

                clean_text(
                    strategy.get(
                        "hypothesis"
                    )
                ),

                clean_text(
                    strategy.get(
                        "notes"
                    )
                ),

                " ".join(
                    map(
                        str,
                        strategy.get(
                            "tags",
                            [],
                        ),
                    )
                ),
            ]
        ).lower()

        if query in searchable:

            matches.append(
                strategy
            )

    return matches


# =========================================================
# SUMMARY
# =========================================================

def build_summary() -> dict[str, Any]:
    """
    Knowledge Base genel özetini döndürür.
    """

    strategies = get_all_strategies()

    status_counts = {
        status: 0
        for status in VALID_STATUSES
    }

    for strategy in strategies:

        status = strategy.get(
            "status",
            "HYPOTHESIS",
        )

        if status not in status_counts:
            status = "HYPOTHESIS"

        status_counts[
            status
        ] += 1

    return {
        "total_strategies": len(
            strategies
        ),

        "status_counts": status_counts,

        "knowledge_base_file": str(
            KNOWLEDGE_BASE_FILE
        ),

        "updated_at": utc_now(),
    }


# =========================================================
# DEMO / TEST
# =========================================================

def create_demo_strategy() -> str:
    """
    Test amacıyla örnek strateji oluşturur.

    Gerçek işlem yapmaz.
    """

    strategy = create_strategy(
        name=(
            "THYAO Trend "
            "Research Candidate"
        ),

        description=(
            "SMA/EMA trend ve RSI "
            "filtrelerini kullanan "
            "araştırma stratejisi."
        ),

        source_type="market_hq",

        source_name=(
            "MarketHQ Walk-Forward"
        ),

        market="BIST",

        symbols=[
            "THYAO.IS",
        ],

        tags=[
            "trend",
            "SMA",
            "EMA",
            "RSI",
            "ATR",
            "BIST",
        ],

        hypothesis=(
            "Orta ve uzun vadeli hareketli "
            "ortalama trendi ile RSI filtresinin "
            "birlikte kullanılması, belirli "
            "piyasa koşullarında daha istikrarlı "
            "sinyaller üretebilir."
        ),

        notes=(
            "İlk araştırma adayı. "
            "Walk-forward sonucu henüz "
            "olumlu olarak doğrulanmış değildir."
        ),
    )

    strategy_id = add_strategy(
        strategy
    )

    set_strategy_parameters(
        strategy_id,
        {
            "sma_fast": 10,
            "sma_slow": 100,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 65,
            "stop_atr_multiplier": 1.5,
            "target_atr_multiplier": 3.0,
        },
    )

    add_rule(
        strategy_id,
        "entry",
        "Trend göstergeleri ve RSI birlikte değerlendirilir.",
    )

    add_rule(
        strategy_id,
        "risk",
        "ATR tabanlı stop ve hedef kullanılır.",
    )

    add_observation(
        strategy_id,
        (
            "WFO V2 sonucunda SMA 10/100, "
            "EMA 20/50, RSI 14/30/65 ve "
            "target ATR 3.0 kombinasyonları "
            "fold'ların önemli bölümünde tekrarlandı."
        ),
        "walk_forward",
    )

    return strategy_id


# =========================================================
# MAIN TEST
# =========================================================

def main() -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "MarketHQ STRATEGY KNOWLEDGE BASE V1"
    )

    print(
        "=" * 70
    )

    database = load_database()

    print()
    print(
        f"Knowledge Base : "
        f"{KNOWLEDGE_BASE_FILE}"
    )

    print(
        f"Mevcut strateji: "
        f"{len(database['strategies'])}"
    )

    # -----------------------------------------------------
    # Demo strategy
    # -----------------------------------------------------

    strategy_id = create_demo_strategy()

    print()
    print(
        "✅ Test stratejisi oluşturuldu."
    )

    print(
        f"Strategy ID: {strategy_id}"
    )

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    update_learning_status(
        strategy_id
    )

    strategy = get_strategy(
        strategy_id
    )

    if strategy:

        print()
        print(
            "STRATEJİ"
        )

        print(
            f"Name       : "
            f"{strategy['name']}"
        )

        print(
            f"Status     : "
            f"{strategy['status']}"
        )

        print(
            f"Confidence : "
            f"{strategy['learning']['confidence']}"
        )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    summary = build_summary()

    print()
    print(
        "KNOWLEDGE BASE ÖZET"
    )

    print(
        f"Toplam strateji: "
        f"{summary['total_strategies']}"
    )

    print(
        f"Dosya: "
        f"{summary['knowledge_base_file']}"
    )

    print()
    print(
        "=" * 70
    )

    print(
        "Strategy Knowledge Base testi tamamlandı."
    )

    print(
        "=" * 70
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
