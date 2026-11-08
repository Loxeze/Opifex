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
preparazione.SINCRONO = True
preparazione.IGNORA_NOTTE = True
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    dv = sql("INSERT INTO divisioni (nome) VALUES ('Prova') RETURNING id")[0][0]
    ag = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Anna','Analista','operativo','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    cs = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni, ruolo_speciale) VALUES (%s,'Padre Casati','Formatore','operativo','divisione','claude-sonnet-5-5','interno','x','formatore') RETURNING id", (dv,))[0][0]
    comp = sql("INSERT INTO competenze (nome) VALUES ('Budget di progetto') RETURNING id")[0][0]
    sql("INSERT INTO competenze_livelli (competenza_id, livello, corpo, stato) VALUES (%s,1,'Il budget si divide in voci di costo; le spese ammissibili sono quelle previste dal bando.','approvata')", (comp,))
    sql("INSERT INTO competenze_livelli (competenza_id, livello, corpo, stato) VALUES (%s,2,'Livello due: rendicontazione e scostamenti.','approvata')", (comp,))
    sql("INSERT INTO agenti_competenze (agente_id, competenza_id, livello) VALUES (%s,%s,1)", (ag, comp))
    DOM = "D1: Quali spese sono ammissibili?\nD2: Come si divide il budget?\nD3: Chi decide le voci?"
    copione[:] = [fine(DOM), fine("R1 le previste dal bando\nR2 in voci di costo\nR3 non so"), fine("V1: 9\nV2: 10\nV3: 8\nLACUNE: nessuna")]
    ris_ = preparazione.verifica(ag, comp)
    ok("verifica conclusa con voto medio 9.0", ris_["esito"] == "ok" and ris_["voto"] == 9.0, str(ris_))
    ok("le domande nascono dal testo del livello (Casati)", "bando" in visti[0]["messages"][0]["content"] if isinstance(visti[0]["messages"][0]["content"], str) else True)
    ok("tre chiamate: domande, risposta dell'agente, correzione", len(visti) == 3)
    ok("voto alto: passa al livello successivo (gia' approvato: assegnato)", sql("SELECT livello FROM agenti_competenze WHERE agente_id=%s", (ag,))[0][0] == 2)
    copione[:] = [fine(DOM), fine("R1 boh\nR2 boh\nR3 boh"), fine("V1: 2\nV2: 3\nV3: 1\nLACUNE: non conosce le spese ammissibili")]
    r2 = preparazione.verifica(ag, comp)
    ok("voto basso: esito lacune e notifica", r2["esito"] == "lacune" and r2["voto"] == 2.0 and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Verifica di preparazione%'")[0][0] == 1, str(r2))
    copione[:] = [fine("niente domande")]
    r3 = preparazione.verifica(ag, comp)
    ok("domande non valide: errore registrato, nessun voto", r3["esito"] == "errore" and sql("SELECT voto FROM verifiche_competenza WHERE id=%s", (r3["id"],))[0][0] is None)
    ok("correzione illeggibile: errore", (lambda: (copione.__setitem__(slice(None), [fine(DOM), fine("R"), fine("boh")]), preparazione.verifica(ag, comp)["esito"])[1])() == "errore")
    ok("lettura voti: servono tre voti", preparazione.leggi_voti("V1: 7\nV2: 8")[0] is None and preparazione.leggi_voti("V1: 7,5\nV2: 8\nV3: 12\nLACUNE: x")[0] == 8.5)
    v = c.get("/gestione/ginnasio/preparazione", headers=H).json()
    ok("vista: Anna con media sull'ultima verifica valida (2.0)", v["agenti"] and v["agenti"][0]["nome"] == "Anna" and float(v["agenti"][0]["media"]) == 2.0 and v["ultime"], str(v["agenti"]))
    ok("Carla non puo'", c.get("/gestione/ginnasio/preparazione", headers=HC).status_code == 403)
    # giro: nessun candidato perche' appena verificata
    ok("giro: nulla da fare (verificata da poco)", preparazione.giro(__import__("app.db", fromlist=["x"]).connessione().__enter__()) is None)
    sql("UPDATE verifiche_competenza SET creata_il = NOW() - interval '10 days'")
    with connessione() as cn:
        ok("dopo 7 giorni e' di nuovo candidata", len(preparazione.candidati(cn, 6)) == 1)
        copione[:] = [fine(DOM), fine("R1 a\nR2 b\nR3 c"), fine("V1: 7\nV2: 7\nV3: 7\nLACUNE: nessuna")]
        ok("il giro la verifica", preparazione.giro(cn) == 1)
        preparazione.IGNORA_NOTTE = False; _n = preparazione.NOTTE; preparazione.NOTTE = (25, 26)
        ok("fuori dalla notte non parte", preparazione.giro(cn) is None)
        preparazione.NOTTE = _n
    ok("impostazioni", c.put("/gestione/ginnasio/preparazione", headers=H, json={"attiva": False, "giorni": 14, "per_giro": 3}).status_code == 200 and c.get("/gestione/ginnasio/preparazione", headers=H).json()["giorni"] == 14)
    ok("avvio manuale", (lambda: (copione.__setitem__(slice(None), [fine(DOM), fine("R"), fine("V1: 6\nV2: 6\nV3: 6\nLACUNE: x")]), c.post("/gestione/ginnasio/preparazione", headers=H, json={"agente_id": ag, "competenza_id": comp}).json()["esito"])[1])() == "ok")
print("TOTALE", sum(ris), "/", len(ris))
