import math
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


# ============================================================
# MARKET CONFIGURATION
# ============================================================

SUPPORTED_MARKETS = {
    "BIST": "Borsa İstanbul",
    "US": "ABD",
}


BIST_SYMBOLS = [
    "AEFES.IS",
    "AKBNK.IS",
    "ASELS.IS",
    "ASTOR.IS",
    "BIMAS.IS",
    "EKGYO.IS",
    "ENKAI.IS",
    "EREGL.IS",
    "FROTO.IS",
    "GARAN.IS",
    "GUBRF.IS",
    "HALKB.IS",
    "ISCTR.IS",
    "KCHOL.IS",
    "KRDMD.IS",
    "MGROS.IS",
    "PASEU.IS",
    "PETKM.IS",
    "PGSUS.IS",
    "SAHOL.IS",
    "SASA.IS",
    "SISE.IS",
    "TAVHL.IS",
    "TCELL.IS",
    "THYAO.IS",
    "TOASO.IS",
    "TTKOM.IS",
    "TUPRS.IS",
    "ULKER.IS",
    "YKBNK.IS",
]


US_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "GOOG",
    "BRK-B",
    "JPM",
    "LLY",
    "V",
    "MA",
    "WMT",
    "XOM",
    "JNJ",
    "ORCL",
    "COST",
    "NFLX",
    "AMD",
    "QCOM",
    "ADBE",
    "CRM",
    "INTC",
    "MU",
    "CAT",
    "BA",
    "HD",
    "KO",
    "BKNG",
]


INDEX_SYMBOLS = [
    "^IXIC",
    "^GSPC",
    "^DJI",
    "XU030.IS",
    "XU100.IS",
]


SPECIAL_SYMBOLS = [
    "^TNX",
    "DX-Y.NYB",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value, default=None):
    """
    Güvenli şekilde float'a çevirir.
    """
    try:
        if value is None:
            return default

        number = float(value)

        if not math.isfinite(number):
            return default

        return number

    except (TypeError, ValueError):
        return default


def clean_symbol(symbol):
    """
    Yahoo Finance sembolünü güvenli şekilde string'e çevirir.
    """
    if symbol is None:
        return ""

    return str(symbol).strip()


def utc_timestamp():
    """
    UTC timestamp üretir.
    """
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# MARKET METADATA
# ============================================================

def detect_market(symbol):
    """
    Sembolün hangi piyasaya ait olduğunu belirler.
    """
    symbol = clean_symbol(symbol)

    if symbol.endswith(".IS"):
        return "BIST"

    return "US"


def detect_country(market):
    """
    Piyasa ülkesini belirler.
    """
    if market == "BIST":
        return "Türkiye"

    return "ABD"


def detect_currency(market):
    """
    Piyasa para birimini belirler.
    """
    if market == "BIST":
        return "TRY"

    return "USD"


def detect_exchange(market):
    """
    Borsa bilgisini belirler.
    """
    if market == "BIST":
        return "Borsa İstanbul"

    return "NASDAQ/NYSE"


def detect_instrument_type(symbol):
    """
    Enstrüman tipini tahmin eder.
    """
    symbol = clean_symbol(symbol)

    if symbol in INDEX_SYMBOLS:
        return "index"

    if symbol in SPECIAL_SYMBOLS:
        return "macro"

    return "stock"


def create_market_record(
    symbol,
    price,
    change_percent,
    volume,
    timestamp=None,
):
    """
    MarketHQ standart piyasa kaydı oluşturur.
    """

    symbol = clean_symbol(symbol)
    market = detect_market(symbol)

    return {
        "symbol": symbol,
        "market": market,
        "market_name": SUPPORTED_MARKETS.get(
            market,
            market,
        ),
        "country": detect_country(market),
        "currency": detect_currency(market),
        "exchange": detect_exchange(market),
        "instrument_type": detect_instrument_type(symbol),
        "name": symbol,
        "price": safe_float(price),
        "change_percent": safe_float(change_percent),
        "volume": safe_float(volume, 0),
        "timestamp": timestamp or utc_timestamp(),
        "source": "Yahoo Finance",
    }


# ============================================================
# OHLCV VALIDATION
# ============================================================

def validate_ohlcv(data):
    """
    Signal Engine'in kullanabileceği OHLCV DataFrame'ini doğrular.

    Gerekli kolonlar:
    Open
    High
    Low
    Close
    Volume
    """

    if data is None:
        return False

    if not isinstance(data, pd.DataFrame):
        return False

    if data.empty:
        return False

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    for column in required_columns:
        if column not in data.columns:
            return False

    return True


# ============================================================
# HISTORICAL DATA
# ============================================================

