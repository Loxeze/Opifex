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
from app import uso_misure, uso_ux
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    S1, S2 = "a1b2c3d4e5f60718", "0011223344556677"
    ev = [
        {"vista": "dashboard", "azione": "vista", "sessione": S1, "dispositivo": "desktop"},
        {"vista": "dashboard", "azione": "uscita", "durata_s": 42, "sessione": S1, "dispositivo": "desktop"},
        {"vista": "agenti", "azione": "errore", "categoria": "timeout", "componente": "/gestione/agenti/:x", "durata_ms": 8000, "sessione": S1, "dispositivo": "telefono"},
        {"vista": "agenti", "azione": "riprova", "esito": "riuscito", "componente": "/gestione/agenti/:x", "durata_ms": 900, "sessione": S1},
        {"vista": "agenti", "azione": "riprova", "esito": "fallito", "componente": "/gestione/agenti/:x", "durata_ms": 700, "sessione": S2},
        {"vista": "agenti", "azione": "clic", "elemento": "menu-agenti", "sessione": S1},
        {"vista": "agenti", "azione": "clic", "elemento": "Mario Rossi mario@x.it", "sessione": S1},       # testo con spazi e chiocciola: va scartato
        {"vista": "chat", "azione": "attesa_inizio", "agente_id": 7, "sessione": S1},
        {"vista": "chat", "azione": "attesa_fine", "agente_id": 7, "durata_ms": 31000, "esito": "risposta", "sessione": S1},
        {"vista": "chat", "azione": "attesa_fine", "agente_id": 7, "durata_ms": 90000, "esito": "annullata", "sessione": S2},
        {"vista": "dashboard", "azione": "contatore_visto", "elemento": "documenti", "sessione": S1},
        {"vista": "documenti", "azione": "contatore_aperto", "elemento": "documenti", "sessione": S1},
        {"vista": "x", "azione": "inventata", "sessione": S1},
        {"vista": "pagina con spazi", "azione": "vista"},
        {"vista": "chat", "azione": "vista", "sessione": "NON-VALIDA!", "dispositivo": "frigorifero"},
    ]
    r = c.post("/uso", headers=H, json={"eventi": ev})
    ok("registrazione accettata", r.status_code == 200 and r.json()["registrati"] == 13, r.text)
    righe = sql("SELECT azione, utente_id, sessione, dispositivo, elemento, componente, agente_id, esito, durata_ms, categoria FROM uso_eventi ORDER BY id")
    per = lambda az: [x for x in righe if x[0] == az]
    ok("azione inventata e nome pagina con spazi scartati", len(righe) == 13 and not per("inventata"))
    ok("eventi anonimi (clic, riprova, attese, contatori) senza persona", all(x[1] is None for a in ("clic", "riprova", "attesa_inizio", "attesa_fine", "contatore_visto", "contatore_aperto") for x in per(a)))
    ok("pagine ed errori restano legati alla persona (presenza in plancia)", all(x[1] is not None for a in ("vista", "uscita", "errore") for x in per(a)))
    ok("clic con testo/chiocciola: elemento scartato, nessun testo salvato", [x[4] for x in per("clic")] == ["menu-agenti", None] and not any("rossi" in str(x).lower() or "@" in str(x) for x in righe))
    ok("sessione non valida e dispositivo sconosciuto scartati", per("vista")[-1][2] is None and per("vista")[-1][3] is None)
    ok("classe di dispositivo e sessione salvate", per("vista")[0][2] == S1 and per("vista")[0][3] == "desktop" and per("errore")[0][3] == "telefono")
    ok("errore con componente, categoria e durata", per("errore")[0][5] == "/gestione/agenti/:x" and per("errore")[0][9] == "timeout" and per("errore")[0][8] == 8000)
    ok("riprova con esito", sorted(x[7] for x in per("riprova")) == ["fallito", "riuscito"])
    ok("attesa con id agente, durata ed esito", per("attesa_inizio")[0][6] == 7 and sorted(x[7] for x in per("attesa_fine")) == ["annullata", "risposta"] and per("attesa_fine")[0][8] == 31000)
    ok("durate limitate (10 minuti al massimo)", c.post("/uso", headers=H, json={"eventi": [{"vista": "chat", "azione": "attesa_fine", "durata_ms": 99999999, "esito": "risposta", "agente_id": 1}]}).status_code == 200 and sql("SELECT max(durata_ms) FROM uso_eventi")[0][0] == 600000)
    ok("collaboratore registra ma non legge il rapporto", c.post("/uso", headers=HC, json={"eventi": [ev[0]]}).status_code == 200 and c.get("/gestione/uso-misure", headers=HC).status_code in (401, 403))
    rap = c.get("/gestione/uso-misure?giorni=7", headers=H).json()
    ok("rapporto: sessioni distinte e dispositivi", rap["sessioni"] == 2 and rap["dispositivi"].get("desktop") == 1 and rap["dispositivi"].get("telefono") == 1, str(rap["dispositivi"]) + str(rap["sessioni"]))
    ok("rapporto: errori per componente", rap["errori"][0]["componente"] == "/gestione/agenti/:x" and rap["errori"][0]["categoria"] == "timeout")
    ok("rapporto: esiti di Riprova", rap["riprova"] == {"riuscito": 1, "fallito": 1}, str(rap["riprova"]))
    ok("rapporto: clic per elemento", rap["clic"][0]["elemento"] == "menu-agenti")
    a7 = [a for a in rap["attese"] if a["agente_id"] == 7]
    ok("rapporto: attese per agente con non concluse", a7 and a7[0]["n"] == 2 and a7[0]["non_concluse"] == 1, str(rap["attese"]))
    ok("rapporto: contatori mostrati e aperti", rap["contatori"] == [{"area": "documenti", "mostrati": 1, "aperti": 1}], str(rap["contatori"]))
    # riepilogo giornaliero: serve un giorno concluso
    sql("UPDATE uso_eventi SET creato_il = NOW() - INTERVAL '1 day'")
    with connessione() as cn:
        n1 = uso_misure.aggrega(cn); n2 = uso_misure.aggrega(cn)
        tot = cn.execute("SELECT sum(eventi) AS e, count(*) AS r FROM uso_giorno").fetchone()
        sess = cn.execute("SELECT count(*) FILTER (WHERE sessioni = 1) AS s FROM uso_giorno WHERE azione='riprova'").fetchone()["s"]
        ok("aggregazione per giorno ripetibile senza duplicati", n1 == n2 and n1 > 0 and tot["e"] == 15, str((n1, n2, dict(tot))))
        ok("riepilogo conta le sessioni (una per esito di Riprova)", sess == 2, str(sess))
        cols = [r["column_name"] for r in cn.execute("SELECT column_name FROM information_schema.columns WHERE table_name IN ('uso_eventi','uso_giorno')").fetchall()]
        ok("nessuna colonna per contenuti (testo, messaggio, email, nome)", not any(k in " ".join(cols) for k in ("testo", "messaggio", "email", "nome", "contenuto")), " ".join(cols))
        sql("UPDATE uso_eventi SET creato_il = NOW() - INTERVAL '130 days' WHERE id = (SELECT min(id) FROM uso_eventi)")
        txt = uso_ux.riepilogo(cn, 14)
        ok("l'Osservatore riceve le misure dettagliate", "MISURE DETTAGLIATE" in txt and "menu-agenti" in txt and "Riprova" in txt, txt[-400:])
        ok("il testo per l'Osservatore non contiene contenuti", "rossi" not in txt.lower() and "@" not in txt)
print("TOTALE", sum(ris), "/", len(ris))
