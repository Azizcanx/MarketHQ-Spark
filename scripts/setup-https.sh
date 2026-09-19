#!/usr/bin/env bash
# HTTPS for IP-only access: Let'sEncrypt IP cert (shortlived profile) + nginx TLS + 80->443 redirect.
# Run: sudo bash scripts/setup-https.sh
set -euo pipefail

IP=$(ip route get 1.1.1.1 | grep -oP 'src \K[0-9.]+' | head -1)
[ -n "$IP" ] || { echo "public ip bulunamadi"; exit 1; }
echo "Hedef: https://$IP"

# apt kilidi (unattended-upgrades) doluysa bekle; paketler zaten varsa hic dokunma
need_pkgs=0
for p in python3-venv nginx cron; do dpkg -s "$p" >/dev/null 2>&1 || need_pkgs=1; done
if [ "$need_pkgs" = "1" ]; then
  for i in $(seq 1 60); do
    fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break
    echo "paket kilidi bekleniyor ($i/60)..."; sleep 10
  done
  apt-get update -qq || echo "UYARI: apt update hata verdi, kurulu paketlerle devam"
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv nginx cron >/dev/null || \
    echo "UYARI: apt install atlandi (muhtemelen zaten kurulu)"
fi

if [ ! -x /opt/certbot/bin/certbot ]; then
  echo "certbot venv kuruluyor (bir iki dk)..."
  python3 -m venv /opt/certbot
  /opt/certbot/bin/pip install --quiet --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --timeout 30 || true
  # Bu VPS'ten pypi.org/github erisimi kopuk; Aliyun aynasi hizli calisiyor
  /opt/certbot/bin/pip install --quiet -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --timeout 30 certbot \
    || /opt/certbot/bin/pip install --quiet certbot
fi
/opt/certbot/bin/certbot --version

mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
SITE=/etc/nginx/sites-available/markethq
[ -f "$SITE" ] && cp -n "$SITE" "$SITE.orig.bak"

write_phase1() {
cat > "$SITE" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 10m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
EOF
}

write_final() {
cat > "$SITE" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 10m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
    }
    location / {
        return 308 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;
    client_max_body_size 10m;
    ssl_certificate /etc/letsencrypt/live/$IP/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$IP/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
EOF
}

# faz 1: :80 acme hazir, nginx calisiyor
write_phase1; nginx -t && systemctl reload nginx

# sertifika al/yele (varsa yenileme — 6 gunluk cert cron'i halleder, quota yakma)
if /opt/certbot/bin/certbot certificates 2>/dev/null | grep -q "Name: $IP"; then
  echo "Sertifika zaten mevcut, yenilenmiyor (cron 6 saatte bir kontrol eder)."
else
  /opt/certbot/bin/certbot certonly --webroot -w /var/www/letsencrypt \
    --ip-address "$IP" --cert-name "$IP" \
    --preferred-profile shortlived \
    --agree-tos --register-unsafely-without-email --non-interactive
fi

# faz 2: TLS + yonlendirme
write_final; nginx -t && systemctl reload nginx

# otomatik yenileme: 6 gunluk cert, 6 saatte bir kontrol
( crontab -l 2>/dev/null | grep -v "certbot renew" ; \
  echo '5 */6 * * * /opt/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"' ) | crontab -

# DuckDNS kayitlari varsa domain cron'unu da kur (API erisilemezse sessiz gecilir)
if [ -f /home/markethq/.config/duckdns.env ]; then
  cp /home/markethq/.config/duckdns.env /etc/markethq-duckdns.env 2>/dev/null || true
  ( crontab -l 2>/dev/null | grep -v "duckdns" ; \
    echo '0 * * * * . /etc/markethq-duckdns.env; curl -s -m 20 "https://api.duckdns.org/update?domains=$SUB&token=$TOKEN&ip" >/dev/null' ) | crontab -
fi

echo
echo "==================================================="
echo "Tamam → https://$IP"
echo "Sertifika 6 gun gecerli; cron 6 saatte bir yeniler."
echo "==================================================="
