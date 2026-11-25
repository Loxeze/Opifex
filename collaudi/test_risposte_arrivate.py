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
from app import scuola, crm, cassaforte, posta_vaglio
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
LETTE = []
def finta_leggi(conn, origine, cid, msg_id):
    LETTE.append(msg_id)
    return ("Da: Paola <paola@belvedere.it>\nOggetto: Re: Un video\n\nBuongiorno, molto interessante! Possiamo sentirci giovedì?\n\n"
            "Il giorno lun 24 nov 2026 Lorenzo Zeppa ha scritto:\n> Gentile Paola, ...")
posta_vaglio.leggi = finta_leggi
PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    A = sql("INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine', 'gmail:1', 'in_corso') RETURNING id")[0][0]
    v = sql("INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, categoria) VALUES ('gmail',1,'m77','paola@belvedere.it','Re: Un video','normale') RETURNING id")[0][0]
    d = sql("""INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, inviata_il, risposta_il, risposta_oggetto, risposta_vaglio_id, risposta_sintesi)
               VALUES (%s,'h1','interessato',NOW() - INTERVAL '1 day',NOW(),'Re: Un video',%s,'vuole sentirsi giovedì') RETURNING id""", (A, v))[0][0]
    r = c.get(f"/gestione/campagne/destinatari/{d}/risposta-ricevuta", headers=H).json()
    ok("si legge l'email arrivata, senza la parte citata", "Possiamo sentirci giovedì" in r["testo"] and "Gentile Paola" not in r["testo"] and LETTE == ["m77"], r)
    d2 = sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, risposta_il) VALUES (%s,'h2','risposto',NOW()) RETURNING id", (A,))[0][0]
    r = c.get(f"/gestione/campagne/destinatari/{d2}/risposta-ricevuta", headers=H).json()
    ok("senza l'email nella posta: lo dice", r["testo"] == "" and r["avviso"])
    ok("solo il titolare", c.get(f"/gestione/campagne/destinatari/{d}/risposta-ricevuta").status_code in (401, 403))
    js = open("app/static/campagne.js").read()
    ok("interfaccia: sezione «Risposte arrivate» separata dalle nostre email", "📥 Risposte arrivate" in js and "📤 Le nostre email" in js and "_letteraArrivataCp" in js)
print(f"TOTALE: {sum(ris)}/{len(ris)}")
