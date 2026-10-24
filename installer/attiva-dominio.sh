#!/bin/bash
# Mette Opifex su un indirizzo con HTTPS (certificato gratuito automatico). Eseguire con: sudo bash attiva-dominio.sh app.opifex.space
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Esegui con sudo."; exit 1; }
DOM="${1:?indica il nome completo, es. app.opifex.space}"
[[ "$DOM" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]] || { echo "Nome non valido"; exit 1; }
DIR=/opt/agenti
IP_SERVER=$(curl -4 -s --max-time 10 https://api.ipify.org || true)
IP_DNS=$(getent ahostsv4 "$DOM" | awk '{print $1; exit}' || true)
echo "Indirizzo del server: ${IP_SERVER:-?}   Il nome $DOM punta a: ${IP_DNS:-nessuno}"
if [ -z "$IP_DNS" ] || { [ -n "$IP_SERVER" ] && [ "$IP_DNS" != "$IP_SERVER" ]; }; then
  echo "ATTENZIONE: $DOM non punta ancora a questo server."
  echo "Nel pannello DNS crea un record A per questo nome verso ${IP_SERVER:-l IP del server}, aspetta qualche minuto e rilancia."
  exit 1
fi
echo "== 1/4 Installo Caddy (HTTPS automatico)"
if ! command -v caddy >/dev/null; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gpg >/dev/null
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg --yes
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
echo "== 2/4 Configuro $DOM"
cat > /etc/caddy/Caddyfile <<CADDY
$DOM {
	encode gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
		-Server
	}
	reverse_proxy 127.0.0.1:8000
}
CADDY
echo "== 3/4 Opifex riconosce l'indirizzo reale dei visitatori"
if ! grep -q -- '--proxy-headers' /etc/systemd/system/agenti.service; then
  sed -i 's|^ExecStart=\(.*\)--port 8000|ExecStart=\1--port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1|' /etc/systemd/system/agenti.service
  systemctl daemon-reload
fi
URL=$(grep '^DATABASE_URL=' "$DIR/.env" | cut -d= -f2-)
psql "$URL" -q -c "INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('google_redirect', 'https://$DOM/gestione/google/callback') ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore" || true
systemctl restart agenti
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; echo "   porte 80 e 443 aperte nel firewall"; fi
echo "== 4/4 Avvio"
systemctl enable --now caddy >/dev/null 2>&1; systemctl restart caddy
sleep 8
if curl -fsS --max-time 20 "https://$DOM/salute" >/dev/null; then echo; echo "FATTO: apri https://$DOM"; else
  echo "Il certificato non e' ancora pronto o le porte 80/443 sono chiuse."; echo "Controlla il firewall del pannello Aruba (porte 80 e 443 in ingresso) e guarda: journalctl -u caddy -n 20 --no-pager"; fi
