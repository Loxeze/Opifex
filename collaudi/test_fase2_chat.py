from datetime import datetime
import os, sys, tempfile, json
from pathlib import Path
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
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
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
from app import cassaforte, agente_browser, chat_coda, progresso, esecuzione
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
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'")
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, visti = [], []
def finta_api(corpo):
    visti.append(corpo)
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
from app import fornitori
def finto_modello(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    d = finta_api({"messages": [{"role": "user", "content": messaggio}]})
    return fornitori.Risposta(testo=d["content"][0]["text"], token_input=100, token_output=20)
esecuzione.chiama_modello = finto_modello
import threading, time
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    dv = sql("INSERT INTO divisioni (nome) VALUES ('Prova') RETURNING id")[0][0]
    A = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Anna','Analista','operativo','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    B = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Bruno','Analista','operativo','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    # 1) la fase e il tempo si vedono durante il lavoro; 2) annullando in lavorazione ci si ferma al passaggio successivo
    fermo = threading.Event(); via = threading.Event()
    def lento(agente_id, messaggio, *a, **k):
        progresso.fase("cerca sul web")
        fermo.set(); via.wait(5)
        progresso.fase("rielabora i risultati")      # qui arriva l'annullamento
        return {"risposta": "non dovrebbe arrivare", "token_input": 1, "token_output": 1}
    chat_coda.esegui_agente = lento
    cid = chat_coda.accoda(A, uid, "fai una ricerca", "pubblico")
    fermo.wait(5); time.sleep(0.2)
    m = [x for x in c.get(f"/chat/conversazioni/{A}", headers=H).json()["messaggi"] if x["id"] == cid][0]
    ok("durante il lavoro: stato, fase e tempo trascorso", m["stato"] == "in_lavoro" and m["fase"] == "cerca sul web" and m["attesa_s"] is not None, str(m)[:200])
    ok("annullare in lavorazione e' accettato", c.post(f"/chat/messaggi/{cid}/annulla", headers=H).json() == {"ok": True, "subito": False})
    via.set(); time.sleep(0.6)
    m = [x for x in c.get(f"/chat/conversazioni/{A}", headers=H).json()["messaggi"] if x["id"] == cid][0]
    ok("si ferma al passaggio successivo: nessuna risposta", m["stato"] == "errore" and m["errore"] == "Annullata da te" and m["risposta"] is None and m["fase"] is None, str(m)[:200])
    ok("non si annulla due volte", c.post(f"/chat/messaggi/{cid}/annulla", headers=H).status_code == 409)
    # 3) annullare un messaggio in coda: subito, e il lavoro non parte mai
    partiti = []
    def mai(agente_id, messaggio, *a, **k):
        partiti.append(messaggio); return {"risposta": "ok", "token_input": 1, "token_output": 1}
    chat_coda.esegui_agente = mai
    lock = chat_coda._blocco(B); lock.acquire()
    cid2 = chat_coda.accoda(B, uid, "primo", "pubblico")
    time.sleep(0.3)
    r = c.post(f"/chat/messaggi/{cid2}/annulla", headers=H).json()
    lock.release(); time.sleep(0.5)
    ok("in coda: annullata subito e mai eseguita", r["subito"] is True and partiti == [] and sql("SELECT stato, errore FROM chat_coda WHERE id=%s", (cid2,))[0] == ("errore", "Annullata da te"))
    # 4) lavoro normale: la risposta arriva e la fase si azzera
    cid3 = chat_coda.accoda(B, uid, "ciao", "pubblico"); time.sleep(0.5)
    ok("messaggio normale: finito, fase azzerata", sql("SELECT stato, fase FROM chat_coda WHERE id=%s", (cid3,))[0] == ("finito", None))
    # 5) un altro utente non puo' annullare
    sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Dario','d@p.it',%s,'titolare')", (cifra_password(PW),))
    HD = {"Authorization": "Bearer " + accedi(c, "d@p.it", PW)}
    cid4 = chat_coda.accoda(A, uid, "x", "pubblico")
    ok("un altro utente non puo' annullare i miei messaggi", c.post(f"/chat/messaggi/{cid4}/annulla", headers=HD).status_code in (404, 409))
    # 6) ordine: scrivere una bozza non sposta la conversazione sopra a una con piu' attivita' recente
    sql("UPDATE chat_coda SET creato_il = NOW() - interval '2 hours', finito_il = NOW() - interval '2 hours' WHERE agente_id=%s", (A,))
    c.put(f"/chat/conversazioni/{A}/bozza", headers=H, json={"testo": "bozza", "fascia": "pubblico"})
    elenco = [x["nome"] for x in c.get("/chat/conversazioni", headers=H).json()]
    ok("la bozza non fa risalire la conversazione", elenco.index("Bruno") < elenco.index("Anna"), str(elenco))
    ok("la fase del progresso senza ascoltatore non fa nulla", progresso.fase("x") is None)
js = open("app/static/chat.js").read()
ok("interfaccia: annulla, tempo, tastiera, indietro del telefono, annuncio limitato", all(x in js for x in ('/annulla', 'tempo-att', 'ArrowDown', 'popstate', 'pushState', 'aria-live', 'prefers' if False else 'role: "list"')))
print("TOTALE", sum(ris), "/", len(ris))
