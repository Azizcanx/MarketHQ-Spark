# MarketHQ Otonom Sistem İzin Kapsamı (Muratify dersleriyle)

Üç katman: allowlist → onay kapısı → blast-radius sınırı.

## 1. Araç allowlist (otonom agent'lar için)

SADECE sunlar:
- `.venv/bin/python` ile salt-okunur analiz + mevcut `_v1` modüllerini çağırma
- `agentspace/agentspace/logs/` altına JSON/JSONL append (feedback, evolution, ops_runs)
- Yeni `_v1` modülü oluşturma (mevcut dosyayı silmeden, import uyumlu)
- `curl` ile localhost:3000 / :8010 / api.binance.com okuma
- `npx tsc`, `npm run build`, `py_compile` doğrulama

YASAK: rm, systemctl, sudo, DB yazma (market_hq.db salt-okunur), secret/env okuma,
canlı emir/broker, `git push`, otomatik merge, servis restart (worker kill dahil —
sadece insan yapar).

## 2. Onay kapıları

- Dosya yazma (yeni dosya, log append): otomatik gecer.
- Mevcut dosya patch'i (eklemeli, kucuk): otomatik gecer, diff dogrulanir.
- Davranis degisikligi (agirlik, esik, varsayılan kaynak): gecerli ama WHY/evolution
  notu zorunlu — degisiklik gerekcesiz kalmaz.
- Silme / restart / dis API'ye yazma / para: INSAN ONAYI sart, agent yapmaz.

## 3. Blast-radius

- Bir turda TEK iyilestirme; frontend + python ayni turda degismez (build riski).
- Backfill dedupe korunur; skor dosyasi tek yazar prensibi (sirali cron'lar).
- Her run kanit birakir: ops_runs.jsonl satiri (ne, sonuc, skor etkisi).
- Supheli durumda: degisiklik yapma, gozlemi evolution sorusu olarak yaz.
