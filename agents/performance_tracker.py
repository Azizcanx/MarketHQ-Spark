import json
import os

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from email.utils import parsedate_to_datetime

import yfinance as yf


DATA_FILE = "performance_data_v2.json"


# =========================================================
# DOSYA
# =========================================================

def load_records():

    if not os.path.exists(DATA_FILE):
        return []

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if isinstance(data, list):
            return data

        return []

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return []


def save_records(records):

    with open(
        DATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            records,
            file,
            ensure_ascii=False,
            indent=4,
        )


# =========================================================
# TARİH
# =========================================================

def parse_news_date(date_text):

    if not date_text:
        return None

    try:

        return parsedate_to_datetime(
            date_text
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


def today_utc():

    return datetime.now(
        timezone.utc
    ).date()


# =========================================================
# GETİRİ
# =========================================================

def calculate_return(
    entry_price,
    exit_price,
):

    if (
        entry_price is None
        or exit_price is None
    ):
        return None

    if entry_price == 0:
        return None

    return (
        (
            exit_price
            - entry_price
        )
        / entry_price
    ) * 100


def calculate_strategy_return(
    raw_return,
    direction,
):

    if raw_return is None:
        return None

    if direction == "Pozitif":
        return raw_return

    if direction == "Negatif":
        return -raw_return

    return None


# =========================================================
# TARİHSEL VERİ
# =========================================================

def get_future_prices(
    symbol,
    news_date,
    days_forward=20,
):

    parsed_date = parse_news_date(
        news_date
    )

    if parsed_date is None:

        return {
            "status": "Veri Yok",
            "reason": (
                "Haber tarihi çözümlenemedi."
            ),
        }

    news_day = parsed_date.date()
    today = today_utc()

    # Haber bugüne veya son birkaç güne aitse
    # gelecek performans henüz oluşmamış olabilir.
    recent_news = (
        news_day
        >= today - timedelta(days=3)
    )

    end_date = (
        news_day
        + timedelta(days=days_forward)
    )

    try:

        ticker = yf.Ticker(symbol)

        history = ticker.history(
            start=news_day,
            end=end_date,
            auto_adjust=False,
        )

    except Exception as error:

        if recent_news:

            return {
                "status": "Bekliyor",
                "reason": (
                    "Haber çok yeni; "
                    "gelecek piyasa verisi "
                    "henüz oluşmamış olabilir."
                ),
            }

        return {
            "status": "Veri Yok",
            "reason": (
                f"Tarihsel veri alınamadı: "
                f"{error}"
            ),
        }

    if history.empty:

        if recent_news:

            return {
                "status": "Bekliyor",
                "reason": (
                    "Haber çok yeni; "
                    "sonraki işlem günü "
                    "henüz oluşmadı."
                ),
            }

        return {
            "status": "Veri Yok",
            "reason": (
                "Tarihsel veri bulunamadı."
            ),
        }

    history = history[
        history["Open"].notna()
        & history["Close"].notna()
    ].copy()

    if history.empty:

        if recent_news:

            return {
                "status": "Bekliyor",
                "reason": (
                    "Haber çok yeni; "
                    "geçerli fiyat henüz oluşmadı."
                ),
            }

        return {
            "status": "Veri Yok",
            "reason": (
                "Geçerli OHLC verisi bulunamadı."
            ),
        }

    future_rows = history[
        history.index.date > news_day
    ].copy()

    if future_rows.empty:

        if recent_news:

            return {
                "status": "Bekliyor",
                "reason": (
                    "Haberden sonra henüz "
                    "işlem günü oluşmadı."
                ),
            }

        return {
            "status": "Veri Yok",
            "reason": (
                "Haberden sonra işlem günü "
                "bulunamadı."
            ),
        }

    first_row = future_rows.iloc[0]

    entry_price = float(
        first_row["Open"]
    )

    one_day_price = float(
        first_row["Close"]
    )

    five_day_price = None

    if len(future_rows) >= 5:

        five_day_price = float(
            future_rows.iloc[4]["Close"]
        )

    return {

        "status": "Hazır",

        "entry_timestamp": (
            future_rows.index[
                0
            ].isoformat()
        ),

        "entry_price": (
            entry_price
        ),

        "one_day_price": (
            one_day_price
        ),

        "five_day_price": (
            five_day_price
        ),
    }


# =========================================================
# SİNYAL KAYDI
# =========================================================

def create_signal_record(
    article,
    analysis,
    target,
):

    return {

        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "article_id": article.get(
            "id"
        ),

        "title": article.get(
            "title"
        ),

        "published": article.get(
            "published"
        ),

        "source": article.get(
            "source"
        ),

        "link": article.get(
            "link"
        ),

        "relevant": analysis.get(
            "relevant"
        ),

        "importance": analysis.get(
            "importance"
        ),

        "confidence": analysis.get(
            "confidence"
        ),

        "market_direction": analysis.get(
            "market_direction"
        ),

        "affected_assets": analysis.get(
            "affected_assets",
            []
        ),

        "target_instrument": target,

        "symbol": target.get(
            "symbol"
        ),

        "instrument_type": target.get(
            "type"
        ),

        "name": target.get(
            "name"
        ),

        "evaluation_status": (
            "Bekliyor"
        ),

        "entry_timestamp": None,

        "entry_price": None,

        "one_day_price": None,

        "one_day_raw_return": None,

        "one_day_strategy_return": None,

        "one_day_result": None,

        "five_day_price": None,

        "five_day_raw_return": None,

        "five_day_strategy_return": None,

        "five_day_result": None,

        "evaluation_note": None,

        "evaluated_at": None,
    }


# =========================================================
# DUPLICATE
# =========================================================

def get_existing_signal(
    records,
    article_id,
    symbol,
):

    for record in records:

        if (
            record.get(
                "article_id"
            )
            == article_id
            and record.get(
                "symbol"
            )
            == symbol
        ):

            return record

    return None


# =========================================================
# SİNYALİ DEĞERLENDİR
# =========================================================

def evaluate_historical_signal(
    record,
):

    symbol = record.get(
        "symbol"
    )

    news_date = record.get(
        "published"
    )

    direction = record.get(
        "market_direction"
    )

    instrument_type = record.get(
        "instrument_type"
    )

    if not symbol or not news_date:

        record[
            "evaluation_status"
        ] = "Veri Yok"

        record[
            "evaluation_note"
        ] = (
            "Sembol veya haber tarihi eksik."
        )

        return record

    if direction not in [
        "Pozitif",
        "Negatif",
    ]:

        record[
            "evaluation_status"
        ] = "Skorlanamaz"

        record[
            "evaluation_note"
        ] = (
            "Yön Pozitif veya Negatif değil."
        )

        return record

    # Henüz performans skorlamasına
    # dahil etmediğimiz araçlar.
    if instrument_type in [
        "yield",
        "currency_index",
    ]:

        record[
            "evaluation_status"
        ] = "Skorlanamaz"

        record[
            "evaluation_note"
        ] = (
            "Bu araç için doğrudan "
            "hisse fiyatı getirisi "
            "kullanılmıyor."
        )

        return record

    prices = get_future_prices(
        symbol,
        news_date,
    )

    status = prices.get(
        "status"
    )

    # ========================================
    # BEKLİYOR
    # ========================================

    if status == "Bekliyor":

        record[
            "evaluation_status"
        ] = "Bekliyor"

        record[
            "evaluation_note"
        ] = prices.get(
            "reason"
        )

        return record

    # ========================================
    # VERİ YOK
    # ========================================

    if status != "Hazır":

        record[
            "evaluation_status"
        ] = "Veri Yok"

        record[
            "evaluation_note"
        ] = prices.get(
            "reason"
        )

        return record

    entry_price = prices[
        "entry_price"
    ]

    one_day_price = prices[
        "one_day_price"
    ]

    five_day_price = prices[
        "five_day_price"
    ]

    one_day_raw = calculate_return(
        entry_price,
        one_day_price,
    )

    one_day_strategy = (
        calculate_strategy_return(
            one_day_raw,
            direction,
        )
    )

    five_day_raw = calculate_return(
        entry_price,
        five_day_price,
    )

    five_day_strategy = (
        calculate_strategy_return(
            five_day_raw,
            direction,
        )
    )

    record[
        "evaluation_status"
    ] = "Tamamlandı"

    record[
        "evaluation_note"
    ] = None

    record[
        "entry_timestamp"
    ] = prices[
        "entry_timestamp"
    ]

    record[
        "entry_price"
    ] = entry_price

    record[
        "one_day_price"
    ] = one_day_price

    record[
        "one_day_raw_return"
    ] = one_day_raw

    record[
        "one_day_strategy_return"
    ] = one_day_strategy

    record[
        "five_day_price"
    ] = five_day_price

    record[
        "five_day_raw_return"
    ] = five_day_raw

    record[
        "five_day_strategy_return"
    ] = five_day_strategy

    # ========================================
    # +1 GÜN
    # ========================================

    if one_day_strategy is None:

        record[
            "one_day_result"
        ] = "Skorlanamaz"

    elif one_day_strategy > 0:

        record[
            "one_day_result"
        ] = "Doğru"

    elif one_day_strategy < 0:

        record[
            "one_day_result"
        ] = "Yanlış"

    else:

        record[
            "one_day_result"
        ] = "Nötr"

    # ========================================
    # +5 GÜN
    # ========================================

    if five_day_strategy is None:

        record[
            "five_day_result"
        ] = "Bekliyor"

    elif five_day_strategy > 0:

        record[
            "five_day_result"
        ] = "Doğru"

    elif five_day_strategy < 0:

        record[
            "five_day_result"
        ] = "Yanlış"

    else:

        record[
            "five_day_result"
        ] = "Nötr"

    record[
        "evaluated_at"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    return record


# =========================================================
# SİNYALİ KAYDET / GÜNCELLE
# =========================================================

def save_signal(
    article,
    analysis,
    target,
):

    records = load_records()

    article_id = article.get(
        "id"
    )

    symbol = target.get(
        "symbol"
    )

    existing = get_existing_signal(
        records,
        article_id,
        symbol,
    )

    # -----------------------------------------
    # VAR OLAN SİNYAL
    # -----------------------------------------

    if existing is not None:

        # Daha önce "Bekliyor" veya
        # "Veri Yok" ise yeniden dene.
        if existing.get(
            "evaluation_status"
        ) in [
            "Bekliyor",
            "Veri Yok",
        ]:

            updated = (
                evaluate_historical_signal(
                    existing
                )
            )

            save_records(
                records
            )

            return updated

        return existing

    # -----------------------------------------
    # YENİ SİNYAL
    # -----------------------------------------

    record = create_signal_record(
        article,
        analysis,
        target,
    )

    record = evaluate_historical_signal(
        record
    )

    records.append(
        record
    )

    save_records(
        records
    )

    return record


# =========================================================
# BEKLEYENLERİ TEKRAR DEĞERLENDİR
# =========================================================

def update_pending_signals():

    records = load_records()

    changed = False

    for record in records:

        status = record.get(
            "evaluation_status"
        )

        if status not in [
            "Bekliyor",
            "Veri Yok",
        ]:

            continue

        before = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
        )

        evaluate_historical_signal(
            record
        )

        after = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
        )

        if before != after:
            changed = True

    if changed:

        save_records(
            records
        )

    return records


