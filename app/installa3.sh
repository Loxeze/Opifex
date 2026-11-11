#!/bin/bash
# Installa Opifex 3.0 ACCANTO alla 2, sullo stesso server, senza toccarla. Il codice si prende dalla 2 aggiornata (stessa versione).
# Uso:  sudo bash /opt/agenti/app/installa3.sh   (oppure scaricato da GitHub: sudo bash i3.sh)            (indirizzo predefinito: aurora.opifex.space)
#       sudo bash /opt/agenti/app/installa3.sh altro.nome.it
# Si puo' rilanciare: rifa' solo cio' che manca.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Esegui con sudo."; exit 1; }
DOM="${1:-aurora.opifex.space}"
[[ "$DOM" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]] || { echo "Nome non valido"; exit 1; }
DUE=/opt/agenti
DIR=/opt/opifex3
PORTA=8001
DB=opifex3
[ -f "$DUE/.env" ] || { echo "Non trovo la 2 in $DUE: questa installazione va messa accanto alla 2."; exit 1; }

export DEBIAN_FRONTEND=noninteractive
export PGOPTIONS="--client-min-messages=warning"

echo "== 1/7 Cartella della 3.0 ($DIR)"
mkdir -p "$DIR"
if [ -f "$DUE/app/edizione.py" ]; then   # la 2 e' gia' aggiornata: stesso codice
  SRC="$DUE"
else                                      # altrimenti il codice si prende da GitHub (ramo principale)
  SRC=$(mktemp -d)
  curl -fsSL https://codeload.github.com/Loxeze/Opifex/tar.gz/refs/heads/main | tar xz -C "$SRC" --strip-components=1
  [ -f "$SRC/app/edizione.py" ] || { echo "Il codice scaricato non contiene la 3.0"; exit 1; }
fi
for f in app sql; do rm -rf "${DIR:?}/$f"; cp -a "$SRC/$f" "$DIR/$f"; done
for f in requirements.txt VERSIONE crea_titolare.py crea_briefing.py; do [ -e "$SRC/$f" ] && cp -f "$SRC/$f" "$DIR/$f"; done
chown -R agenti:agenti "$DIR"
echo "   versione $(cat "$DIR/VERSIONE")"

echo "== 2/7 Database proprio ($DB) e impostazioni"
URL2=$(grep '^DATABASE_URL=' "$DUE/.env" | cut -d= -f2-)
URL3="${URL2%/*}/$DB"
RUOLO=$(printf '%s' "$URL2" | sed -E 's|^postgresql://([^:@/]+).*|\1|')
if [ "$(runuser -u postgres -- psql -At -c "SELECT count(*) FROM pg_database WHERE datname='$DB'")" = "0" ]; then
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE $DB OWNER $RUOLO ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8'"
  echo "   database creato"
fi
if [ ! -f "$DIR/.env" ]; then
  CODICE=$(openssl rand -hex 6)
  {
    echo "DATABASE_URL=$URL3"
    echo "SECRET_KEY=$(openssl rand -hex 48)"          # diversa dalla 2: un accesso alla 2 non vale per la 3
    grep -E '^(CHIAVE_CASSAFORTE|CHIAVE_ANTHROPIC|CHIAVE_OPENAI|CHIAVE_XAI)=' "$DUE/.env" || true   # stessa cassaforte: le chiavi copiate restano leggibili
    echo "ORIGINI_CONSENTITE=https://$DOM"
    echo "OPIFEX_EDIZIONE=3"
    echo "OPIFEX_IMPORTA_DA=$URL2"
    echo "OPIFEX_CODICE_AVVIO=$CODICE"
    echo "OPIFEX_INDIRIZZO=https://$DOM"
  } > "$DIR/.env"
  chown agenti:agenti "$DIR/.env"; chmod 600 "$DIR/.env"
fi
CODICE=$(grep '^OPIFEX_CODICE_AVVIO=' "$DIR/.env" | cut -d= -f2-)

echo "== 3/7 Schemi del database"
q() { psql "$URL3" -q -At -v ON_ERROR_STOP=1 "$@"; }
q -c "CREATE TABLE IF NOT EXISTS schema_migrazioni (nome TEXT PRIMARY KEY, applicata_il TIMESTAMPTZ DEFAULT NOW())"
for f in "$DIR"/sql/[0-9]*.sql; do
  n=$(basename "$f")
  if [ "$(q -c "SELECT count(*) FROM schema_migrazioni WHERE nome='$n'")" = "0" ]; then
    psql "$URL3" -q -1 -v ON_ERROR_STOP=1 < "$f" >/dev/null
    q -c "INSERT INTO schema_migrazioni (nome) VALUES ('$n')"
  fi
done
echo "   $(q -c 'SELECT count(*) FROM schema_migrazioni') schemi applicati"

