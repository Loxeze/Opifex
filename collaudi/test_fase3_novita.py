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
import time
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    dv = sql("INSERT INTO divisioni (nome) VALUES ('Prova') RETURNING id")[0][0]
    ag = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Anna','Analista','operativo','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    ag2 = sql("INSERT INTO agenti (divisione_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,'Bruno','Analista','operativo','divisione','claude-sonnet-5-5','interno','x') RETURNING id", (dv,))[0][0]
    pr = sql("INSERT INTO progetti (nome) VALUES ('Masha') RETURNING id")[0][0]
    sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id) VALUES ('Scheda cliente','in_corso',%s,%s)", (pr, ag))
    # stato prima di qualsiasi attivita'
    s0 = c.get("/gestione/agenti-stato", headers=H)
    ok("stato agenti: titolare ok, collaboratore escluso", s0.status_code == 200 and c.get("/gestione/agenti-stato", headers=HC).status_code in (401, 403))
    ok("nessuna attivita': vuoto", s0.json() == {}, str(s0.json()))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'inizio','Scrivi la scheda')", (ag,))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'fase','ragiona e scrive')", (ag,))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'strumento','cerca_sul_web')", (ag,))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'errore_strumento','timeout')", (ag,))
    s1 = c.get("/gestione/agenti-stato", headers=H).json()
    l = s1.get(str(ag), {}).get("lavoro")
    ok("agente al lavoro con progetto e compito", l and l["progetto"] == "Masha" and l["compito"] == "Scheda cliente", str(s1))
    ok("flusso dei passaggi in ordine cronologico", l and [p["tipo"] for p in l["passi"]] == ["fase", "strumento", "errore_strumento"], str(l))
    ok("chi non lavora non compare come al lavoro", str(ag2) not in s1)
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'fine','ok')", (ag,))
    s2 = c.get("/gestione/agenti-stato", headers=H).json()
    ok("finito: ultima attivita' conclusa, niente 'al lavoro'", "lavoro" not in s2[str(ag)] and s2[str(ag)]["ultimo"]["esito"] == "concluso", str(s2))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'inizio','x')", (ag2,))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'errore','boom')", (ag2,))
    ok("ultima attivita' con errore", c.get("/gestione/agenti-stato", headers=H).json()[str(ag2)]["ultimo"]["esito"] == "errore")
    # formazione
    comp = sql("INSERT INTO competenze (nome) VALUES ('Budget') RETURNING id")[0][0]
    rid = sql("INSERT INTO richieste_formazione (agente_id, competenza_id, competenza_nome, livello, stato, fase, token_usati) VALUES (%s,%s,'Budget',2,'in_corso','ricerca',1234) RETURNING id", (ag, comp))[0][0]
    sql("INSERT INTO formazione_materiale (richiesta_id, titolo, contenuto, fonte) VALUES (%s,'Doc 1','testo','http://x')", (rid,)) if False else None
    f = c.get("/gestione/agenti-stato", headers=H).json()[str(ag)].get("formazione")
    ok("formazione in corso: competenza, livello, fase, token", f and f["competenza"] == "Budget" and f["livello"] == 2 and f["fase"] == "ricerca" and f["token"] == 1234, str(f))
    sql("UPDATE richieste_formazione SET stato='conclusa' WHERE id=%s", (rid,))
    ok("formazione conclusa non compare", "formazione" not in c.get("/gestione/agenti-stato", headers=H).json()[str(ag)])
    # novita'
    n0 = c.get("/novita", headers=H).json()
    ok("prima volta: tutto a zero (nessun arretrato)", n0 == {"progetti": 0, "ginnasio": 0, "documenti": 0}, str(n0))
    time.sleep(1.1)
    sql("INSERT INTO documenti (nome, nome_file, caricato_da) VALUES ('Scheda','s.pdf',NULL)")
    sql("INSERT INTO documenti (nome, nome_file, caricato_da) VALUES ('Scheda2','s2.pdf',NULL)")
    sql("INSERT INTO task (titolo, stato, progetto_id, creato_da_agente_id) VALUES ('Nuovo da agente','da_fare',%s,%s)", (pr, ag))
    sql("UPDATE task SET stato='completata', completata_il=NOW() WHERE titolo='Scheda cliente'")
    sql("INSERT INTO richieste_formazione (agente_id, competenza_id, competenza_nome, livello, stato) VALUES (%s,%s,'Budget',3,'da_approvare')", (ag, comp))
    n1 = c.get("/novita", headers=H).json()
    ok("documenti nuovi contati", n1["documenti"] == 2, str(n1))
    ok("progetti: task creato da agente + completato", n1["progetti"] == 2, str(n1))
    ok("ginnasio: bozza da approvare contata", n1["ginnasio"] == 1, str(n1))
    ok("collaboratore vede zero", c.get("/novita", headers=HC).json() == {"progetti": 0, "ginnasio": 0, "documenti": 0})
    ok("area sconosciuta: 404", c.post("/novita/chat/visto", headers=H).status_code == 404)
    ok("segna visto: documenti si azzera", c.post("/novita/documenti/visto", headers=H).status_code == 200 and c.get("/novita", headers=H).json()["documenti"] == 0)
    ok("le altre aree restano", c.get("/novita", headers=H).json()["progetti"] == 2)
    c.post("/novita/progetti/visto", headers=H)
    ok("progetti azzerato", c.get("/novita", headers=H).json()["progetti"] == 0)
    ok("ginnasio resta finche' la bozza e' da approvare (poi visto)", c.get("/novita", headers=H).json()["ginnasio"] == 1)
    c.post("/novita/ginnasio/visto", headers=H)
    ok("ginnasio: resta 1 finche' c'e' da approvare", c.get("/novita", headers=H).json()["ginnasio"] == 1)
    ok("senza accesso: 401", c.get("/novita").status_code in (401, 403))
    import os
    from app import novita as _nv
    os.environ["OPIFEX_CACHE_STATO"] = "30"
    _nv._CACHE["t"] = 0.0
    a1 = c.get("/gestione/agenti-stato", headers=H).json()
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'inizio','nuovo')", (ag2,))
    a2 = c.get("/gestione/agenti-stato", headers=H).json()
    ok("con la cache attiva due richieste ravvicinate danno la stessa risposta (una sola lettura)", a1 == a2)
    ok("la cache non salta l'autorizzazione", c.get("/gestione/agenti-stato", headers=HC).status_code in (401, 403))
    _nv._LOCK.acquire()
    _nv._CACHE["t"] = 0.0
    ok("se una lettura e' gia' in corso si risponde subito con l'ultimo stato noto", c.get("/gestione/agenti-stato", headers=H).json() == a1)
    _nv._LOCK.release()
    os.environ["OPIFEX_CACHE_STATO"] = "0"
print("TOTALE", sum(ris), "/", len(ris))
