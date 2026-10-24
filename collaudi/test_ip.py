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
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(DSN, autocommit=True) as k:
    k.execute("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
with TestClient(app) as c:
    ok("login corretto prima", c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).status_code == 200)
    codici = [c.post("/login", json={"email": f"x{i}@p.it", "password": "sbagliata"}).status_code for i in range(31)]
    ok("30 errori con email diverse dallo stesso indirizzo: i primi sono 401", codici[:30].count(401) == 30, str(codici))
    r = c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"})
    ok("poi l'indirizzo e' bloccato anche con credenziali giuste", r.status_code in (423, 429), str(r.status_code) + r.text[:80])
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
