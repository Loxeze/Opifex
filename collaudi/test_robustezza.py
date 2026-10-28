import os, sys, tempfile, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
import httpx
from app import fornitori, main as principale, db as modulo_db, webpush, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")




class R:
    def __init__(s, codice, testo="", intest=None): s.status_code, s.text, s.headers = codice, testo, intest or {}
    def json(s): return {"content": [{"type": "text", "text": "ciao"}], "usage": {"input_tokens": 3, "output_tokens": 2}, "stop_reason": "end_turn"}
chiamate, esiti, pause = [], [], []
def finto_post(url, headers=None, json=None, timeout=None):
    chiamate.append(url); e = esiti.pop(0)
    if isinstance(e, Exception): raise e
    return e
httpx.post = finto_post
fornitori.time.sleep = lambda x: pause.append(x)
fornitori.chiave = lambda n: "k"
modulo_db.apri_pool()
def prova(seq):
    chiamate.clear(); pause.clear(); esiti[:] = seq
    return fornitori.invia("https://x", {}, {})
r = prova([R(529), R(529), R(200)])
ok("sovraccarico 529 due volte, poi riesce: 3 tentativi con pause crescenti", r.status_code == 200 and len(chiamate) == 3 and pause == [2, 6], str(pause))
r = prova([R(400, "richiesta errata")])
ok("errore definitivo (400): nessun nuovo tentativo", r.status_code == 400 and len(chiamate) == 1 and not pause)
r = prova([R(401, "chiave")]); ok("chiave errata (401): subito", r.status_code == 401 and len(chiamate) == 1)
r = prova([httpx.ReadTimeout("t"), httpx.ConnectError("c"), R(200)])
ok("timeout e rete interrotta: si riprova", r.status_code == 200 and len(chiamate) == 3)
r = prova([R(429, "", {"retry-after": "9"}), R(200)])
ok("429: si rispetta il tempo di attesa indicato dal fornitore", r.status_code == 200 and pause == [9])
r = prova([R(429, "", {"retry-after": "9999"}), R(200)])
ok("attesa massima 30 secondi", pause == [30])
try:
    prova([httpx.ReadTimeout("t")] * 4); eccezione = None
except fornitori.ErroreFornitore as e: eccezione = str(e)
ok("sempre in timeout: errore chiaro del fornitore, non un crash", eccezione and "non risponde" in eccezione and "ReadTimeout" in eccezione and len(chiamate) == 4, str(eccezione))
r = prova([R(503), R(503), R(503), R(503)])
ok("503 ripetuto: dopo i tentativi risponde il chiamante con il codice", r.status_code == 503 and len(chiamate) == 4)
chiamate.clear(); pause.clear(); esiti[:] = [R(529), R(200)]
risp = fornitori.chiama_modello("anthropic", "m", "s", "msg", 100)
ok("chiamata semplice: un 529 non ferma piu' l'agente", risp.testo == "ciao" and len(chiamate) == 2)
import importlib
from app import agente_browser
importlib.reload(agente_browser)
agente_browser.fornitori_chiave = lambda n: "k"
chiamate.clear(); pause.clear(); esiti[:] = [R(529), R(200)]
d = agente_browser._chiama_api({"model": "m", "max_tokens": 10, "messages": []})
ok("chiamata con strumenti: stessa protezione", d["stop_reason"] == "end_turn" and len(chiamate) == 2, f"{d} {chiamate}")
# lavori di fondo isolati
fatti = []
def rotto(c): raise RuntimeError("guasto di prova")
principale._passo("prova guasto", rotto)
principale._passo("secondo", lambda c: fatti.append(1))
principale._passo("prova guasto", rotto)
ok("un passo che fallisce non ferma gli altri", fatti == [1])
ok("il guasto genera una sola notifica al giorno", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%prova guasto%'")[0][0] == 1)
# limiti
imp = {k: v for k, v in sql("SELECT chiave, valore FROM impostazioni_sistema WHERE chiave LIKE 'dialoghi_%'")}
ok("limiti dei dialoghi allargati (30 milioni di token/giorno, 12 messaggi, 5 domande)", imp["dialoghi_budget_token_giornaliero"] == "30000000" and imp["dialoghi_max_messaggi"] == "12" and imp["dialoghi_max_domande"] == "5", str(imp))
ok("nuovi agenti: 16000 token di risposta di base; i dialoghi 16000", sql("SELECT column_default FROM information_schema.columns WHERE table_name='agenti' AND column_name='max_token_risposta'")[0][0] == "16000" and dialoghi.MAX_TOKEN_DIALOGO == 16000)
ok("tutti gli agenti gia' al valore iniziale sono passati a 3000", sql("SELECT count(*) FROM agenti WHERE max_token_risposta=1500")[0][0] == 0)
sql("UPDATE impostazioni_sistema SET valore='555555' WHERE chiave='dialoghi_budget_token_giornaliero'")
sql("UPDATE impostazioni_sistema SET valore='9' WHERE chiave='dialoghi_max_messaggi'")
sql("UPDATE agenti SET max_token_risposta=1500 WHERE nome='Marco'"); sql("UPDATE agenti SET max_token_risposta=2000 WHERE nome='Leo'")
import subprocess
sql("DELETE FROM impostazioni_sistema WHERE chiave='migrazione_limiti_1_23_3'"); sql(open("sql/49_limiti_piu_larghi.sql").read())
imp = dict(sql("SELECT chiave, valore FROM impostazioni_sistema WHERE chiave LIKE 'dialoghi_%'"))
ok("la migrazione non tocca i valori scelti a mano", imp["dialoghi_budget_token_giornaliero"] == "555555" and imp["dialoghi_max_messaggi"] == "9")
ok("e rispetta i tetti personalizzati dei singoli agenti", sql("SELECT max_token_risposta FROM agenti WHERE nome='Leo'")[0][0] == 2000 and sql("SELECT max_token_risposta FROM agenti WHERE nome='Marco'")[0][0] == 3000)
ok("riserva di connessioni al database per gli agenti al lavoro", modulo_db.pool.max_size >= 40 and modulo_db.pool.timeout >= 60)
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ok("la schermata dei limiti mostra i nuovi valori", c.get("/gestione/dialoghi/limiti", headers=H).json()["dialoghi_max_domande"] in ("5", 5), c.get("/gestione/dialoghi/limiti", headers=H).text)
print("TOTALE", sum(ris), "/", len(ris))
