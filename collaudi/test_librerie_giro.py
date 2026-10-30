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
from app import dipendenze
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
import tempfile
from app.db import apri_pool
apri_pool()
from pathlib import Path
d = Path(tempfile.mkdtemp()); rq = d / "requirements.txt"
rq.write_text("httpx==0.28.1\nlibreria-che-non-esiste-xyz==1.2.3\nnumpy==2.5.4  # presente\n")
ok("riconosce le librerie mancanti", dipendenze.mancanti(rq) == [("libreria-che-non-esiste-xyz", "1.2.3")], str(dipendenze.mancanti(rq)))
chiamate = []
r = dipendenze.assicura_librerie(rq, installa=lambda el: chiamate.append(el) or "ok")
ok("installa solo cio' che manca, con la versione indicata", chiamate == [["libreria-che-non-esiste-xyz==1.2.3"]] and r["esito"] == "ok")
ok("avvisa Lorenzo", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Ho installato le librerie mancanti%'")[0][0] == 1)
r = dipendenze.assicura_librerie(rq, installa=lambda el: "errore di rete")
ok("se non riesce lo dice", r["esito"] == "errore di rete" and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Mancano delle librerie%'")[0][0] == 1)
rq.write_text("httpx==0.28.1\n")
ok("niente da fare: nessuna installazione", dipendenze.assicura_librerie(rq, installa=lambda el: 1 / 0) == {"mancanti": [], "esito": "ok"})
ok("il requirements reale e' completo nell'ambiente di prova", dipendenze.mancanti() == [], str(dipendenze.mancanti()))
src = open("app/static/controlli.js").read()
ok("Giro di aggiornamento: microfono sulle risposte e sui fatti", src.count("bottoneMic(") >= 2 and "Voce.inAscolto" in src[src.index("function vistaGiro"):src.index("function vistaContenuti")])
print("TOTALE", sum(ris), "/", len(ris))