def fetch_ohlcv_history(
    symbol,
    period="1y",
    interval="1d",
):
    """
    Bir sembol için geçmiş OHLCV verisini çeker.

    Signal Engine için temel veri kaynağıdır.

    Örnek:
        fetch_ohlcv_history("THYAO.IS")

    Dönen kolonlar:
        Open
        High
        Low
        Close
        Volume
    """

    symbol = clean_symbol(symbol)

    if not symbol:
        return pd.DataFrame()

    try:
        ticker = yf.Ticker(symbol)

        history = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=False,
        )

        if history is None or history.empty:
            print(
                f"⚠️ OHLCV verisi bulunamadı: {symbol}"
            )
            return pd.DataFrame()

        required_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        missing = [
            column
            for column in required_columns
            if column not in history.columns
        ]

        if missing:
            print(
                f"⚠️ {symbol} eksik kolonlar: {missing}"
            )
            return pd.DataFrame()

        history = history[
            required_columns
        ].copy()

        history = history.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        )

        history["Volume"] = (
            pd.to_numeric(
                history["Volume"],
                errors="coerce",
            )
            .fillna(0)
        )

        for column in [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]:
            history[column] = pd.to_numeric(
                history[column],
                errors="coerce",
            )

        history = history.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        )

        history = history.sort_index()

        return history

    except Exception as exc:
        print(
            f"❌ OHLCV alınamadı "
            f"({symbol}): {exc}"
        )
        return pd.DataFrame()


# ============================================================
# LATEST MARKET SNAPSHOT
# ============================================================

def fetch_symbol_data(
    symbol,
    period="5d",
):
    """
    Bir sembolün güncel piyasa özetini getirir.

    Bu fonksiyon mevcut MarketHQ pipeline'ının
    kullandığı snapshot yapısını korur.
    """

    symbol = clean_symbol(symbol)

    if not symbol:
        return None

    try:
        history = fetch_ohlcv_history(
            symbol,
            period=period,
            interval="1d",
        )

        if history.empty:
            return None

        if len(history) < 1:
            return None

        latest = history.iloc[-1]

        price = safe_float(
            latest["Close"]
        )

        volume = safe_float(
            latest["Volume"],
            0,
        )

        change_percent = 0.0

        if len(history) >= 2:
            previous = safe_float(
                history.iloc[-2]["Close"]
            )

            if (
                previous is not None
                and previous != 0
                and price is not None
            ):
                change_percent = (
                    (price - previous)
                    / previous
                ) * 100

        timestamp = None

        try:
            timestamp = history.index[-1]

            if hasattr(
                timestamp,
                "to_pydatetime",
            ):
                timestamp = (
                    timestamp.to_pydatetime()
                )

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(
                    tzinfo=timezone.utc
                )

            timestamp = timestamp.isoformat()

        except Exception:
            timestamp = utc_timestamp()

        return create_market_record(
            symbol=symbol,
            price=price,
            change_percent=change_percent,
            volume=volume,
            timestamp=timestamp,
        )

    except Exception as exc:
        print(
            f"❌ Market verisi alınamadı "
            f"({symbol}): {exc}"
        )
        return None


# ============================================================
# MARKET GROUP FETCHERS
# ============================================================

def get_bist_data():
    """
    BIST hisselerinin güncel snapshot verisini getirir.
    """

    results = []

    for symbol in BIST_SYMBOLS:
        record = fetch_symbol_data(
            symbol
        )

        if record is not None:
            results.append(record)

    return results


def get_us_market_data():
    """
    ABD hisselerinin güncel snapshot verisini getirir.
    """

    results = []

    for symbol in US_SYMBOLS:
        record = fetch_symbol_data(
            symbol
        )

        if record is not None:
            results.append(record)

    return results


def get_index_data():
    """
    Endekslerin güncel snapshot verisini getirir.
    """

    results = []

    for symbol in INDEX_SYMBOLS:
        record = fetch_symbol_data(
            symbol
        )

        if record is not None:
            results.append(record)

    return results


def get_special_data():
    """
    Özel/makro sembollerin güncel verisini getirir.
    """

    results = []

    for symbol in SPECIAL_SYMBOLS:
        record = fetch_symbol_data(
            symbol
        )

        if record is not None:
            results.append(record)

    return results


def get_market_data():
    """
    Tüm güncel piyasa verilerini getirir.
    """

    results = []

    results.extend(
        get_bist_data()
    )

    results.extend(
        get_us_market_data()
    )

    results.extend(
        get_index_data()
    )

    results.extend(
        get_special_data()
    )

    return results


# ============================================================
# HISTORICAL DATA HELPERS
# ============================================================

def get_symbol_history(
    symbol,
    period="1y",
    interval="1d",
):
    """
    Signal Engine için doğrudan geçmiş OHLCV döndürür.
    """

    return fetch_ohlcv_history(
        symbol=symbol,
        period=period,
        interval=interval,
    )


