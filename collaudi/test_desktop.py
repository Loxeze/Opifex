import os, sys, hashlib, json, subprocess, tempfile, time, threading
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from app.main import app
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with TestClient(app) as c:
    m = c.get("/desktop/manifesto")
    ok("manifesto pubblico", m.status_code == 200, m.text[:100])
    m = m.json()
    ind = c.get("/desktop/indice.py"); exe = c.get("/desktop/IndiceArchivio.exe")
    ok("indice.py servito e impronta corretta", ind.status_code == 200 and hashlib.sha256(ind.content).hexdigest() == m["indice"]["sha256"])
    ok("eseguibile servito, e' un programma Windows, impronta corretta", exe.status_code == 200 and exe.content[:2] == b"MZ" and hashlib.sha256(exe.content).hexdigest() == m["lanciatore"]["sha256"])
    ok("versione di Opifex nel manifesto", m["opifex"] and m["lanciatore"]["versione"] >= 2)
    ok("elenco pacchetti con revisione", m["requisiti"]["rev"] >= 1 and "numpy" in m["requisiti"]["pacchetti"])
    ok("l'eseguibile incorpora lo stesso indice.py del server", ind.content in exe.content)
    ok("l'eseguibile sa aggiornarsi dal manifesto", b"/desktop/manifesto" in exe.content and b"--finestra" in exe.content)
    ok("il manifesto non espone percorsi o segreti", not any(k in json.dumps(m).lower() for k in ("password", "token", "/home", "secret")))
    ok("pagina App: link di scarico", "/desktop/IndiceArchivio.exe" in open("app/static/app_mobile.js").read())
print("TOTALE", sum(ris), "/", len(ris))
sys.exit(0 if all(ris) else 1)
