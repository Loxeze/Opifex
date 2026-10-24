#!/bin/bash
# Installa la piattaforma agenti su Ubuntu 24.04. Eseguire con: sudo bash installa-piattaforma.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Esegui con sudo."; exit 1; }
DIR=/opt/agenti
export DEBIAN_FRONTEND=noninteractive
echo "== 1/6 Pacchetti di sistema"
apt-get update -qq
apt-get install -y -qq postgresql python3-venv python3-pip >/dev/null

echo "== 2/6 Utente e cartella"
id agenti >/dev/null 2>&1 || useradd --system --home "$DIR" --shell /usr/sbin/nologin agenti
mkdir -p "$DIR"
sed '1,/^__PAYLOAD__$/d' "$0" | base64 -d | tar xz -C "$DIR"
chown -R agenti:agenti "$DIR"

echo "== 3/6 Database"
if [ ! -f "$DIR/.env" ]; then
  DBPASS=$(openssl rand -hex 24)
  SECRET=$(openssl rand -hex 48)
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE agenti LOGIN PASSWORD '$DBPASS';
CREATE DATABASE agenti OWNER agenti ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';
SQL
  cat > "$DIR/.env" <<ENV
DATABASE_URL=postgresql://agenti:$DBPASS@127.0.0.1:5432/agenti
SECRET_KEY=$SECRET
CHIAVE_ANTHROPIC=
CHIAVE_OPENAI=
CHIAVE_XAI=
ENV
  chown agenti:agenti "$DIR/.env"; chmod 600 "$DIR/.env"
else
  echo "   Installazione esistente: copia di sicurezza del database prima dell'aggiornamento"
  mkdir -p /var/backups/agenti
  runuser -u postgres -- pg_dump agenti | gzip > "/var/backups/agenti/agenti-$(date +%F-%H%M).sql.gz"
  chmod 700 /var/backups/agenti
fi

if ! grep -q '^CHIAVE_CASSAFORTE=.' "$DIR/.env"; then
  sed -i '/^CHIAVE_CASSAFORTE=/d' "$DIR/.env"
  echo "CHIAVE_CASSAFORTE=$(openssl rand -base64 32 | tr '+/' '-_')" >> "$DIR/.env"
  chown agenti:agenti "$DIR/.env"; chmod 600 "$DIR/.env"
  echo "   creata la chiave della cassaforte delle credenziali (nel file .env: non cancellarla, o le credenziali salvate non si potranno piu' leggere)"
fi

echo "== 4/6 Schemi e dati (solo quelli non ancora applicati)"
URL=$(grep '^DATABASE_URL=' "$DIR/.env" | cut -d= -f2-)
q() { psql "$URL" -q -At -v ON_ERROR_STOP=1 "$@"; }
q -c "CREATE TABLE IF NOT EXISTS schema_migrazioni (nome TEXT PRIMARY KEY, applicata_il TIMESTAMPTZ DEFAULT NOW())"
if [ "$(q -c 'SELECT count(*) FROM schema_migrazioni')" = "0" ] && [ "$(q -c "SELECT to_regclass('public.agenti') IS NOT NULL")" = "t" ]; then
  for n in 01_schema 02_schema_utenti 03_schema_supervisione 04_schema_sviluppo 05_dati_iniziali; do
    q -c "INSERT INTO schema_migrazioni (nome) VALUES ('$n.sql') ON CONFLICT DO NOTHING"
  done
fi
for f in "$DIR"/sql/[0-9]*.sql; do
  n=$(basename "$f")
  if [ "$(q -c "SELECT count(*) FROM schema_migrazioni WHERE nome='$n'")" = "0" ]; then
    echo "   applico $n"
    psql "$URL" -q -1 -v ON_ERROR_STOP=1 < "$f"
    q -c "INSERT INTO schema_migrazioni (nome) VALUES ('$n')"
  fi
done

echo "== 5/6 Ambiente Python"
[ -d "$DIR/venv" ] || runuser -u agenti -- python3 -m venv "$DIR/venv"
runuser -u agenti -- "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
if ! ls -d "$DIR"/browsers/chromium-* >/dev/null 2>&1; then
  echo "   installo il browser per la navigazione dei siti (circa 3 minuti)"
  mkdir -p "$DIR/browsers"
  PLAYWRIGHT_BROWSERS_PATH="$DIR/browsers" "$DIR/venv/bin/playwright" install --with-deps chromium >/dev/null
  chown -R agenti:agenti "$DIR/browsers"
fi

echo "== 6/6 Servizio"
cat > /etc/systemd/system/agenti.service <<UNIT
[Unit]
Description=Piattaforma agenti (API)
After=postgresql.service network.target
[Service]
User=agenti
WorkingDirectory=$DIR
Environment=PLAYWRIGHT_BROWSERS_PATH=$DIR/browsers
ExecStart=$DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
# Aggiornamenti da GitHub: lo script che installa gira come root e sta fuori dalla cartella dell'app
install -m 755 -o root -g root "$DIR/installer/opifex-aggiorna" /usr/local/sbin/opifex-aggiorna
install -m 644 -o root -g root "$DIR/installer/opifex-aggiorna.service" /etc/systemd/system/opifex-aggiorna.service
install -m 644 -o root -g root "$DIR/installer/opifex-aggiorna.path" /etc/systemd/system/opifex-aggiorna.path
mkdir -p "$DIR/aggiornamenti"; chown agenti:agenti "$DIR/aggiornamenti"; chmod 755 "$DIR/aggiornamenti"
systemctl daemon-reload
systemctl enable --now opifex-aggiorna.path >/dev/null 2>&1
systemctl enable --now agenti >/dev/null 2>&1
systemctl restart agenti
sleep 3
curl -s http://127.0.0.1:8000/salute && echo " <- API attiva" || { echo "API non risponde:"; journalctl -u agenti -n 20 --no-pager; exit 1; }
cat <<FINE

FATTO. Prossimi passi:
 1) Solo alla prima installazione, crea il tuo utente:
      sudo -u agenti bash -c 'cd $DIR && ./venv/bin/python crea_titolare.py'
 2) Chiavi dei fornitori (quando le hai):  sudo nano $DIR/.env  poi  sudo systemctl restart agenti
 3) Dal tuo computer apri il tunnel:  ssh -L 8000:localhost:8000 lorenzo@81.2.251.34
    poi nel browser: http://localhost:8000/   (interfaccia di gestione)
FINE
exit 0
__PAYLOAD__
