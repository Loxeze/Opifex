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
from app import chat_coda, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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






import time
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("senza misure: messaggio chiaro", c.get("/gestione/misure", headers=H).json()["totali"]["chiamate"] == 0)
    copione[:] = [fine("Prima")]
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao dammi un parere breve", "fascia_dati": "interno"})
    ok("risposta ok", r.status_code == 200, r.text)
    copione[:] = [fine("Seconda")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "e poi?", "fascia_dati": "interno"})
    m = c.get("/gestione/misure?giorni=7", headers=H).json()
    ok("ogni risposta e' misurata", m["totali"]["chiamate"] == 2, str(m["totali"]))
    ok("origine riconosciuta (chat)", m["per_origine"][0]["origine"] == "Chat con Lorenzo", str(m["per_origine"]))
    ok("per agente con istruzioni e passi", m["per_agente"][0]["nome"] and m["per_agente"][0]["car_istruzioni"] > 0 and m["per_agente"][0]["passi_medi"] >= 1)
    voci = {x["chiave"] for x in m["composizione"]}
    ok("composizione con istruzioni e richiesta", {"istruzioni", "richiesta"} <= voci and abs(sum(x["quota"] for x in m["composizione"]) - 100) < 1, str(m["composizione"]))
    ok("la seconda risposta porta la cronologia", "storia" in voci)
    ok("risposte piu' costose elencate", len(m["piu_costose"]) == 2 and m["piu_costose"][0]["agente"])
    ok("suggerimenti presenti", isinstance(m["suggerimenti"], list))
    ok("solo il titolare vede le misure", c.get("/gestione/misure", headers=HC).status_code in (401, 403))
    ok("giorni fuori limite rifiutati", c.get("/gestione/misure?giorni=500", headers=H).status_code == 422)
    # suggerimento cache: simulo risposte con piu' passaggi
    sql("INSERT INTO misure_chiamate (agente_id, modello, origine, token_input, token_output, costo, passi) VALUES (%s,'m','Briefing',40000,500,0.5,5)", (marco,))
    m = c.get("/gestione/misure", headers=H).json()
    ok("suggerisce la cache dei prompt con la stima", any("Cache dei prompt" in s["titolo"] and s["risparmio"] > 0 for s in m["suggerimenti"]), str(m["suggerimenti"]))
    ok("origine briefing nel riepilogo", any(o["origine"] == "Briefing" for o in m["per_origine"]))
    ok("interfaccia: pagina consumi registrata", "vistaMisure" in c.get("/app/misure.js").text and "misure.js" in c.get("/app/index.html").text)
print("TOTALE", sum(ris), "/", len(ris))
