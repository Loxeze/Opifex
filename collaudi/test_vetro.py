import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import costi
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
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    ok("senza accesso: 401", c.get("/account/preferenze").status_code == 401)
    ok("all'inizio nessuna preferenza", c.get("/account/preferenze", headers=H).json() == {})
    for chiave, valore in [("stile", "classico"), ("sfondo", "oceano"), ("vetro", 0.5)]:
        r = c.put(f"/account/preferenze/{chiave}", headers=H, json={"valore": valore})
        ok(f"salva {chiave}", r.status_code == 200 and r.json()["valore"] == valore, r.text)
    p = c.get("/account/preferenze", headers=H).json()
    ok("le preferenze tornano indietro", p["stile"] == "classico" and p["sfondo"] == "oceano" and p["vetro"] == 0.5, str(p))
    ok("ogni utente ha le sue", c.get("/account/preferenze", headers=HA).json() == {})
    c.put("/account/preferenze/stile", headers=HA, json={"valore": "vetro"})
    ok("quelle di Lorenzo non cambiano", c.get("/account/preferenze", headers=H).json()["stile"] == "classico")
    ok("si riscrive senza duplicare", c.put("/account/preferenze/vetro", headers=H, json={"valore": 0.35}).status_code == 200 and sql("SELECT count(*) FROM preferenze_utente WHERE chiave='vetro'")[0][0] == 1)
    for nome, chiave, valore in [("stile sconosciuto", "stile", "neon"), ("sfondo sconosciuto", "sfondo", "<script>"), ("densita' troppo bassa", "vetro", 0.1), ("densita' troppo alta", "vetro", 0.9), ("densita' testuale", "vetro", "0.5"), ("densita' booleana", "vetro", True)]:
        ok(nome + ": 422", c.put(f"/account/preferenze/{chiave}", headers=H, json={"valore": valore}).status_code == 422)
    ok("chiave sconosciuta: 404", c.put("/account/preferenze/qualsiasi", headers=H, json={"valore": 1}).status_code == 404)
    ok("azzera una preferenza", c.delete("/account/preferenze/sfondo", headers=H).status_code == 200 and "sfondo" not in c.get("/account/preferenze", headers=H).json())
    ok("le preferenze della vecchia Plancia non esistono piu'", c.put("/account/preferenze/plancia_layout", headers=H, json={"valore": {"aurora": [0, 0, 300, 300, 1, 0]}}).status_code == 404)
    ok("azzera chiave sconosciuta: 404", c.delete("/account/preferenze/x", headers=H).status_code == 404)
    # costi senza chiamare i fornitori
    chiamate = []
    costi.dai_fornitori = lambda conn, g=14: chiamate.append(g) or {}
    r = c.get("/gestione/costi?giorni=7&fornitori=false", headers=H)
    ok("costi leggeri: nessuna chiamata ai fornitori", r.status_code == 200 and not chiamate and "stima" in r.json(), r.text[:150])
    c.get("/gestione/costi?giorni=7", headers=H)
    ok("costi completi: chiama i fornitori", chiamate == [7])
    ok("preferenze: elimina l'utente, spariscono", (sql("DELETE FROM utenti WHERE email='anna@p.it'"), sql("SELECT count(*) FROM preferenze_utente WHERE utente_id NOT IN (SELECT id FROM utenti)")[0][0])[1] == 0)
print("TOTALE", sum(ris), "/", len(ris))
sys.exit(0 if all(ris) else 1)
