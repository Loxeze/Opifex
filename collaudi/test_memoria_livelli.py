import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import esecuzione, memoria_lavoro
from app.sicurezza import cifra_password
from app.db import connessione
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE"); sql("UPDATE agenti SET fascia_dati_max='riservato'")
anna = sql("SELECT id FROM utenti WHERE email='anna@p.it'")[0][0]
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (anna, mk))
sofia = sql("SELECT id FROM agenti WHERE nome='Sofia'")[0][0]; scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
sql("UPDATE agenti SET divisione_id=NULL WHERE id IN (%s,%s)", (sofia, scout))
sql("INSERT INTO task (titolo, assegnato_agente_id) VALUES ('Candidatura Olivetti', %s)", (sofia,))
tk = sql("SELECT id FROM task")[0][0]
with TestClient(app) as c:
    HT = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    seed = sql("SELECT count(*) FROM memorie_lavoro WHERE persona AND stato='proposta'")[0][0]
    ok("voci iniziali su Lorenzo: proposte, non ancora valide", seed >= 8 and sql("SELECT count(*) FROM memorie_lavoro WHERE persona AND stato='approvata'")[0][0] == 0, str(seed))
    with connessione() as conn:
        a = esecuzione._carica_agente(conn, sofia)
        ok("proposte non arrivano agli agenti", "Masone" not in memoria_lavoro.contesto(conn, a, "dove vive Lorenzo"))
    pid = sql("SELECT id FROM memorie_lavoro WHERE persona AND tema='chi sono'")[0][0]
    ok("il titolare approva la voce su di se'", c.post(f"/memoria/{pid}/decisione", headers=HT, json={"azione": "approva"}).status_code == 200)
    with connessione() as conn:
        t1 = memoria_lavoro.contesto(conn, a, "preparami una bozza qualsiasi"); t2 = memoria_lavoro.contesto(conn, esecuzione._carica_agente(conn, scout), "altro")
    ok("livello 1 arriva a ogni agente anche se la domanda non lo nomina", "Masone" in t1 and "Masone" in t2 and "CHI E' LORENZO" in t1, t1[:200])
    ok("Anna non vede le voci su Lorenzo", all(not v["persona"] for v in c.get("/memoria?stato=tutte", headers=HA).json()["voci"]))
    ok("Anna non puo' scrivere sul livello 1", c.post("/memoria", headers=HA, json={"testo": "Voce non mia sulla persona.", "persona": True}).status_code == 403)
    ok("livello 1 non ha altro ambito", c.post("/memoria", headers=HT, json={"testo": "Voce con ambito sbagliato.", "persona": True, "divisione_id": mk}).status_code == 422)
    r = c.post("/memoria", headers=HT, json={"testo": "Per la candidatura Olivetti il titolo provvisorio e' Bellezza Accessibile.", "task_id": tk, "tipo": "decisione"})
    ok("voce di task registrata", r.status_code == 201, r.text)
    ok("task inesistente: 422", c.post("/memoria", headers=HT, json={"testo": "Voce su un task che non c'e'.", "task_id": 99999}).status_code == 422)
    with connessione() as conn:
        ca = memoria_lavoro.contesto(conn, a, "avanti"); cs = memoria_lavoro.contesto(conn, esecuzione._carica_agente(conn, scout), "avanti")
    ok("l'agente del task vede il livello 4, in sezione propria", "TASK IN CORSO" in ca and "Bellezza Accessibile" in ca, ca[:300])
    ok("un agente estraneo al task non lo vede", "Bellezza Accessibile" not in cs)
    ok("l'ordine dei livelli: Lorenzo prima del task", ca.index("CHI E' LORENZO") < ca.index("TASK IN CORSO"))
    ok("filtro per livello", {v["livello"] for v in c.get("/memoria?stato=approvata&livello=4", headers=HT).json()["voci"]} == {4} and len(c.get("/memoria?stato=approvata&livello=1", headers=HT).json()["voci"]) == 1)
    sql("UPDATE agenti SET fascia_dati_max='pubblico' WHERE id=%s", (sofia,))
    with connessione() as conn:
        cp = memoria_lavoro.contesto(conn, esecuzione._carica_agente(conn, sofia), "avanti")
    ok("la riservatezza vale anche per il livello 1", "Masone" not in cp)
    sql("DELETE FROM task WHERE id=%s", (tk,))
    ok("cancellato il task, spariscono le sue voci", sql("SELECT count(*) FROM memorie_lavoro WHERE task_id IS NOT NULL")[0][0] == 0)
    ok("migrazione ripetibile: nessun duplicato di voci iniziali", (sql("SELECT count(*) FROM memorie_lavoro WHERE persona")[0][0] == seed))
print("TOTALE", sum(ris), "/", len(ris))
sys.exit(0 if all(ris) else 1)
