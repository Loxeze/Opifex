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
from app import documenti_blocco
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
import io, zipfile, os as _os
documenti_blocco.SINCRONO = True
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    # 6 file da ~100 MB di testo non compressibile-ish (totale ~600 MB > vecchio tetto 400 MB)
    blocco = (b"riga di testo del montaggio numero 12345\n" * 2_400_000)[:99_000_000]
    files = [("file", (f"grande{i}.txt", io.BytesIO(blocco[:98_000_000 - i * 1000]), "text/plain")) for i in range(6)]
    r = c.post("/gestione/documenti-blocco", headers=H, files=files, data={"fascia_dati": "interno"})
    ok("oltre 400 MB in un solo caricamento: accettato", r.status_code == 202, r.text[:200])
    d = sql("SELECT stato, totale, caricati, saltati FROM caricamenti_blocco ORDER BY id DESC LIMIT 1")[0]
    ok("tutti i file elaborati", d[0] == "concluso" and d[1] == 6 and d[2] + d[3] == 6, str(d))
    ok("cartella temporanea ripulita", not [x for x in _os.listdir(__import__("tempfile").gettempdir()) if x.startswith("opifex-blocco-")])
    # zip con molti file
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(30): z.writestr(f"cartella/f{i}.txt", f"documento numero {i} sul montaggio\n" * 50)
    r = c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("cartella.zip", zb.getvalue(), "application/zip"))], data={"fascia_dati": "interno"})
    d = sql("SELECT totale, caricati FROM caricamenti_blocco ORDER BY id DESC LIMIT 1")[0]
    ok("zip da disco", r.status_code == 202 and d == (30, 30), str(d))
    r = c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("vuoto.xyz", b"a", "text/plain"))], data={"fascia_dati": "interno"})
    ok("formato non supportato segnalato, non bloccante", r.status_code == 202 and sql("SELECT saltati FROM caricamenti_blocco ORDER BY id DESC LIMIT 1")[0][0] == 1)
print("TOTALE", sum(ris), "/", len(ris))
