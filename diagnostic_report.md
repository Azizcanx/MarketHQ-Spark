# Diagnostic Research — Setup Engine V1
===========================================

Tarih: 2026-09-16
Veri: 1,597 backtest_v1 kaydı (THYAO.IS 1h)

---

A) EN ÖNEMLİ 5 BULGU
=====================

1. **5/10 evidence boyutu SABİT** — hiç değişmiyor
   entry_quality = 0.80 her zaman
   invalidation_clarity = 1.00 her zaman
   risk_rr = 0.55 her zaman
   strategy_agreement = 0.30 her zaman
   formation_chain = 0.833 her zaman
   Sonuç: bu boyutlar quality score'a SİFİR bilgi katıyor. Ağırlık ne olursa olsun
   sonuç değişmez.

2. **Regime dominant faktör, quality score değil**
   DOWNTREND:  wr=51%  avgR=+0.273
   UPTREND:     wr=44%  avgR=+0.089
   RANGE:       wr=37%  avgR=-0.085
   Quality pearson = 0.000 HEPSİNDE (sabit quality ↔ outcome)

3. **setup_type hiç doldurulmuyor — hepsi "unknown"**
   1,597 kayıp × 16 strateji = strateji bazlı analiz imkansız
   Backtest engine setup生成'da setup_type atamıyor

4. **Problem ENTRY'de değil — EXIT/REGIME'de**
   Winners entry_q = 0.578, losers entry_q = 0.589
   Losers entry quality'u daha YÜKSEK!
   Demek: iyi giriş yapıyoruz ama yanlış regimede/stop'da çıkıyoruz

5. **Sadece 13 unique signature — çok düşük çeşitlilik**
   Max 479 aynı signature, ortalama 122.8 setup/signature
   Aynı pattern tekrar tekrar test ediliyor = overfitting riski

---

B) SETUP ENGINE'İN AN ZAYIFLIĞI
================================

REGIME FİLTRESİ YOK — engine tüm regimlerde setup üretiyor.
RANGE regiminde -0.085 avgR, DOWNTREND'de +0.273.
Fark: 0.358 R per trade. Regime seçimi quality scoring'den
10x daha çok açıklama yapar.

Ek: setup_type eksik → strategy weighting yapılamaz.
Ek: CHoCH never fires (önceki bulgu) → structure_quality her zaman
 LOW'da kalıyor.

---

C) QUALITY SCORING'İN AN ZAYIFLIĞI
====================================

5 boyut SABİT → 50% ağırlık gürültüye gidiyor.
Gerçekten işe yarayan 3 boyut:
  historical_validation (+0.13 pearson)
  structure_quality    (+0.11 pearson)
  regime_compatibility (+0.11 pearson)

Ama structure_quality range (0.20-0.40) çok dar.
Regime compatibility range (0.40-0.85) iyi ama
setup_type eksik nedeniyle doğru hesaplanmıyor.

Kalite score ≈ 0.47-0.51 aralığında — çok dar, ayrımtırmıyor.

---

D) STRATEGY WEIGHTING İÇİN KULLANILABİLCEK VERİ
=================================================

Mevcut veriyle YAPILACAKLAR:
1. setup_type doldurulması (en kritik)
2. Regime breakdown kullanılarak ağırlık:
   DOWNTREND setup'ları ağırlıkla, RANGE'a karşı ağırlık azalt
3. Historical_validation score'u weight olarak kullan
   (tek gerçekten öngörücü boyut)
4. Strategy_agreement × regime_compatibility çarpımı
   (iki boyut birlikte güçlü)

YAPILAMAYANLAR (eksik veri):
- Strategy family bazlı ayrım (setup_type yok)
- Timeframe bazlı performans (tek TF test edildi)
- Symbol bazlı genelleme (tek sembol)

---

E) FAZ 2'DE YAPILACAK DEĞİŞİKLİKLER
=====================================

ÖNCELİĞE GÖRE:

Kritik (setup engine):
  1. setup_type'u üretimde doldur — strategy family atama
  2. Regime filter ekle — RANGE'da setup sayısını azalt veya
     RANGE setup'larını düşük ağırlıkla işaretle
  3. CHoCH/liquidity detection düzelt — structure_quality'yı
     gerçekten hesapla (şu an NEUTRAL her zaman döndürüyor)

Yüksek (quality scoring):
  4. Sabit boyutları kaldır veya yeniden hesapla:
     entry_quality, invalidation_clarity, strategy_agreement,
     formation_chain, risk_rr
  5. Kalite score aralığını genişlet (0.3-0.8 → 0.0-1.0)
  6. Regime compatibility'yi overweight et (en güçlü sinyal)

Orta (backtest):
  7. Signature çeşitliliğini artır — farklı pattern'ler üret
  8. Weighted average R hesapla (quality score'a göre)

Düşük (nice-to-have):
  9. Monte Carlo robustness testi
  10. Walk-forward validation

---

F) DEĞİŞİKLİK YAPMANDAN ÖNCE ÇÖZÜLMESİ GEREKEN PROBLEMLER
===========================================================

1. setup_type atama eksik — backend'de fix gerekli
   (setup_object_model.py'de setup_type field'ı var ama
    backtest engine assign edmiyor)

2. Historical_validation sadece yfinance data'ya bakıyor
   — 3 outcome kaydı var, tamamı "open". Gerçek geçmiş
   validation yok.

3. RANGE regiminde -0.085 avgR — bu strateji RANGE'da
   çalışmıyor. Ya RANGE'da setup üretimini azalt ya da
   RANGE'a özel strateji ekle.

4. 13 signature — çok az çeşitlilik. Setup generation
   pattern diversity'si düşük.

5. 50.4% kayıplar "weak historical_validation" — bu boyut
   aslında işe yaramıyor gibi görünüyor. Ya düzelt ya
   kaldır.

6. Survivorship bias: THYAO.IS listedir hâlâ ama sadece
   tek sembol. Diversifikasyon yok.

7. Sample: 1597 setup / 230 trades — 1597 setup'tan sadece
   230'ı trade oldu (14% execution rate). Bu da düşük.

---

SONUÇ
======

Setup engine "yeterince iyi ayrışmıyor" çünkü:
- Regime filter yok (en büyük etken)
- 5/10 quality boyutu sabit (sabotaj)
- setup_type eksik (strategy weighting imkansız)
- CHoCH/liquidity detection never fires (structure zayıf)

Bu 4 sorunu çözersek quality scoring öngörücü olabilir.
Şu anki quality score ≈ random guess ile aynı.
