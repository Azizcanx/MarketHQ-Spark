# -*- coding: utf-8 -*-

"""
MarketHQ Signal Diagnostic

Amaç:
    Backtest sırasında neden işlem oluşmadığını tespit etmek.

    BUY / SELL / WAIT dağılımını,
    signal score dağılımını
    ve Signal Engine hatalarını gösterir.

Gerçek işlem yapmaz.
"""

from __future__ import annotations

from collections import Counter

from agents.market_data_agent import get_signal_data
from signal_engine import (
    DEFAULT_CONFIG,
    add_indicators,
    generate_signal,
)


def main():

    symbol = "THYAO.IS"

    print()
    print("=" * 60)
    print("MARKETHQ SIGNAL DIAGNOSTIC")
    print("=" * 60)
    print()

    # -----------------------------------------------------
    # VERİ
    # -----------------------------------------------------

    print(
        f"Veri alınıyor: {symbol}"
    )

    try:

        data = get_signal_data(
            symbol,
            period="1y",
        )

    except Exception as exc:

        print(
            f"❌ Veri alınamadı: {exc}"
        )
        return

    if data is None or data.empty:

        print(
            "❌ Veri bulunamadı."
        )
        return

    print(
        f"📊 Ham bar sayısı: {len(data)}"
    )

    # -----------------------------------------------------
    # INDICATORS
    # -----------------------------------------------------

    try:

        df = add_indicators(
            data.copy(),
            DEFAULT_CONFIG,
        )

    except Exception as exc:

        print()
        print(
            f"❌ Indicator hesaplama hatası: {exc}"
        )
        return

    print(
        f"📈 Indicator sonrası bar: {len(df)}"
    )

    print()

    # -----------------------------------------------------
    # SIGNAL ANALYSIS
    # -----------------------------------------------------

    signal_counts = Counter()

    score_values = []

    errors = []

    examples = {
        "BUY": [],
        "SELL": [],
        "WAIT": [],
    }

    # -----------------------------------------------------
    # HER BAR
    # -----------------------------------------------------

    for index, row in df.iterrows():

        try:

            result = generate_signal(
                row,
                DEFAULT_CONFIG,
            )

            if isinstance(result, dict):

                signal = str(
                    result.get(
                        "signal",
                        "WAIT",
                    )
                ).upper()

                score = result.get(
                    "score"
                )

                reason = result.get(
                    "reason",
                    "",
                )

            else:

                signal = str(
                    result
                ).upper()

                score = None
                reason = ""

            # ---------------------------------------------
            # SIGNAL NORMALIZATION
            # ---------------------------------------------

            if signal not in {
                "BUY",
                "SELL",
                "WAIT",
            }:

                signal = "WAIT"

            signal_counts[
                signal
            ] += 1

            # ---------------------------------------------
            # SCORE
            # ---------------------------------------------

            if score is not None:

                try:

                    score_float = float(
                        score
                    )

                    score_values.append(
                        score_float
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            # ---------------------------------------------
            # EXAMPLES
            # ---------------------------------------------

            if (
                signal in examples
                and len(
                    examples[signal]
                ) < 5
            ):

                examples[signal].append(
                    {
                        "date": str(
                            index
                        ),
                        "close": row.get(
                            "Close"
                        ),
                        "score": score,
                        "reason": reason,
                    }
                )

        except Exception as exc:

            errors.append(
                {
                    "date": str(index),
                    "error": str(exc),
                }
            )

    # -----------------------------------------------------
    # REPORT
    # -----------------------------------------------------

    total = sum(
        signal_counts.values()
    )

    print("=" * 60)
    print("SIGNAL DAĞILIMI")
    print("=" * 60)

    print(
        f"Toplam bar          : {total}"
    )

    print(
        f"BUY                 : "
        f"{signal_counts.get('BUY', 0)}"
    )

    print(
        f"SELL                : "
        f"{signal_counts.get('SELL', 0)}"
    )

    print(
        f"WAIT                : "
        f"{signal_counts.get('WAIT', 0)}"
    )

    print(
        f"Signal Engine hata  : "
        f"{len(errors)}"
    )

    # -----------------------------------------------------
    # PERCENTAGES
    # -----------------------------------------------------

    if total > 0:

        buy_percent = (
            signal_counts.get(
                "BUY",
                0,
            )
            / total
            * 100
        )

        sell_percent = (
            signal_counts.get(
                "SELL",
                0,
            )
            / total
            * 100
        )

        wait_percent = (
            signal_counts.get(
                "WAIT",
                0,
            )
            / total
            * 100
        )

        print()

        print(
            f"BUY oranı           : "
            f"{buy_percent:.2f}%"
        )

        print(
            f"SELL oranı          : "
            f"{sell_percent:.2f}%"
        )

        print(
            f"WAIT oranı          : "
            f"{wait_percent:.2f}%"
        )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    print()
    print("=" * 60)
    print("SCORE ANALİZİ")
    print("=" * 60)

    if score_values:

        print(
            f"Score sayısı        : "
            f"{len(score_values)}"
        )

        print(
            f"Minimum score       : "
            f"{min(score_values):.2f}"
        )

        print(
            f"Maksimum score      : "
            f"{max(score_values):.2f}"
        )

        average_score = (
            sum(score_values)
            / len(score_values)
        )

        print(
            f"Ortalama score      : "
            f"{average_score:.2f}"
        )

    else:

        print(
            "Score bilgisi bulunamadı."
        )

    # -----------------------------------------------------
    # SIGNAL EXAMPLES
    # -----------------------------------------------------

    print()
    print("=" * 60)
    print("BUY ÖRNEKLERİ")
    print("=" * 60)

    if examples["BUY"]:

        for item in examples["BUY"]:

            print(
                f"{item['date']} | "
                f"Close={item['close']} | "
                f"Score={item['score']}"
            )

            if item["reason"]:

                print(
                    f"  Sebep: "
                    f"{item['reason']}"
                )

    else:

        print(
            "BUY sinyali yok."
        )

    print()
    print("=" * 60)
    print("SELL ÖRNEKLERİ")
    print("=" * 60)

    if examples["SELL"]:

        for item in examples["SELL"]:

            print(
                f"{item['date']} | "
                f"Close={item['close']} | "
                f"Score={item['score']}"
            )

            if item["reason"]:

                print(
                    f"  Sebep: "
                    f"{item['reason']}"
                )

    else:

        print(
            "SELL sinyali yok."
        )

    # -----------------------------------------------------
    # WAIT EXAMPLES
    # -----------------------------------------------------

    print()
    print("=" * 60)
    print("WAIT ÖRNEKLERİ")
    print("=" * 60)

    for item in examples["WAIT"]:

        print(
            f"{item['date']} | "
            f"Close={item['close']} | "
            f"Score={item['score']}"
        )

        if item["reason"]:

            print(
                f"  Sebep: "
                f"{item['reason']}"
            )

    # -----------------------------------------------------
    # ERRORS
    # -----------------------------------------------------

    if errors:

        print()
        print("=" * 60)
        print("SIGNAL ENGINE HATALARI")
        print("=" * 60)

        for error in errors[:10]:

            print(
                f"{error['date']} | "
                f"{error['error']}"
            )

    # -----------------------------------------------------
    # FINAL DIAGNOSIS
    # -----------------------------------------------------

    print()
    print("=" * 60)
    print("ÖN TEŞHİS")
    print("=" * 60)

    buy_count = signal_counts.get(
        "BUY",
        0,
    )

    sell_count = signal_counts.get(
        "SELL",
        0,
    )

    wait_count = signal_counts.get(
        "WAIT",
        0,
    )

    if errors:

        print(
            "⚠️ Signal Engine içerisinde hata var."
        )

        print(
            "Önce hataları düzelteceğiz."
        )

    elif buy_count == 0 and sell_count == 0:

        print(
            "⚠️ Hiç BUY/SELL üretilmemiş."
        )

        print(
            "Problem büyük ihtimalle "
            "Signal Engine skor/eşik sisteminde."
        )

    elif buy_count + sell_count < 5:

        print(
            "⚠️ Çok az BUY/SELL üretilmiş."
        )

        print(
            "Signal Engine fazla seçici olabilir."
        )

    else:

        print(
            "✅ Signal Engine yeterli sayıda "
            "BUY/SELL üretiyor."
        )

        print(
            "Problem Backtest Engine tarafında "
            "aranmalı."
        )

    print()
    print(
        "Diagnostic tamamlandı."
    )
    print()


if __name__ == "__main__":
    main()

