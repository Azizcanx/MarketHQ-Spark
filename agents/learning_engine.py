import sys
from pathlib import Path
from typing import Any
import math


# =========================================================
# MARKET HQ PROJE KLASÖRÜNÜ PYTHON PATH'E EKLE
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# DATABASE
# =========================================================

from database import (
    add_experiment_result,
    create_learning_experiment,
    get_connection,
    get_learned_rules,
    init_db,
    save_learned_rule,
)


# =========================================================
# SAYI KONTROLÜ
# =========================================================

def is_number(value: Any) -> bool:

    try:
        number = float(value)

        return math.isfinite(number)

    except (TypeError, ValueError):

        return False


# =========================================================
# GETIRI HESAPLA
# =========================================================

def calculate_return(
    entry_price: float | None,
    future_price: float | None,
) -> float | None:

    if not is_number(entry_price):
        return None

    if not is_number(future_price):
        return None

    entry = float(entry_price)
    future = float(future_price)

    if entry <= 0:
        return None

    return (
        (future - entry)
        / entry
        * 100.0
    )


# =========================================================
# SİNYAL SONUCU
# =========================================================

def evaluate_direction(
    signal_direction: str,
    return_value: float | None,
) -> str:

    if return_value is None:

        return "Veri Yok"

    if signal_direction == "Pozitif":

        if return_value > 0:
            return "Doğru"

        if return_value < 0:
            return "Yanlış"

        return "Nötr"

    if signal_direction == "Negatif":

        if return_value < 0:
            return "Doğru"

        if return_value > 0:
            return "Yanlış"

        return "Nötr"

    return "Skorlanamaz"


# =========================================================
# DENEY OLUŞTUR
# =========================================================

def create_method_experiment(
    method_name: str,
    symbol: str,
    signal_direction: str,
    method_type: str = "indicator",
    market: str | None = None,
    timeframe: str = "1d",
    knowledge_id: int | None = None,
) -> int:

    experiment_id = create_learning_experiment(
        method_name=method_name,
        symbol=symbol,
        method_type=method_type,
        market=market,
        timeframe=timeframe,
        signal_direction=signal_direction,
        parameters={
            "entry_policy": "next_observation_open",
            "evaluation_windows": [
                "1d",
                "5d",
                "20d",
            ],
        },
        knowledge_id=knowledge_id,
    )

    return experiment_id


# =========================================================
# GÖZLEM EKLE
# =========================================================

def add_observation(
    experiment_id: int,
    observation_date: str,
    entry_price: float,
    price_1d: float | None,
    price_5d: float | None,
    price_20d: float | None,
    signal_direction: str,
    market_regime: str | None = None,
    volume_state: str | None = None,
    volatility_state: str | None = None,
) -> int:

    return_1d = calculate_return(
        entry_price,
        price_1d,
    )

    return_5d = calculate_return(
        entry_price,
        price_5d,
    )

    return_20d = calculate_return(
        entry_price,
        price_20d,
    )

    result_1d = evaluate_direction(
        signal_direction,
        return_1d,
    )

    result_5d = evaluate_direction(
        signal_direction,
        return_5d,
    )

    result_20d = evaluate_direction(
        signal_direction,
        return_20d,
    )

    result_id = add_experiment_result(
        experiment_id=experiment_id,
        observation_date=observation_date,
        entry_price=entry_price,
        price_1d=price_1d,
        price_5d=price_5d,
        price_20d=price_20d,
        return_1d=return_1d,
        return_5d=return_5d,
        return_20d=return_20d,
        result_1d=result_1d,
        result_5d=result_5d,
        result_20d=result_20d,
        market_regime=market_regime,
        volume_state=volume_state,
        volatility_state=volatility_state,
    )

    return result_id


# =========================================================
# SONUÇLARDAN KURAL ÖĞREN
# =========================================================

