import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from app.main import app
ris = []
def ok(n, c): ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n)
with TestClient(app) as c:
    r = c.get("/privacy")
    ok("pagina privacy pubblica, senza accesso", r.status_code == 200 and "Informativa sulla privacy" in r.text and "Limited Use" in r.text and "text/html" in r.headers["content-type"])
print(f"TOTALE: {sum(ris)}/{len(ris)}")
