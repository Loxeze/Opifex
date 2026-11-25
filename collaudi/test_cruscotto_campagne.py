import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, crm, cassaforte
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": "PasswordLunga!2026", "codice": "codice-di-prova-2026"})
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", "PasswordLunga!2026")}
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine','pubblico') RETURNING id")[0][0]
    A = sql("INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine Toscana','gmail:1','in_corso') RETURNING id")[0][0]
    k1 = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato) VALUES (%s,'cantina',%s) RETURNING id", (li, cassaforte.cifra("Tenuta Belvedere")))[0][0]
    for i in range(6):
        sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, inviata_il) VALUES (%s,%s,'inviata',NOW() - INTERVAL '1 day')", (A, f"a{i}"))
    d1 = sql("""INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, inviata_il, risposta_il, risposta_sintesi) VALUES (%s,%s,'b1','interessato',NOW()-INTERVAL '2 days',NOW()-INTERVAL '1 hour','vuole sentirsi giovedì') RETURNING id""", (A, k1))[0][0]
    sql("INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, destinatario_id) VALUES ('gmail',1,'m','x@y.it','o','t','da_approvare',%s,'risposta',%s)", (A, d1))
    sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, inviata_il, risposta_il) VALUES (%s,'b2','non_interessato',NOW()-INTERVAL '3 days',NOW()-INTERVAL '1 day')", (A,))
    sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato) VALUES (%s,'c1','in_attesa')", (A,))
    d = c.get("/gestione/campagne/cruscotto", headers=H).json()
    ok("in attesa di risposta, risposte, tasso", d["in_attesa"] == 6 and d["risposte"] == 2 and d["partite"] == 8 and d["tasso"] == 25.0, d)
    ok("interessati, non interessati, da gestire", d["interessati"] == 1 and d["non_interessati"] == 1 and d["da_gestire"] == 1, d)
    ok("schede delle ultime risposte, la piu' recente prima, con ente e sintesi", d["ultime"][0]["chi"] == "Tenuta Belvedere" and d["ultime"][0]["da_gestire"] and d["ultime"][0]["sintesi"] and len(d["ultime"]) == 2)
    ok("imbuto e andamento di 14 giorni", d["imbuto"][0]["gradino"] == "Contatti" and len(d["giorni"]) == 14 and sum(x["partite"] for x in d["giorni"]) == 8, d["giorni"][-3:])
    ok("per campagna", d["campagne"][0]["nome"] == "Cantine Toscana" and d["campagne"][0]["in_attesa"] == 6)
    ok("solo il titolare", c.get("/gestione/campagne/cruscotto").status_code in (401, 403))
    ok("Plancia: riquadro campagne", "riquadroCampagnePlancia" in open("app/static/plancia.js").read())
print(f"TOTALE: {sum(ris)}/{len(ris)}")
