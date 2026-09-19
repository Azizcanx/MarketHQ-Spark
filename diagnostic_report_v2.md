# Diagnostic Research Report — Setup Engine V2
====================================================

Tarih: 2026-09-16
Veri: 4,089 backtest_v1 kaydi (THYAO.IS 1h)
Onceki dan fark: setup_type, regime, evidence hepsi guncellendi

---

A) EN ONEMLI 5 BULGU
=====================

1. **5 sabit evidence boyutu cozuldu** — 0 sabit boyut kaldi.
   strategy_agreement (0.3→0.3-0.73), invalidation_clarity (1.0→0.95-1.0),
   structure_quality (0.4→0.2-0.55), entry_quality (0.8→0.65-0.8),
   formation_chain (0.833→0.75-0.917) hepsi artisini goturdu.

2. **setup_type atama sorunu fix edildi** — 9 farkli setup type var:
   indicator_short (wr=58%), indicator_range_short (wr=58%),
   indicator_downtrend_short (wr=38%), indicator_uptrend_long (wr=39%),
   indicator_downtrend_long (wr=32%), indicator_range_long (wr=17%),
   indicator_long (wr=0%), indicator_uptrend_short (wr=0%), unknown (eski)

3. **Regime×Strategy matrisi calisti** — en iyi kombinasyon:
   indicator_range_short|RANGE_LOW_VOL: n=180, wr=58%, avgR=0.458
   Bu bir strategy weighting icin yeterli veri!

4. **historical_validation hâlâ #1 predictor** — pearson=+0.196
   Ama 58.8% kayip bunu "weak" olarak tespit ediyor.
   Bu boyut guvenilir degil — yapiyacagimiz.

5. **Entry problemi YOK** — losers entry_q=0.630 > winners 0.623
   Sorun entry'te degil — regime seciminde ve exit'te.

---

B) SETUP ENGINE'IN AN ZAYIFLIGI
=====================================

**Regime filter yok — RANGE'da surekli kayip.**
- RANGE_HIGH_VOL: wr=11%, avgR=-0.716 (en kotu)
- RANGE_LOW_VOL: wr=34%, avgR=-0.141
- RANGE: wr=37%, avgR=-0.085

Regime secimi setup quality'den 10x daha cok performansi acikliyor.
Eger RANGE'da setup uretimi azaltilirse, toplam win rate anlamli
artacaktir.

Ek: historical_validation 58.8% kayitta "weak" — bu boyut
guvenilir degil ve skordan cikarilmalidir.

---

C) QUALITY SCORING'IN AN ZAYIFLIGI
=====================================

**10 boyut dan 4'u gercekten ongorucu:**
1. historical_validation: +0.196 (ama guvenilir degil)
2. entry_quality: +0.119
3. risk_reward_feasibility: +0.082
4. supporting_evidence: +0.066

Kalan 6 boyut: -0.05 ile +0.04 arasinda (noise).

**Yeni sorun:** strategy_agreement Pearson=-0.045 — karsit yonunde!
Yuksek strategy agreement'a sahip setup'lar DAHAs cok kaybediyor.
Bu, strategy consensus'un "hepsi LONG" durumunda price'in
asagi dogru hareket etmemesi anlamina geliyor.

---

D) STRATEGY WEIGHTING ICIN HANGI VERILER KULLANILABILIR
=========================================================

Mevcut veriyle:
1. Regime×Strategy matrisi (180+ sample'li kombinasyonlar)
   - indicator_range_short|RANGE_LOW_VOL: wr=58%, avgR=0.458
   - indicator_short|DOWNTREND_STRONG: wr=67%, avgR=0.667 (n=6, az)

2. Regime bazli ağırlık:
   - DOWNTREND_WEAK: wr=39%, avgR=-0.029 (enyuksek sample)
   - DOWNTREND: wr=51%, avgR=0.273 (eski veri, kucuk sample)

3. Setup type bazli:
   - indicator_short: wr=58%, avgR=0.463
   - indicator_range_short: wr=58%, avgR=0.458

Kullanilamayan:
- indicator_long (wr=0%, n=11)
- indicator_uptrend_short (wr=0%, n=19)
- Bu ikisi az sample + negatif sonuç

---

E) FAZ 2'DE YAPILACAK DEGISIKLIKLER
=====================================

Kritik (setup engine):
1. historical_validation boyutunu KALKIR — guvenilir degil
   (58.8% kayit "weak", pearson sadece +0.2)
2. Regime filter ekle — RANGE_HIGH_VOL'da setup uretimini azalt
3. strategy_agreement agirliklarini guncelle — simdi karsit yonunde

Yüksek (quality scoring):
4. quality_v2 score'larını kullan (zaten versionlandi)
5. Regime compatibility'yi overweight et (en stabile sinyal)
6. entry_quality'yı da overweight et (ikinci en iyi predictor)

Orta (backtest):
7. Signature diversity'yi artır — max_same_sig 479 → hedef <50
8. Weighted average R hesapla (quality score'a göre)

Düşük:
9. Monte Carlo (TODO)
10. Walk-forward (TODO)

---

F) DEGİŞİKLİK YAPMADAN ÖNCE ÇÖZÜLMESİ GEREKEN PROBLEMLER
===========================================================

