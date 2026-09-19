import time
from datetime import datetime

from agents.news_agent import prepare_news
from agents.analyst_agent import analyze_news
from agents.turkey_agent import (
    prepare_turkey_news,
    get_turkey_market_data,
    get_company_updates,
)
from agents.market_data_agent import (
    get_market_data,
    validate_market_record,
)
from agents.performance_tracker import (
    save_signal,
    get_statistics,
    update_pending_signals,
)

from runtime_state import (
    initialize_runtime_state,
    set_agent_status,
    set_system_status,
)


# =========================================================
# RUNTIME INIT
# =========================================================

initialize_runtime_state()


# =========================================================
# HEADER
# =========================================================

def print_header():
    print("\n" + "=" * 60)
    print("🏢 MARKET HQ")
    print("=" * 60)

    print(
        f"🕒 Çalışma zamanı: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print("=" * 60)


# =========================================================
# SAFE CALL
# =========================================================

def safe_call(
    label,
    function,
    default=None,
    agent_id=None,
):
    if agent_id:
        set_agent_status(
            agent_id,
            "WORKING",
            f"{label} çalışıyor...",
            progress=10,
        )

    try:
        result = function()

        print(f"✅ {label}")

        if agent_id:
            set_agent_status(
                agent_id,
                "COMPLETED",
                f"{label} tamamlandı.",
                progress=100,
            )

        return result

    except Exception as exc:
        print(f"❌ {label} başarısız")
        print(f"   Hata: {exc}")

        if agent_id:
            set_agent_status(
                agent_id,
                "ERROR",
                f"{label} başarısız.",
                progress=0,
                error=str(exc),
            )

        return default


# =========================================================
# NEWS PIPELINE
# =========================================================

def run_news_pipeline():
    print("\n" + "-" * 60)
    print("🇺🇸 HABER PIPELINE")
    print("-" * 60)

    news = safe_call(
        "News Agent",
        prepare_news,
        default=[],
        agent_id="news",
    )

    if not news:
        print("ℹ️ Haber adayı bulunamadı.")

        set_agent_status(
            "news",
            "COMPLETED",
            "Haber adayı bulunamadı.",
            progress=100,
        )

        return []

    print(
        f"📰 Hazırlanan haber adayı: "
        f"{len(news)}"
    )

    set_agent_status(
        "news",
        "COMPLETED",
        f"{len(news)} haber adayı hazırlandı.",
        progress=100,
    )

    return news


# =========================================================
# TURKEY PIPELINE
# =========================================================

def run_turkey_pipeline():
    print("\n" + "-" * 60)
    print("🇹🇷 TÜRKİYE PIPELINE")
    print("-" * 60)

    turkey_news = safe_call(
        "Turkey News Agent",
        prepare_turkey_news,
        default=[],
        agent_id="turkey_news",
    )

    turkey_market_data = safe_call(
        "Türkiye Market Data",
        get_turkey_market_data,
        default=[],
        agent_id="turkey_market",
    )

    company_updates = safe_call(
        "Company Updates",
        get_company_updates,
        default=[],
        agent_id="company_updates",
    )

    print(
        f"📰 Türkiye haberleri: "
        f"{len(turkey_news)}"
    )

    print(
        f"📊 Türkiye piyasa kayıtları: "
        f"{len(turkey_market_data)}"
    )

    print(
        f"🏢 Şirket bildirimleri: "
        f"{len(company_updates)}"
    )

    return {
        "news": turkey_news,
        "market_data": turkey_market_data,
        "company_updates": company_updates,
    }


# =========================================================
# MARKET DATA PIPELINE
# =========================================================

def run_market_data_pipeline():
    print("\n" + "-" * 60)
    print("📈 MARKET DATA PIPELINE")
    print("-" * 60)

    set_agent_status(
        "market_data",
        "WORKING",
        "Piyasa verileri alınıyor...",
        progress=10,
    )

    market_data = safe_call(
        "Market Data Agent",
        get_market_data,
        default=[],
        agent_id="market_data",
    )

    valid_market_data = []

    total_records = len(market_data)

    if total_records == 0:
        print("ℹ️ Piyasa kaydı bulunamadı.")

        set_agent_status(
            "market_data",
            "COMPLETED",
            "Piyasa kaydı bulunamadı.",
            progress=100,
        )

        return []

    for index, record in enumerate(
        market_data,
        start=1,
    ):
        try:
            if validate_market_record(record):
                valid_market_data.append(record)

        except Exception as exc:
            print(
                f"⚠️ Geçersiz kayıt kontrolünde hata: "
                f"{exc}"
            )

        progress = int(
            10
            + (
                index
                / total_records
            )
            * 85
        )

        set_agent_status(
            "market_data",
            "WORKING",
            (
                f"Veri doğrulanıyor "
                f"({index}/{total_records})"
            ),
            progress=progress,
        )

    print(
        f"📥 Toplam piyasa kaydı: "
        f"{len(market_data)}"
    )

    print(
        f"✅ Geçerli piyasa kaydı: "
        f"{len(valid_market_data)}"
    )

    print(
        f"⚠️ Elenen kayıt: "
        f"{len(market_data) - len(valid_market_data)}"
    )

    set_agent_status(
        "market_data",
        "COMPLETED",
        (
            f"{len(valid_market_data)} "
            f"geçerli piyasa kaydı."
        ),
        progress=100,
    )

    return valid_market_data


# =========================================================
# PERFORMANCE UPDATE
# =========================================================

def update_performance():
    print("\n" + "-" * 60)
    print("⏱️ PENDING SIGNAL UPDATE")
    print("-" * 60)

    set_agent_status(
        "performance",
        "WORKING",
        "Bekleyen sinyaller güncelleniyor...",
        progress=25,
    )

    try:
        update_pending_signals()

        print("✅ Bekleyen sinyaller güncellendi.")

        set_agent_status(
            "performance",
            "COMPLETED",
            "Bekleyen sinyaller güncellendi.",
            progress=100,
        )

    except Exception as exc:
        print(
            "❌ Bekleyen sinyaller güncellenemedi."
        )

        print(
            f"   Hata: {exc}"
        )

        set_agent_status(
            "performance",
            "ERROR",
            "Bekleyen sinyaller güncellenemedi.",
            progress=0,
            error=str(exc),
        )


# =========================================================
# AI ANALYST
# =========================================================

def run_analyst(news, turkey_news=None):
    print("\n" + "-" * 60)
    print("🤖 AI ANALYST")
    print("-" * 60)

    if turkey_news is None:
        turkey_news = []

    if not news and not turkey_news:
        print("ℹ️ Analiz edilecek haber yok.")

        set_agent_status(
            "analyst",
            "COMPLETED",
            "Analiz edilecek haber yok.",
            progress=100,
        )

        return []

    # -----------------------------------------------------
    # GENEL + TÜRKİYE HABERLERİNİ BİRLEŞTİR
    # -----------------------------------------------------

    general_news = news[:3]
    local_news = turkey_news[:3]

    combined_news = general_news + local_news

    # Aynı URL varsa tekrar analiz etme
    unique_news = []
    seen_urls = set()

    for article in combined_news:
        url = article.get("url")

        if url:
            if url in seen_urls:
                continue

            seen_urls.add(url)

        unique_news.append(article)

    test_news = unique_news[:6]

    print(
        f"🌎 Genel haber: "
        f"{len(general_news)}"
    )

    print(
        f"🇹🇷 Türkiye haber: "
        f"{len(local_news)}"
    )

    print(
        f"🧠 Toplam analiz kuyruğu: "
        f"{len(test_news)}"
    )

    set_agent_status(
        "analyst",
        "WORKING",
        (
            f"{len(test_news)} haber "
            f"analiz ediliyor..."
        ),
        progress=20,
    )

    analyzed_news = safe_call(
        "Analyst Agent",
        lambda: analyze_news(test_news),
        default=[],
        agent_id="analyst",
    )

    print(
        f"✅ Analiz tamamlanan haber: "
        f"{len(analyzed_news)}"
    )

    set_agent_status(
        "analyst",
        "COMPLETED",
        (
            f"{len(analyzed_news)} haber "
            f"analizi tamamlandı."
        ),
        progress=100,
    )

    return analyzed_news


# =========================================================
# DISPLAY ANALYST RESULTS
# =========================================================

def display_analyst_results(analyzed_news):
    print("\n" + "=" * 60)
    print("🧠 AI ANALYST SONUÇLARI")
    print("=" * 60)

    if not analyzed_news:
        print("ℹ️ Gösterilecek analiz sonucu yok.")
        return

    for number, article in enumerate(
        analyzed_news,
        start=1,
    ):
        title = article.get(
            "title",
            "Başlıksız haber",
        )

        analysis = article.get(
            "analysis",
            {},
        )

        print(
            f"\n{number}. 📰 {title}"
        )

        print(
            f"   ✅ Relevant: "
            f"{analysis.get('relevant')}"
        )

        print(
            f"   ⭐ Önem: "
            f"{analysis.get('importance')}/10"
        )

        print(
            f"   📈 Yön: "
            f"{analysis.get('market_direction')}"
        )

        print(
            f"   🔎 Güven: "
            f"{analysis.get('confidence')}"
        )

        targets = analysis.get(
            "target_instruments",
            [],
        )

        if targets:
            print(
                "   🎯 Takip araçları:"
            )

            for target in targets:
                print(
                    f"      - "
                    f"{target.get('symbol', '?')} | "
                    f"{target.get('name', '?')}"
                )

        else:
            print(
                "   🎯 Takip araçları: "
                "Belirlenemedi"
            )

        print(
            f"   📝 Özet: "
            f"{analysis.get('summary', '-')}"
        )

        print(
            f"   💡 Gerekçe: "
            f"{analysis.get('reason', '-')}"
        )


# =========================================================
# PERFORMANCE TRACKER
# =========================================================

def run_performance_tracker(analyzed_news):
    print("\n" + "-" * 60)
    print("📊 PERFORMANCE TRACKER")
    print("-" * 60)

    set_agent_status(
        "performance",
        "WORKING",
        "Analiz sonuçları sinyale dönüştürülüyor...",
        progress=10,
    )

    saved_count = 0

    if not analyzed_news:
        print("ℹ️ Kaydedilecek analiz yok.")

        set_agent_status(
            "performance",
            "COMPLETED",
            "Kaydedilecek analiz yok.",
            progress=100,
        )

        return

    total_articles = len(analyzed_news)

    for article_index, article in enumerate(
        analyzed_news,
        start=1,
    ):
        analysis = article.get(
            "analysis",
            {},
        )

        relevant = analysis.get(
            "relevant",
            False,
        )

        importance = analysis.get(
            "importance",
            0,
        )

        direction = analysis.get(
            "market_direction",
        )

        if not relevant:
            continue

        if importance < 5:
            continue

        if direction not in [
            "Pozitif",
            "Negatif",
        ]:
            continue

        targets = analysis.get(
            "target_instruments",
            [],
        )

        if not targets:
            print(
                f"⚠️ Takip aracı yok: "
                f"{article.get('title', '-')}"
            )
            continue

        for target in targets:
            try:
                record = save_signal(
                    article,
                    analysis,
                    target,
                )

                saved_count += 1

                symbol = record.get(
                    "symbol",
                    target.get(
                        "symbol",
                        "?",
                    ),
                )

                status = record.get(
                    "evaluation_status",
                    "unknown",
                )

                print(
                    f"💾 {symbol} "
                    f"→ {status}"
                )

                if record.get(
                    "evaluation_note"
                ):
                    print(
                        f"   ℹ️ "
                        f"{record['evaluation_note']}"
                    )

                if record.get(
                    "entry_price"
                ) is not None:
                    print(
                        f"   📥 Giriş: "
                        f"{record['entry_price']:.4f}"
                    )

                if record.get(
                    "one_day_strategy_return"
                ) is not None:
                    print(
                        f"   ⏱️ +1 gün strateji: "
                        f"{record['one_day_strategy_return']:.2f}%"
                    )

                if record.get(
                    "five_day_strategy_return"
                ) is not None:
                    print(
                        f"   📅 +5 gün strateji: "
                        f"{record['five_day_strategy_return']:.2f}%"
                    )

            except Exception as exc:
                print(
                    f"❌ Sinyal kaydedilemedi: "
                    f"{target.get('symbol', '?')}"
                )

                print(
                    f"   Hata: {exc}"
                )

        progress = int(
            (
                article_index
                / total_articles
            )
            * 100
        )

        set_agent_status(
            "performance",
            "WORKING",
            (
                f"Analiz {article_index}/"
                f"{total_articles} işlendi. "
                f"{saved_count} sinyal kaydedildi."
            ),
            progress=progress,
        )

    print(
        f"\n💾 Bu çalışmada kaydedilen sinyal: "
        f"{saved_count}"
    )

    set_agent_status(
        "performance",
        "COMPLETED",
        (
            f"Çalışmada {saved_count} "
            f"sinyal kaydedildi."
        ),
        progress=100,
    )


# =========================================================
# PERFORMANCE DISPLAY
# =========================================================

def display_performance():
    print("\n" + "=" * 60)
    print("📈 PERFORMANCE SUMMARY")
    print("=" * 60)

    stats = safe_call(
        "Performance Tracker",
        get_statistics,
        default={},
        agent_id=None,
    )

    if not stats:
        print(
            "ℹ️ Performans istatistiği alınamadı."
        )
        return

    print(
        f"Tamamlanan sinyal: "
        f"{stats.get('total', 0)}"
    )

    print(
        f"Bekleyen sinyal: "
        f"{stats.get('pending', 0)}"
    )

    print(
        f"+1 gün doğru: "
        f"{stats.get('one_day_correct', 0)}"
    )

    print(
        f"+1 gün yanlış: "
        f"{stats.get('one_day_wrong', 0)}"
    )

    print(
        f"+5 gün doğru: "
        f"{stats.get('five_day_correct', 0)}"
    )

    print(
        f"+5 gün yanlış: "
        f"{stats.get('five_day_wrong', 0)}"
    )

    one_day_win_rate = stats.get(
        "one_day_win_rate"
    )

    if one_day_win_rate is not None:
        print(
            f"+1 gün başarı: "
            f"{one_day_win_rate:.2f}%"
        )
    else:
        print(
            "+1 gün başarı: "
            "Henüz yeterli veri yok."
        )

    five_day_win_rate = stats.get(
        "five_day_win_rate"
    )

    if five_day_win_rate is not None:
        print(
            f"+5 gün başarı: "
            f"{five_day_win_rate:.2f}%"
        )
    else:
        print(
            "+5 gün başarı: "
            "Henüz yeterli veri yok."
        )

    average_one_day_return = stats.get(
        "average_one_day_return"
    )

    if average_one_day_return is not None:
        print(
            f"Ortalama +1 gün strateji getirisi: "
            f"{average_one_day_return:.2f}%"
        )

    average_five_day_return = stats.get(
        "average_five_day_return"
    )

    if average_five_day_return is not None:
        print(
            f"Ortalama +5 gün strateji getirisi: "
            f"{average_five_day_return:.2f}%"
        )


# =========================================================
# SYSTEM STATUS
# =========================================================

def display_system_status():
    print("\n" + "=" * 60)
    print("🏢 MARKET HQ SYSTEM STATUS")
    print("=" * 60)

    services = [
        ("🇺🇸 News Agent", "news"),
        ("🇹🇷 Turkey News Agent", "turkey_news"),
        ("🇹🇷 Turkey Market Data", "turkey_market"),
        ("🏢 Company Updates", "company_updates"),
        ("📈 Market Data", "market_data"),
        ("🤖 Analyst Agent", "analyst"),
        ("📊 Performance Tracker", "performance"),
        ("🧪 Strategy Lab", "strategy_lab"),
        ("📚 FIN[SYS] Method Engine", "fin_sys"),
        ("🎥 YouTube Visual Engine", "youtube"),
    ]

    from runtime_state import get_runtime_state

    state = get_runtime_state()

    for service, agent_id in services:
        agent = state.get(
            "agents",
            {},
        ).get(
            agent_id,
            {},
        )

        status = agent.get(
            "status",
            "UNKNOWN",
        )

        detail = agent.get(
            "detail",
            "",
        )

        print(
            f"{service:<32} : "
            f"{status:<10} | "
            f"{detail}"
        )


# =========================================================
# MAIN ORCHESTRATOR
# =========================================================

def run_market_hq():
    start_time = time.perf_counter()

    set_system_status(
        "WORKING",
        "MarketHQ pipeline çalışıyor.",
    )

    set_agent_status(
        "hq",
        "WORKING",
        "MarketHQ pipeline başlatıldı.",
        progress=5,
    )

    print_header()

    try:
        set_agent_status(
            "hq",
            "WORKING",
            "News pipeline çalışıyor.",
            progress=10,
        )

        news = run_news_pipeline()

        set_agent_status(
            "hq",
            "WORKING",
            "Türkiye pipeline çalışıyor.",
            progress=25,
        )

        turkey_data = run_turkey_pipeline()

        set_agent_status(
            "hq",
            "WORKING",
            "Market Data pipeline çalışıyor.",
            progress=40,
        )

        valid_market_data = (
            run_market_data_pipeline()
        )

        set_agent_status(
            "hq",
            "WORKING",
            "Performans verileri güncelleniyor.",
            progress=55,
        )

        update_performance()

        set_agent_status(
            "hq",
            "WORKING",
            "AI Analyst çalışıyor.",
            progress=65,
        )

        # -------------------------------------------------
        # GENEL + TÜRKİYE HABERLERİNİ AI ANALYST'E GÖNDER
        # -------------------------------------------------

        analyzed_news = run_analyst(
            news,
            turkey_data["news"],
        )

        display_analyst_results(
            analyzed_news
        )

        set_agent_status(
            "hq",
            "WORKING",
            "Performance Tracker çalışıyor.",
            progress=80,
        )

        run_performance_tracker(
            analyzed_news
        )

        display_performance()

        elapsed = (
            time.perf_counter()
            - start_time
        )

        print("\n" + "=" * 60)
        print("📋 ÇALIŞMA ÖZETİ")
        print("=" * 60)

        print(
            f"🇺🇸 Haber adayı: "
            f"{len(news)}"
        )

        print(
            f"🇹🇷 Türkiye haberi: "
            f"{len(turkey_data['news'])}"
        )

        print(
            f"📊 Türkiye piyasa verisi: "
            f"{len(turkey_data['market_data'])}"
        )

        print(
            f"🏢 Şirket bildirimi: "
            f"{len(turkey_data['company_updates'])}"
        )

        print(
            f"📈 Geçerli market kaydı: "
            f"{len(valid_market_data)}"
        )

        print(
            f"🤖 AI analiz sayısı: "
            f"{len(analyzed_news)}"
        )

        print(
            f"⏱️ Toplam çalışma süresi: "
            f"{elapsed:.2f} saniye"
        )

        display_system_status()

        set_agent_status(
            "hq",
            "COMPLETED",
            (
                f"MarketHQ tamamlandı. "
                f"{elapsed:.2f} saniye."
            ),
            progress=100,
        )

        set_system_status(
            "COMPLETED",
            "MarketHQ pipeline başarıyla tamamlandı.",
        )

        print("\n" + "=" * 60)
        print("✅ MARKET HQ ÇALIŞMASI TAMAMLANDI")
        print("=" * 60)
        print()

    except Exception as exc:
        set_agent_status(
            "hq",
            "ERROR",
            "MarketHQ beklenmeyen hata ile durdu.",
            progress=0,
            error=str(exc),
        )

        set_system_status(
            "ERROR",
            f"MarketHQ hata verdi: {exc}",
        )

        print(
            "\n❌ MARKET HQ BEKLENMEYEN HATA"
        )

        print(
            f"   Hata: {exc}"
        )

        raise


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    run_market_hq()
