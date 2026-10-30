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
from app import cassaforte
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore') ON CONFLICT DO NOTHING", (cifra_password(PW),))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ag = [r[0] for r in sql("SELECT id FROM agenti ORDER BY id LIMIT 4")]
    conv = sql("INSERT INTO conversazioni (titolo) VALUES ('t') RETURNING id")[0][0]
    for da, a in ((ag[0], ag[1]), (ag[1], ag[0]), (ag[0], ag[1]), (ag[2], ag[3])):
        sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'x')", (conv, da, a))
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,NULL,'a Lorenzo')", (conv, ag[0]))
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'a se stesso')", (conv, ag[2], ag[2]))
    d = c.get("/gestione/organigramma", headers=H).json()["dialoghi"]
    coppie = {(x["a"], x["b"]): x["messaggi"] for x in d}
    ok("una sola linea per coppia, in qualunque direzione", coppie.get((min(ag[0], ag[1]), max(ag[0], ag[1]))) == 3, str(coppie))
    ok("anche una sola frase basta", coppie.get((min(ag[2], ag[3]), max(ag[2], ag[3]))) == 1)
    ok("niente linee con Lorenzo o con se stessi", len(coppie) == 2 and all(a != b for a, b in coppie))
    ok("Carla non vede l'organigramma", c.get("/gestione/organigramma", headers={"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}).status_code == 403)
src = open("app/static/organizzazione.js").read()
ok("il grafico disegna i legami di dialogo", "dati.dialoghi" in src and "layout.per.get(d.a)" in src)
ok("rotazione lenta e indipendente dai fotogrammi", "VELOCITA_ROT = 0.035" in src and "rotY += 0.003" not in src)
print("TOTALE", sum(ris), "/", len(ris))
