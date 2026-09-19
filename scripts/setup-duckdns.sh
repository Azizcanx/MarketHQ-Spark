#!/usr/bin/env bash
# DuckDNS kaydi + saatlik IP tazeleme (markethq kullanıcısı olarak çalıştır).
# Gereksinim: duckdns.org'da Google/GitHub ile giriş yapıp subdomain oluşturmuş olmak.
set -euo pipefail

echo "DuckDNS kurulumu"
read -rp "Subdomain adi (ornek 'markethq', .duckdns.org eklenir): " SUB
read -rs -p "DuckDNS token (paneldeki uzun anahtar): " TOKEN; echo
[ -n "$SUB" ] && [ -n "$TOKEN" ] || { echo "subdomain/token boş olamaz"; exit 1; }

mkdir -p ~/.config
umask 077
printf 'DOMAIN=%s.duckdns.org\nSUB=%s\nTOKEN=%s\n' "$SUB" "$SUB" "$TOKEN" > ~/.config/duckdns.env
IP=$(curl -fsS https://api.ipify.org)
RES=$(curl -fsS "https://api.duckdns.org/update?domains=${SUB}&token=${TOKEN}&ip=${IP}")
echo "DuckDNS güncellendi (beklenen OK): ${RES}"

# saatlik tazeleme cron'u
( crontab -l 2>/dev/null | grep -v duckdns-update; \
  printf '%s\n' "0 * * * * . ~/.config/duckdns.env; curl -s -m 20 \"https://api.duckdns.org/update?domains=\$SUB&token=\$TOKEN&ip=\" >/dev/null" ) | crontab -

echo "OK → $SUB.duckdns.org → $IP (cron kuruldu). Şimdi: sudo bash scripts/setup-https.sh"