def get_bist_history(
    period="1y",
    interval="1d",
):
    """
    Tüm BIST sembollerinin geçmiş verisini döndürür.

    Sonuç:
        {
            "THYAO.IS": DataFrame,
            "ASELS.IS": DataFrame,
            ...
        }
    """

    results = {}

    for symbol in BIST_SYMBOLS:
        history = get_symbol_history(
            symbol,
            period=period,
            interval=interval,
        )

        if not history.empty:
            results[symbol] = history

    return results


def get_us_history(
    period="1y",
    interval="1d",
):
    """
    Tüm ABD sembollerinin geçmiş verisini döndürür.
    """

    results = {}

    for symbol in US_SYMBOLS:
        history = get_symbol_history(
            symbol,
            period=period,
            interval=interval,
        )

        if not history.empty:
            results[symbol] = history

    return results


def get_index_history(
    period="1y",
    interval="1d",
):
    """
    Tüm endekslerin geçmiş verisini döndürür.
    """

    results = {}

    for symbol in INDEX_SYMBOLS:
        history = get_symbol_history(
            symbol,
            period=period,
            interval=interval,
        )

        if not history.empty:
            results[symbol] = history

    return results


# ============================================================
# SIGNAL ENGINE DATA
# ============================================================

def get_signal_data(
    symbol,
    period="1y",
    interval="1d",
):
    """
    Signal Engine'e hazır OHLCV verisi sağlar.

    Bu fonksiyon özellikle yeni Signal Engine
    mimarisi için kullanılacaktır.
    """

    history = get_symbol_history(
        symbol=symbol,
        period=period,
        interval=interval,
    )

    if history.empty:
        return pd.DataFrame()

    if not validate_ohlcv(history):
        print(
            f"⚠️ Geçersiz OHLCV verisi: {symbol}"
        )
        return pd.DataFrame()

    return history


def get_signal_data_batch(
    symbols,
    period="1y",
    interval="1d",
):
    """
    Birden fazla sembol için Signal Engine verisi döndürür.
    """

    results = {}

    if not symbols:
        return results

    for symbol in symbols:
        history = get_signal_data(
            symbol=symbol,
            period=period,
            interval=interval,
        )

        if not history.empty:
            results[
                clean_symbol(symbol)
            ] = history

    return results


# ============================================================
# VALIDATION
# ============================================================

def validate_market_record(record):
    """
    Güncel market snapshot kaydını doğrular.
    """

    if not isinstance(record, dict):
        return False

    required_fields = [
        "symbol",
        "market",
        "market_name",
        "country",
        "currency",
        "exchange",
        "instrument_type",
        "name",
        "price",
        "change_percent",
        "volume",
        "timestamp",
        "source",
    ]

    for field in required_fields:
        if field not in record:
            return False

    price = safe_float(
        record.get("price")
    )

    change_percent = safe_float(
        record.get("change_percent")
    )

    volume = safe_float(
        record.get("volume"),
        0,
    )

    if price is None:
        return False

    if change_percent is None:
        return False

    if volume is None:
        return False

    if price < 0:
        return False

    if volume < 0:
        return False

    return True


def validate_market_data(records):
    """
    Market snapshot listesini doğrular.
    """

    if not isinstance(records, list):
        return []

    valid_records = []

    for record in records:
        if validate_market_record(record):
            valid_records.append(record)

    return valid_records


# ============================================================
# DEBUG / TEST
# ============================================================

def print_history_summary(
    symbol,
    period="1y",
    interval="1d",
):
    """
    Geçmiş veri testini terminalde gösterir.
    """

    history = get_signal_data(
        symbol=symbol,
        period=period,
        interval=interval,
    )

    print()
    print("=" * 60)
    print("MarketHQ OHLCV TEST")
    print("=" * 60)
    print(
        f"Sembol       : {symbol}"
    )
    print(
        f"Periyot      : {period}"
    )
    print(
        f"Interval     : {interval}"
    )

    if history.empty:
        print(
            "❌ Veri alınamadı."
        )
        print("=" * 60)
        return False

    print(
        f"Bar sayısı   : {len(history)}"
    )

    print(
        f"İlk tarih    : {history.index[0]}"
    )

    print(
        f"Son tarih    : {history.index[-1]}"
    )

    print()
    print(
        "Son 5 kayıt:"
    )

    print(
        history.tail(5).to_string()
    )

    print("=" * 60)

    return True


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print(
        "🚀 MarketHQ Market Data Agent"
    )

    print(
        "📊 Güncel piyasa verisi test ediliyor..."
    )

    sample = fetch_symbol_data(
        "THYAO.IS"
    )

    if sample:
        print()
        print(
            "✅ Snapshot başarılı:"
        )
        print(
            sample
        )
    else:
        print(
            "❌ Snapshot alınamadı."
        )

    print()

    print(
        "📈 OHLCV geçmiş verisi test ediliyor..."
    )

    print_history_summary(
        "THYAO.IS",
        period="1y",
        interval="1d",
    )

    print()
    print(
        "✅ Market Data Agent testi tamamlandı."
    )

