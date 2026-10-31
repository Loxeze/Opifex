import os, sys, tempfile, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"; os.environ["CHIAVE_OPENAI"] = "finta-openai-0123456789"
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







from app import modello_economico
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    sql("UPDATE modelli_ai SET costo_input_per_milione=0.10, costo_output_per_milione=0.50, fascia='economico' WHERE nome='claude-haiku-5-5'")
    sql("UPDATE modelli_ai SET costo_input_per_milione=5, costo_output_per_milione=25 WHERE nome='claude-opus-5-5'")
    sql("INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia) VALUES ((SELECT id FROM fornitori_ai WHERE nome='openai'),'gpt-6-luna',0.10,0.50,'economico') ON CONFLICT DO NOTHING")
    sql("UPDATE agenti SET modello='claude-opus-5-5', modello_dialogo='claude-sonnet-5-5' WHERE id=%s", (marco,))
    sql("UPDATE agenti SET modello='gpt-4o', accesso_web=TRUE WHERE id=%s", (scout,))
    sql("UPDATE agenti SET modello='claude-sonnet-5-5', accesso_web=FALSE WHERE id=%s", (dario,))
    p = c.get("/gestione/modelli-economici", headers=H).json()["piano"]
    pm_ = {x["nome"]: x for x in p}
    ok("anteprima: Marco da Opus a Haiku (ha il web: resta Claude)", pm_["Marco"]["attuale"] == "claude-opus-5-5" and pm_["Marco"]["proposto"] == "claude-haiku-5-5", str(pm_["Marco"]))
    ok("a parita' di prezzo con ChatGPT resta Claude", all(x["proposto"] != "gpt-6-luna" for x in p))
    ok("anteprima non cambia nulla", sql("SELECT modello FROM agenti WHERE id=%s", (marco,)) == [("claude-opus-5-5",)])
    ok("solo il titolare puo' cambiare i modelli", c.post("/gestione/modelli-economici", headers=HC).status_code in (401, 403))
    r = c.post("/gestione/modelli-economici", headers=H).json()
    ok("applicato a tutti", r["agenti_cambiati"] >= 3 and sql("SELECT count(*) FROM agenti WHERE modello <> 'claude-haiku-5-5'")[0][0] == 0, str(sql("SELECT nome, modello FROM agenti WHERE modello <> 'claude-haiku-5-5'")))
    ok("chi usa la ricerca web resta su Claude (Scout)", sql("SELECT modello FROM agenti WHERE id=%s", (scout,)) == [("claude-haiku-5-5",)])
    ok("modello precedente conservato", sql("SELECT modello_precedente FROM agenti WHERE id=%s", (marco,)) == [("claude-opus-5-5",)] and sql("SELECT modello_precedente FROM agenti WHERE id=%s", (scout,)) == [("gpt-4o",)])
    ok("scelta manuale dei dialoghi tolta", sql("SELECT count(*) FROM agenti WHERE modello_dialogo IS NOT NULL")[0][0] == 0)
    c.post("/gestione/modelli-economici", headers=H)
    ok("secondo giro: il precedente non viene sovrascritto", sql("SELECT modello_precedente FROM agenti WHERE id=%s", (marco,)) == [("claude-opus-5-5",)])
    ok("una risposta funziona col nuovo modello", c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"}).status_code == 200)
    ok("la misura riporta il nuovo modello", sql("SELECT modello FROM misure_chiamate ORDER BY id DESC LIMIT 1") == [("claude-haiku-5-5",)])
    r = c.post("/gestione/modelli-economici/ripristina", headers=H).json()
    ok("ripristino", r["agenti_ripristinati"] >= 3 and sql("SELECT modello FROM agenti WHERE id=%s", (marco,)) == [("claude-opus-5-5",)] and sql("SELECT modello FROM agenti WHERE id=%s", (scout,)) == [("gpt-4o",)])
    ok("dopo il ripristino niente precedente", sql("SELECT count(*) FROM agenti WHERE modello_precedente IS NOT NULL")[0][0] == 0)
    # un modello ChatGPT davvero piu' economico viene scelto, tranne per chi ha il web
    sql("INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia) VALUES ((SELECT id FROM fornitori_ai WHERE nome='openai'),'gpt-5-nano',0.05,0.20,'economico') ON CONFLICT DO NOTHING")
    p = {x["nome"]: x for x in c.get("/gestione/modelli-economici", headers=H).json()["piano"]}
    ok("se ChatGPT costa meno viene proposto", p["Dario"]["proposto"] == "gpt-5-nano", str(p["Dario"]))
    ok("ma non a chi cerca sul web", p["Scout"]["proposto"] == "claude-haiku-5-5" and p["Marco"]["proposto"] == "claude-haiku-5-5", str(p["Scout"]))
    sql("UPDATE agenti SET fascia_dati_max='riservato'"); sql("UPDATE fornitori_ai SET non_conservazione_attiva=FALSE WHERE nome='openai'")
    p = {x["nome"]: x for x in c.get("/gestione/modelli-economici", headers=H).json()["piano"]}
    ok("riservatezza: senza garanzie del fornitore niente ChatGPT", p["Dario"]["proposto"] == "claude-haiku-5-5", str(p["Dario"]))
    # una volta sola
    sql("DELETE FROM impostazioni_sistema WHERE chiave=%s", (modello_economico.MARCA,))
    with connessione() as cn:
        n1 = modello_economico.una_volta(cn)
    with connessione() as cn:
        n2 = modello_economico.una_volta(cn)
    ok("all'aggiornamento: una sola volta", n1 >= 1 and n2 == 0, f"{n1} {n2}")
    ok("avviso a Lorenzo", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%modello piu%economico%'")[0][0] >= 1)
print("TOTALE", sum(ris), "/", len(ris))