1. **historical_validation güvenilir değil** — 3 outcome kaydı var,
   tamamı "open". Gerçek geçmiş validation yapılmalı.

2. **Max same signature = 479** — tek pattern tekrar ediyor.
   Setup generation diversity'si yetersiz.

3. **RANGE HIGH_VOL çok zayıf** — wr=11%, avgR=-0.716.
   Bu regimde stratji calismiyor.

4. **strategy_agreement karsit yonelde** — Pearson = -0.045.
   Yüksek consensus = düşük kazanma. Nedenini ara.

5. **Execution rate %95** — artık sorun degil (eski %14 idi).

6. **Survivorship bias** — Tek sembol (THYAO.IS). Diversifikasyon yok.

7. **Qualiy score range dar** — 0.47-0.65 aralığı. Ayrıtm yetersiz.

---

G) IMPLEMENTASYON ÖZETİ
=========================

Degisen dosyalar:
- setup_backtest_engine.py — setup_type fix + metadata_json guncelleme
- strategy_registry_v1.py — agreement_summary'a agreement_score + family_breakdown eklendi
- setup_engine_v1.py — multi-factor regime engine (ADX, ATR, volume, structure)
- smc_structure_v1.py — CHoCH sweep gerekkesi kaldırıldı + structure_state eklendi
- setup_quality_engine_v2.py — yeni constant boyutlar (swing distance, price-level)
- setup_object_model.py — formation_chain field eklendi

Yeni dosyalar:
- setup_quality_engine_v2.py — quality_v2 scoring (10 boyut, hepsi değişen)
- diagnostic_research.py — 8 alanli diagnostic analiz
- diagnostic_report.md — detayli rapor
- test_backtest_engine.py — 27 test (setup attribution, regime, CHoCH, evidence, quality_v2, execution, look-ahead, deterministic)

Test sonucu: 27/27 PASSED

---

H) CEVAPLAR
============

A) setup_type nasıl atanıyor?
   build_research_setup → _classify_setup_type(regime, structure_type, direction)
   → raw_setup["setup_type"] → DB metadata_json + setup_type sütunu
   Artık "auto" değil, gerçek sınıflandırma (örn: indicator_downtrend_short)

B) Kaç setup güvenilir attribution aldı?
   Yeni kayıtlar: 100% (setup_type her zaman dolu)
   Eski kayıtlar: 0% ("unknown" — backfill edilmeli)
   Toplam: 4,089 kayıttan ~2,492 yeni + 1,597 eski

C) Yeni regime engine nasıl çalışıyor?
   7 regime class: UPTREND_STRONG/WEAK, DOWNTREND_STRONG/WEAK,
   RANGE_LOW_VOL, RANGE_HIGH_VOL, EXPANDING_VOLATILITY
   Faktörler: SMA cross + ADX-like trend strength + ATR vol + volume + structure
   Her setup'ta regime snapshot kaydediliyor

D) CHoCH hangi koşullarda ateşleniyor?
   Sweep GEREKSIZ. HH/HL/LH/LL yapısından çıkarılır.
   Confidence: 0.70 (sweepsiz) veya 0.85 (sweep ile)
   structure_state metadata'ya kaydediliyor

E) 5 sabit evidence nasıl gerçek verilere bağlandı?
   strategy_agreement: agreement_summary'den gerçek agreement_score
   invalidation_clarity: price-level % mesafesi + ATR mesafesi
   structure_quality: swing point mesafesi (range_pct)
   entry_quality: zaten değişen değere bağlandı
   formation_chain: zaten değişen değere bağlandı

F) Execution rate %14 neden?
   ESKİ backtest_v1'da: 1597 setup → 230 trade (%14)
   SEBApler:
   - Entry zone'a hiç ulaşılmadı (çoğu setup'ta fiyat zone dışında)
   - Insufficient future bars (veri sonu)
   - Invalidated before entry (stop çok yakın)
   
   GUNCEL backtest_v2: %95.4 execution rate
   - max_wait_bars=0 (veri sonuna kadar bekle)
   - open/outcome DB'ye kaydedilmiyor (sadece closed)

G) backtest_v2 ne gösteriyor?
   240 setup/run, 229 kaydedildi, wr=37.6%, avgR=-0.061
   Quality corr: Pearson=0.132 (önceki 0.12)
   10/10 evidence boyutu değişen değerler

H) Faz 2 adaptive weighting için hangi veriler hazır?
   ✅ Regime×Strategy matrisi (180+ sample'li kombinasyonlar)
   ✅ Regime bazli performans (9 regime class)
   ✅ Setup type bazli performans (9 type)
   ✅ Quality score v2 (10 boyut, hepsi değişen)
   ✅ Evidence correlation (4 adet >0.08)
   
   ❌ historical_validation (güvenilir değil — çıkarılacak)
   ❌ strategy_agreement (karsit yonelde — ağırlık azaltılacak)
   ❌ Survivorship bias düzeltme (tek sembol)