echo "== 4/7 Ambiente Python (qualche minuto la prima volta)"
[ -d "$DIR/venv" ] || runuser -u agenti -- python3 -m venv "$DIR/venv"
runuser -u agenti -- "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
mkdir -p "$DIR/backup" "$DIR/finestre" "$DIR/aggiornamenti"; chown agenti:agenti "$DIR/backup" "$DIR/finestre" "$DIR/aggiornamenti"

echo "== 5/7 Servizio opifex3 (porta $PORTA)"
cat > /etc/systemd/system/opifex3.service <<UNIT
[Unit]
Description=Opifex 3.0 (accanto alla 2)
After=postgresql.service network.target
[Service]
User=agenti
WorkingDirectory=$DIR
Environment=PLAYWRIGHT_BROWSERS_PATH=$DUE/browsers
Environment=OPIFEX_DIR=$DIR
Environment=BACKUP_DIR=$DIR/backup
Environment=ENV_FILE=$DIR/.env
Environment=FINESTRE_DIR=$DIR/finestre
ExecStart=$DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORTA --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
# aggiornamenti dall'app: una copia dello script della 2, che lavora solo sulla 3
sed -e "s|/opt/agenti|$DIR|g" -e "s|127.0.0.1:8000|127.0.0.1:$PORTA|" -e "s|pg_dump agenti|pg_dump $DB|" -e "s|restart agenti|restart opifex3|g" \
    -e "s|/var/backups/agenti|/var/backups/opifex3|" -e "s|/var/lock/opifex-aggiorna.lock|/var/lock/opifex3-aggiorna.lock|" \
    "$DIR/app/opifex-aggiorna.modello" > /usr/local/sbin/opifex3-aggiorna
chmod 755 /usr/local/sbin/opifex3-aggiorna
cat > /etc/systemd/system/opifex3-aggiorna.service <<UNIT
[Unit]
Description=Opifex 3.0: installa l'aggiornamento
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/opifex3-aggiorna
TimeoutStartSec=1500
UNIT
cat > /etc/systemd/system/opifex3-aggiorna.path <<UNIT
[Unit]
Description=Opifex 3.0: richiesta di aggiornamento
[Path]
PathExists=$DIR/aggiornamenti/richiesta
Unit=opifex3-aggiorna.service
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now opifex3-aggiorna.path >/dev/null 2>&1
systemctl enable opifex3 >/dev/null 2>&1
systemctl restart opifex3
for i in $(seq 1 30); do curl -s "http://127.0.0.1:$PORTA/salute" >/dev/null && break; sleep 2; done
curl -s "http://127.0.0.1:$PORTA/salute" >/dev/null && echo "   Opifex 3.0 risponde" || { echo "La 3.0 non risponde:"; journalctl -u opifex3 -n 25 --no-pager; exit 1; }

echo "== 6/7 Indirizzo https://$DOM"
IP_SERVER=$(curl -4 -s --max-time 10 https://api.ipify.org || true)
IP_DNS=$(getent ahostsv4 "$DOM" | awk '{print $1; exit}' || true)
if [ -z "$IP_DNS" ] || { [ -n "$IP_SERVER" ] && [ "$IP_DNS" != "$IP_SERVER" ]; }; then
  echo ""
  echo "   MANCA UN PASSO: il nome $DOM non punta ancora a questo server."
  echo "   Nel pannello DNS di Aruba crea un record A:  nome «${DOM%%.*}»  ->  ${IP_SERVER:-indirizzo del server}"
  echo "   Dopo qualche minuto rilancia lo stesso comando: completera' da qui."
  exit 0
fi
if ! command -v caddy >/dev/null || [ ! -f /etc/caddy/Caddyfile ]; then
  echo "   Non trovo Caddy: la 3.0 e' attiva sul server (porta $PORTA) ma serve il suo indirizzo https. Scrivimi e ti guido."; exit 1
fi
if ! grep -q "^$DOM {" /etc/caddy/Caddyfile 2>/dev/null; then
  cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.prima-di-opifex3"
  cat >> /etc/caddy/Caddyfile <<CADDY

$DOM {
	encode gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
		-Server
	}
	reverse_proxy 127.0.0.1:$PORTA
}
CADDY
  if ! caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    cp "/etc/caddy/Caddyfile.prima-di-opifex3" /etc/caddy/Caddyfile
    echo "   Configurazione di Caddy non valida: ho rimesso quella di prima (la 2 non e' toccata)."; exit 1
  fi
  systemctl reload caddy
fi

echo "== 7/7 Controllo"
sleep 5
curl -s --max-time 20 "https://$DOM/salute" >/dev/null && echo "   https://$DOM risponde" || echo "   Il certificato si sta preparando: tra un minuto prova ad aprire https://$DOM"
cat <<FINE

FATTO. La 2 continua a funzionare su app.opifex.space, senza modifiche.
Apri:  https://$DOM
Crea il tuo accesso con il codice d'avvio:   $CODICE
FINE
exit 0
