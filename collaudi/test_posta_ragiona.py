import os, sys, json
from datetime import datetime, timezone, timedelta
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import fornitori, posta_vaglio as pv, cassaforte
from app.fornitori import Risposta, ErroreLocale
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Renovatio','l.zeppa@renovatiogroup.it',%s,'{gmail}') RETURNING id", (cassaforte.cifra("rt"),))[0][0]
k = psycopg.connect(DSN, row_factory=dict_row)

# --- 1. il modello che ragiona prima di rispondere
CHIAMATE = []
RISPOSTE = []
def finto(fornitore, modello, istr, msg, max_token=1500, **kw):
    CHIAMATE.append(max_token)
    return Risposta(RISPOSTE.pop(0), 10, 10)
fornitori.chiama_modello = finto
RISPOSTE[:] = ['<think>Vediamo: la mail [1] parla di una fattura {forse}. Rispondo.</think>\n[{"n": 1, "documento": true, "tipo": "fattura", "importo": 122}]']
ok("il ragionamento <think> viene tolto e il JSON si legge", pv._json(pv._chiedi(k, "x", "y", 1200)) == [{"n": 1, "documento": True, "tipo": "fattura", "importo": 122}] and CHIAMATE == [1200])
CHIAMATE.clear()
RISPOSTE[:] = ['<think>Ragiono a lungo [1] e la risposta viene tagliata', '<think>breve</think>[{"n": 1, "documento": false}]']
t = pv._chiedi(k, "x", "y", 1200)
ok("risposta tagliata dentro il ragionamento: si riprova una volta con piu' spazio", pv._json(t) == [{"n": 1, "documento": False}] and CHIAMATE == [1200, 3600], CHIAMATE)

# --- 2. fatture trovate anche con un modello che ragiona
ieri = datetime.now(timezone.utc) - timedelta(days=200)
v1 = sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, casella, data, mittente, oggetto, categoria, letta)
            VALUES ('gmail', %s, 'f1', 'l.zeppa@renovatiogroup.it', %s, 'Aruba <fatture@aruba.it>', 'Fattura n. 123 - rinnovo hosting', 'storica', TRUE) RETURNING id""", (gid, ieri))[0][0]
sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, casella, data, mittente, oggetto, categoria, letta)
       VALUES ('gmail', %s, 'n1', 'l.zeppa@renovatiogroup.it', %s, 'Newsletter <news@x.it>', 'Le novita di maggio', 'storica', TRUE)""", (gid, ieri))
pv._anteprima = lambda conn, r: "Gentile cliente, in allegato la fattura n. 123 di euro 122,00 con scadenza 30/06." if r["msg_id"] == "f1" else "Ecco le novita."
CHIAMATE.clear()
RISPOSTE[:] = ['<think>La prima email e\' una fattura di Aruba [importo 122]...</think>[{"n": 1, "documento": true, "tipo": "fattura", "direzione": "uscita", "controparte": "Aruba", "importo": 122, "numero": "123"}]']
n = pv.amministrazione(k, 12)
ok("la fattura viene riconosciuta e registrata", n == 2 and sql("SELECT tipo, controparte, importo FROM posta_amministrazione WHERE vaglio_id=%s", (v1,)) == [("fattura", "Aruba", 122)], (n, sql("SELECT * FROM posta_amministrazione")))
c = {"chiave": f"gmail-{gid}", "origine": "gmail", "id": gid, "email": "l.zeppa@renovatiogroup.it"}
sql("UPDATE impostazioni_sistema SET valore='2026-01-01' WHERE chiave='posta_storico_dal'")
ok("i numeri dal vivo della casella: 1 fattura, nessuna da esaminare", pv.storico_numeri(k, c) == {"documenti": 1, "da_esaminare": 0}, pv.storico_numeri(k, c))

# --- 3. recupero col computer spento: la posta vecchia si scarica lo stesso
sql("DELETE FROM posta_vaglio"); sql("DELETE FROM impostazioni_sistema WHERE chiave='posta_storico_stato'")
pv.caselle = lambda conn: [dict(c)]
def elenco(conn, origine, cid, n, giorni, ricerca="", tutto=False, avanzamento=None, finestra=None):
    da, a = finestra
    return [{"id": f"m{da}", "data": datetime(da.year, da.month, 5, 10, tzinfo=timezone.utc), "da": "Enel <bollette@enel.it>", "oggetto": "Bolletta in scadenza",
             "anteprima": "bolletta importo scadenza pagamento", "filo": "", "a": "", "allegati": "bolletta.pdf"}]
pv.recenti = elenco
def spento(*a, **kw):
    raise ErroreLocale("Nessun computer con il modello locale risponde")
fornitori.chiama_modello = spento
pv.archivia_in_sospeso = lambda conn, n: 0
r = pv.storico_passo(k)
st = pv.storico_stato(k)[c["chiave"]]
ok("computer spento: il mese si scarica e il recupero va avanti", r and r.get("mese") == "2026-01" and st["fino_a"] == "2026-02-01" and st["email"] == 1, (r, st))
ok("la bolletta resta da esaminare per dopo", pv.storico_numeri(k, c)["da_esaminare"] == 1)
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('posta_storico_attivo', '1') ON CONFLICT (chiave) DO UPDATE SET valore='1'")
pv.vaglia = lambda conn, forza=False, giorni=None: {"errore": "Nessun computer con il modello locale risponde"}
e = pv.giro(k)
ok("il giro automatico fa il recupero anche quando il filtro aspetta il computer", e.get("storico", {}).get("passi") and pv.storico_stato(k)[c["chiave"]]["fino_a"] == "2026-03-01", e)
fornitori.chiama_modello = finto
RISPOSTE[:] = ['<think>bolletta</think>[{"n": 1, "documento": true, "tipo": "avviso_pagamento", "controparte": "Enel", "importo": 80}]'] * 3
pv.amministrazione(k, 12)
ok("computer riacceso: l'arretrato viene esaminato", pv.storico_numeri(k, c)["documenti"] >= 1, pv.storico_numeri(k, c))
js = open("app/static/posta.js").read()
ok("la carta del recupero mostra quante restano da esaminare", "ancora da esaminare" in js and "c.documenti" in js)
k.close()
print(f"TOTALE: {sum(ris)}/{len(ris)}")