def learn_rule_from_results(
    method_name: str,
    symbol: str,
    timeframe: str = "1d",
    condition_name: str = "all_observations",
    method_type: str = "indicator",
    market: str | None = None,
) -> dict[str, Any]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                er.return_1d,
                er.return_5d,
                er.return_20d,

                er.result_1d,
                er.result_5d,
                er.result_20d

            FROM experiment_results er

            INNER JOIN learning_experiments le
                ON le.id = er.experiment_id

            WHERE le.method_name = ?
            AND le.symbol = ?
            AND le.timeframe = ?
            """,
            (
                method_name,
                symbol,
                timeframe,
            ),
        ).fetchall()

    finally:

        conn.close()

    if not rows:

        return {
            "method_name": method_name,
            "symbol": symbol,
            "sample_size": 0,
            "learned": False,
            "reason": "Henüz deney sonucu yok.",
        }

    returns_1d = [
        float(row["return_1d"])
        for row in rows
        if row["return_1d"] is not None
    ]

    returns_5d = [
        float(row["return_5d"])
        for row in rows
        if row["return_5d"] is not None
    ]

    returns_20d = [
        float(row["return_20d"])
        for row in rows
        if row["return_20d"] is not None
    ]

    correct_1d = sum(
        1
        for row in rows
        if row["result_1d"] == "Doğru"
    )

    total_1d = sum(
        1
        for row in rows
        if row["result_1d"]
        in {
            "Doğru",
            "Yanlış",
        }
    )

    if total_1d > 0:

        success_rate = (
            correct_1d
            / total_1d
            * 100.0
        )

    else:

        success_rate = None

    if returns_1d:

        average_return = (
            sum(returns_1d)
            / len(returns_1d)
        )

    else:

        average_return = None

    if returns_5d:

        average_return_5d = (
            sum(returns_5d)
            / len(returns_5d)
        )

    else:

        average_return_5d = None

    if returns_20d:

        average_return_20d = (
            sum(returns_20d)
            / len(returns_20d)
        )

    else:

        average_return_20d = None

    best_return = (
        max(returns_1d)
        if returns_1d
        else None
    )

    worst_return = (
        min(returns_1d)
        if returns_1d
        else None
    )

    # =====================================================
    # ÖRNEKLEM BÜYÜKLÜĞÜNE GÖRE GÜVEN
    # =====================================================

    if total_1d >= 100:

        confidence = 0.95

    elif total_1d >= 50:

        confidence = 0.85

    elif total_1d >= 20:

        confidence = 0.70

    elif total_1d >= 10:

        confidence = 0.55

    else:

        confidence = 0.30

    if success_rate is not None:

        observation = (
            f"{method_name} / {symbol}: "
            f"{total_1d} skorlanabilir 1G gözlem, "
            f"başarı %{success_rate:.2f}."
        )

    else:

        observation = (
            f"{method_name} / {symbol}: "
            f"yeterli 1G veri yok."
        )

    save_learned_rule(
        method_name=method_name,
        condition_name=condition_name,
        sample_size=len(rows),
        method_type=method_type,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        success_rate=success_rate,
        average_return=average_return,
        average_return_5d=average_return_5d,
        average_return_20d=average_return_20d,
        best_return=best_return,
        worst_return=worst_return,
        confidence=confidence,
        observation=observation,
    )

    return {
        "method_name": method_name,
        "symbol": symbol,
        "sample_size": len(rows),
        "success_rate": success_rate,
        "average_return": average_return,
        "average_return_5d": average_return_5d,
        "average_return_20d": average_return_20d,
        "best_return": best_return,
        "worst_return": worst_return,
        "confidence": confidence,
        "learned": True,
    }


# =========================================================
# ÖĞRENİLMİŞ HAFIZA
# =========================================================

def get_method_memory(
    method_name: str,
    symbol: str | None = None,
) -> list[dict[str, Any]]:

    return get_learned_rules(
        method_name=method_name,
        symbol=symbol,
    )


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    init_db()

    print(
        "=== 🧠 LEARNING ENGINE ==="
    )

    print(
        "✅ Learning Engine hazır."
    )

    print(
        "✅ Database bağlantısı başarılı."
    )

    print(
        "Henüz gerçek deney çalıştırılmadı."
    )

    print(
        "Sıradaki aşama:"
    )

    print(
        "FIN[SYS] metodolojisi + "
        "BIST/US geçmiş verisi → "
        "otomatik deneyler"
    )
