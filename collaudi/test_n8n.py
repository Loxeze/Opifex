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
from app import cassaforte, agente_browser, n8n, esecuzione, crm, reparti_pronti
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
import httpx
chiamate = []
def finto(metodo, url, json=None, params=None, headers=None, timeout=None, follow_redirects=None):
    chiamate.append((metodo, url, json, params, headers))
    class R:
        status_code = 200
        def json(self_):
            if url.endswith("/workflows") and metodo == "GET":
                return {"data": [{"id": "w1", "name": "Bandi", "active": True, "updatedAt": "x", "nodes": [1, 2]}]}
            if url.endswith("/workflows/w1"):
                return {"id": "w1", "name": "Bandi", "active": True, "nodes": [{"name": "Cron", "type": "n8n-nodes-base.scheduleTrigger", "parameters": {"a": 1}, "credentials": {"x": "SEGRETO"}}], "connections": {}}
            if url.endswith("/executions"):
                return {"data": [{"id": 5, "workflowId": "w1", "status": "error", "startedAt": "t0", "stoppedAt": "t1", "mode": "trigger", "data": {"segreto": "PRIVATO"}}]}
            if metodo == "POST":
                return {"id": "w9", "name": json["name"]}
            return {}
    return R()
httpx.request = finto
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("Carla non puo'", c.get("/gestione/n8n", headers=HC).status_code == 403)
    ok("non collegato", c.get("/gestione/n8n", headers=H).json()["collegato"] is False)
    ok("indirizzo con credenziali rifiutato", c.put("/gestione/n8n", headers=H, json={"url": "https://u:p@n8n.it", "chiave": "k" * 20}).status_code == 409)
    ok("senza reparto l'agente non c'e'", sql("SELECT count(*) FROM agenti WHERE nome='Esperto n8n'")[0][0] == 0)
    with connessione() as cn:
        reparti_pronti.attiva(cn, "sviluppo")
    r = c.put("/gestione/n8n", headers=H, json={"url": "https://n8n.esempio.it/", "chiave": "chiave-n8n-di-prova-1234"})
    ok("collegato", r.status_code == 200, r.text)
    ok("chiave cifrata e mai restituita", "chiave-n8n" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='n8n_chiave_cifrata'")[0][0] and "chiave-n8n" not in json.dumps(c.get("/gestione/n8n", headers=H).json()))
    ok("chiamata con l'header della chiave e url normalizzato", chiamate[-1][4]["X-N8N-API-KEY"] == "chiave-n8n-di-prova-1234" and chiamate[-1][1] == "https://n8n.esempio.it/api/v1/workflows", str(chiamate[-1][1]))
    ok("agente creato in Sviluppo software, con flag", sql("SELECT d.nome, a.n8n_attivo FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE a.nome='Esperto n8n'")[0] == ("Sviluppo software", True))
    aid = sql("SELECT id FROM agenti WHERE nome='Esperto n8n'")[0][0]
    with connessione() as cn:
        g = n8n.gestore(connessione, aid)
    ok("elenco", "Bandi" in g("n8n_workflow_elenca", {}))
    o = g("n8n_workflow_leggi", {"id": "w1"})
    ok("lettura senza credenziali", "Cron" in o and "SEGRETO" not in o)
    ok("id con caratteri strani rifiutato", g("n8n_workflow_leggi", {"id": "../x"}).startswith("ERRORE"))
    o = g("n8n_esecuzioni", {"workflow_id": "w1", "stato": "error"})
    ok("esecuzioni: solo stato e orari, mai i dati", "error" in o and "PRIVATO" not in o and chiamate[-1][3]["includeData"] == "false")
    o = g("n8n_workflow_bozza", {"nome": "Avviso bandi", "nodi": [{"name": "Cron", "type": "n8n-nodes-base.scheduleTrigger", "position": [0, 0], "credentials": {"x": "S"}}], "connessioni": {}})
    post = [x for x in chiamate if x[0] == "POST"][-1]
    ok("bozza creata con prefisso, senza credenziali, senza attivazione", o.startswith("OK") and post[2]["name"].startswith("[BOZZA Opifex] ") and "credentials" not in post[2]["nodes"][0] and "active" not in post[2], str(post[2])[:200])
    ok("nodo senza position rifiutato", g("n8n_workflow_bozza", {"nome": "x", "nodi": [{"name": "a", "type": "b"}]}).startswith("ERRORE"))
    ok("nessuna chiamata di attivazione/cancellazione possibile", all(x[0] in ("GET", "POST") and "activate" not in x[1] for x in chiamate))
    copione[:] = [fine("ok")]
    esecuzione.esegui_agente(aid, "elenca i workflow", "interno", None, max_token=300)
    ok("l'agente riceve gli strumenti n8n", visti and "n8n_workflow_bozza" in [t["name"] for t in visti[-1].get("tools", [])], str([t["name"] for t in visti[-1].get("tools", [])]) if visti else "")
    ok("scollega", c.delete("/gestione/n8n", headers=H).status_code == 200 and c.get("/gestione/n8n", headers=H).json()["collegato"] is False)
print("TOTALE", sum(ris), "/", len(ris))
