#!/bin/bash
set -e

cd /var/www/tezkor

python3 - <<'PY'
from pathlib import Path
p = Path('.env')
text = p.read_text() if p.exists() else ''
keep = []
for line in text.splitlines():
    if not line.strip():
        continue
    if line.startswith('ALLOWED_HOSTS=') or line.startswith('CSRF_TRUSTED_ORIGINS='):
        continue
    keep.append(line)
keep.append('ALLOWED_HOSTS=tezkor-savdo.uz,www.tezkor-savdo.uz,189.74.100.71,localhost,127.0.0.1')
keep.append(
    'CSRF_TRUSTED_ORIGINS='
    'https://tezkor-savdo.uz,https://www.tezkor-savdo.uz,'
    'http://tezkor-savdo.uz,http://www.tezkor-savdo.uz,'
    'http://189.74.100.71,https://189.74.100.71'
)
p.write_text('\n'.join(keep) + '\n')
print(p.read_text())
PY

cat > /etc/nginx/sites-available/tezkor << 'NXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name tezkor-savdo.uz www.tezkor-savdo.uz 189.74.100.71 _;

    client_max_body_size 20M;

    location /static/ {
        alias /var/www/tezkor/staticfiles/;
        expires 7d;
        access_log off;
    }

    location /media/ {
        alias /var/www/tezkor/media/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NXEOF

ln -sfn /etc/nginx/sites-available/tezkor /etc/nginx/sites-enabled/tezkor
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
systemctl restart tezkor

echo "=== DNS ==="
getent hosts tezkor-savdo.uz || true
getent hosts www.tezkor-savdo.uz || true
(command -v dig >/dev/null && dig +short tezkor-savdo.uz A) || true
(command -v dig >/dev/null && dig +short www.tezkor-savdo.uz A) || true

IP=$(getent ahostsv4 tezkor-savdo.uz | awk '{print $1; exit}')
echo "Domain A: ${IP:-none}"

if [ "$IP" = "189.74.100.71" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
  certbot --nginx -d tezkor-savdo.uz -d www.tezkor-savdo.uz \
    --non-interactive --agree-tos -m admin@tezkor-savdo.uz --redirect || true
else
  echo "DNS_NOT_READY: A record is '${IP:-none}' (need 189.74.100.71)"
fi

curl -sS -o /dev/null -w "HOST_DOMAIN %{http_code}\n" -H "Host: tezkor-savdo.uz" http://127.0.0.1/ || true
systemctl is-active tezkor
systemctl is-active nginx
echo DOMAIN_SETUP_OK
