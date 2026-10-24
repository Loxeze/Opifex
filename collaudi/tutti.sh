#!/bin/bash
# uso: tutti.sh [nome_test ...]  (senza argomenti: tutti)
SP=/tmp/claude-0/-home-claude/f97e63d7-0f90-572a-b598-f314f34539ca/scratchpad
bash $SP/avvia_pg.sh
cd $SP/pacchetto
P="runuser -u postgres -- /usr/lib/postgresql/16/bin/psql -q -h 127.0.0.1 -p 54329 -v ON_ERROR_STOP=1"
reset(){ $P -d postgres -c "DROP DATABASE IF EXISTS agenti_test" -c "CREATE DATABASE agenti_test ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8'" >/dev/null; for f in sql/[0-9]*.sql; do $P -d agenti_test < $f >/dev/null || echo ERRORE $f; done; }
T="${@:-test_collaudo test_gestione test_documenti test_accessi test_dialoghi test_richieste test_aziende test_aggiornamenti test_canali test_utenti test_progetti test_novita test_task test_ip test_memoria test_gmail test_percorsi test_social test_release18}"
for t in $T; do reset; echo "== $t"; SP=$SP $SP/venv/bin/python $SP/$t.py 2>&1 | grep -E "^(OK|FALLITO)|TOTALE|Traceback|Error|File \"|assert" | grep -v "^OK" ; done