# =========================================================
# İSTATİSTİK
# =========================================================

def get_statistics():

    records = load_records()

    completed = [
        record
        for record in records
        if record.get(
            "evaluation_status"
        ) == "Tamamlandı"
    ]

    one_day_completed = [
        record
        for record in completed
        if record.get(
            "one_day_result"
        ) in [
            "Doğru",
            "Yanlış",
            "Nötr",
        ]
    ]

    five_day_completed = [
        record
        for record in completed
        if record.get(
            "five_day_result"
        ) in [
            "Doğru",
            "Yanlış",
            "Nötr",
        ]
    ]

    one_day_correct = sum(
        1
        for record
        in one_day_completed
        if record.get(
            "one_day_result"
        ) == "Doğru"
    )

    one_day_wrong = sum(
        1
        for record
        in one_day_completed
        if record.get(
            "one_day_result"
        ) == "Yanlış"
    )

    five_day_correct = sum(
        1
        for record
        in five_day_completed
        if record.get(
            "five_day_result"
        ) == "Doğru"
    )

    five_day_wrong = sum(
        1
        for record
        in five_day_completed
        if record.get(
            "five_day_result"
        ) == "Yanlış"
    )

    one_day_returns = [
        record[
            "one_day_strategy_return"
        ]
        for record
        in one_day_completed
        if record.get(
            "one_day_strategy_return"
        ) is not None
    ]

    five_day_returns = [
        record[
            "five_day_strategy_return"
        ]
        for record
        in five_day_completed
        if record.get(
            "five_day_strategy_return"
        ) is not None
    ]

    one_day_win_rate = None

    if one_day_completed:

        one_day_win_rate = (
            one_day_correct
            / len(one_day_completed)
        ) * 100

    five_day_win_rate = None

    if five_day_completed:

        five_day_win_rate = (
            five_day_correct
            / len(five_day_completed)
        ) * 100

    average_one_day_return = None

    if one_day_returns:

        average_one_day_return = (
            sum(one_day_returns)
            / len(one_day_returns)
        )

    average_five_day_return = None

    if five_day_returns:

        average_five_day_return = (
            sum(five_day_returns)
            / len(five_day_returns)
        )

    pending = sum(
        1
        for record in records
        if record.get(
            "evaluation_status"
        ) == "Bekliyor"
    )

    unavailable = sum(
        1
        for record in records
        if record.get(
            "evaluation_status"
        ) == "Veri Yok"
    )

    unscored = sum(
        1
        for record in records
        if record.get(
            "evaluation_status"
        ) == "Skorlanamaz"
    )

    return {

        "total": len(completed),

        "pending": pending,

        "unavailable": unavailable,

        "unscored": unscored,

        "one_day_correct": (
            one_day_correct
        ),

        "one_day_wrong": (
            one_day_wrong
        ),

        "five_day_correct": (
            five_day_correct
        ),

        "five_day_wrong": (
            five_day_wrong
        ),

        "one_day_win_rate": (
            one_day_win_rate
        ),

        "five_day_win_rate": (
            five_day_win_rate
        ),

        "average_one_day_return": (
            average_one_day_return
        ),

        "average_five_day_return": (
            average_five_day_return
        ),
    }
