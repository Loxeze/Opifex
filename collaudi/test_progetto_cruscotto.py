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
from app import cassaforte, agente_browser, preparazione, esecuzione, ginnasio as g
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
sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) SELECT 'Aurora','Moderatrice','manager','divisione','claude-sonnet-5-5','interno','x' WHERE NOT EXISTS (SELECT 1 FROM agenti WHERE nome='Aurora')")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    dv = sql("INSERT INTO divisioni (nome) VALUES ('Marketing') RETURNING id")[0][0]
    mg = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Marta','Manager marketing','manager','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    op = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni, superiore_id) VALUES (%s,'Omar','Copywriter','operativo','divisione','claude-sonnet-5-5','interno','x',%s) RETURNING id", (dv, mg))[0][0]
    pr = sql("INSERT INTO progetti (nome, descrizione) VALUES ('Masha','Lancio del prodotto') RETURNING id")[0][0]
    vuoto = sql("INSERT INTO progetti (nome) VALUES ('Vuoto') RETURNING id")[0][0]
    t1 = sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id, scadenza) VALUES ('Scheda cliente','in_corso',%s,%s,CURRENT_DATE - 2) RETURNING id", (pr, op))[0][0]
    t2 = sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id, scadenza, completata_il) VALUES ('Brief','completata',%s,%s,CURRENT_DATE - 5, NOW() - interval '4 days') RETURNING id", (pr, op))[0][0]
    sql("INSERT INTO task (titolo, stato, progetto_id, scadenza) VALUES ('Piano editoriale','da_fare',%s,CURRENT_DATE + 3)", (pr,))
    sql("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (t1, op, "Scheda cliente completa. " * 20))
    sql("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,'ok fatto')", (t1, op))
    d1 = sql("INSERT INTO documenti (nome, nome_file, caratteri, creato_da_agente_id) VALUES ('Analisi mercato','a.pdf',900,%s) RETURNING id", (op,))[0][0]
    sql("INSERT INTO task_documenti (task_id, documento_id) VALUES (%s,%s)", (t1, d1))
    sql("INSERT INTO documenti (nome, nome_file) VALUES ('Estraneo','e.pdf')")
    sql("INSERT INTO milestone (progetto_id, titolo, scadenza) VALUES (%s,'Lancio',CURRENT_DATE + 10)", (pr,))
    r = c.get(f"/progetti/{pr}/cruscotto", headers=H)
    ok("cruscotto risponde al titolare", r.status_code == 200, r.text[:200])
    cr = r.json()
    tipi = sorted(m["tipo"] for m in cr["materiale"])
    ok("materiale: la scheda lunga e il documento, non il commento breve né i documenti estranei", tipi == ["documento", "testo"], str(tipi))
    ok("materiale: anteprima e agente", [m for m in cr["materiale"] if m["tipo"] == "testo"][0]["agente"] == "Omar" and len([m for m in cr["materiale"] if m["tipo"] == "testo"][0]["anteprima"]) <= 260)
    ok("numeri: aperte, in ritardo, scadenze a 7 giorni", cr["numeri"]["aperte"] == 2 and cr["numeri"]["in_ritardo"] == 1 and cr["numeri"]["scadenze_7g"] == 1, str(cr["numeri"]))
    ok("task e milestone per calendario e Gantt", len(cr["task"]) == 3 and len(cr["milestone"]) == 1 and cr["task"][0]["creata_il"])
    ok("attivita' recente: commento, chiusura", {a["tipo"] for a in cr["attivita"]} >= {"commento", "completata"}, str(cr["attivita"]))
    ok("soggetti: il manager di chi lavora al progetto", [s["nome"] for s in cr["soggetti"]] == ["Marta"], str(cr["soggetti"]))
    cm = [m for m in cr["materiale"] if m["tipo"] == "testo"][0]
    ok("testo completo del contenuto", len(c.get(f"/progetti/{pr}/materiale/{cm['id']}", headers=H).json()["testo"]) > 400)
    ok("contenuto di un altro progetto: 404", c.get(f"/progetti/{vuoto}/materiale/{cm['id']}", headers=H).status_code == 404)
    ok("progetto inesistente: 404", c.get("/progetti/99999/cruscotto", headers=H).status_code == 404)
    rc = c.get(f"/progetti/{pr}/cruscotto", headers=HC)
    ok("collaboratore senza accesso al progetto: 404", rc.status_code == 404)
    ok("senza accesso: 401", c.get(f"/progetti/{pr}/cruscotto").status_code in (401, 403))
    ok("progetto vuoto: tutto vuoto, nessun errore", c.get(f"/progetti/{vuoto}/cruscotto", headers=H).json()["materiale"] == [])
    ok("riunione senza manager coinvolti: errore chiaro", c.post(f"/gestione/progetti/{vuoto}/riunione", headers=H).status_code == 422)
    ok("collaboratore non puo' avviare riunioni", c.post(f"/gestione/progetti/{pr}/riunione", headers=HC).status_code in (401, 403))
    rr = c.post(f"/gestione/progetti/{pr}/riunione", headers=H)
    ok("riunione creata con il manager coinvolto", rr.status_code == 201 and rr.json()["partecipanti"] == ["Marta"], rr.text[:200])
    tv = sql("SELECT stato, progetto_id, ordine_del_giorno, titolo FROM tavoli WHERE id = %s", (rr.json()["id"],))[0]
    ok("riunione legata al progetto e avviata", tv[0] == "in_corso" and tv[1] == pr and "Masha" in tv[3])
    ok("ordine del giorno dai dati del progetto (task in ritardo, milestone)", "Scheda cliente" in tv[2] and "Lancio" in tv[2], tv[2])
    ok("la riunione compare nel cruscotto", [x["id"] for x in c.get(f"/progetti/{pr}/cruscotto", headers=H).json()["riunioni"]] == [rr.json()["id"]])
print("TOTALE", sum(ris), "/", len(ris))
