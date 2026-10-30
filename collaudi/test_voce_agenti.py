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
from app import telegram, voce_elevenlabs as ve
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('C','c@p.it',%s,'collaboratore')", (cifra_password("PasswordLunga!2026"),))
class R:
    def __init__(s, code=200, content=b"", dati=None): s.status_code = code; s.content = content; s._d = dati or {}
    def json(s): return s._d
chiamate = []
def finto_post(url, **k):
    chiamate.append((url, k)); return R(content=b"ID3mp3finto")
ve.httpx.post = finto_post
ve.httpx.get = lambda url, **k: R(dati={"voices": [{"voice_id": "v1", "name": "Aurora IT"}]})
KEY = "sk_" + "a" * 30
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    Hc = {"Authorization": "Bearer " + accedi(c, "c@p.it", "PasswordLunga!2026")}
    ag = sql("SELECT id FROM agenti WHERE livello NOT IN ('manager','referente') AND NOT COALESCE(sentinella,FALSE) ORDER BY id LIMIT 1")
    if not ag:
        sql("INSERT INTO agenti (nome, ruolo, livello) VALUES ('Operaio','Prova','operativo')")
        ag = sql("SELECT id FROM agenti WHERE nome='Operaio'")
    aid = ag[0][0]
    ok("collaboratore non vede le voci", c.get("/gestione/voci-agenti", headers=Hc).status_code == 403)
    d = c.get("/gestione/voci-agenti", headers=H).json()
    ok("senza chiave: elevenlabs falso e nessuna voce", d["elevenlabs"] is False and d["voci"] == [])
    c.put("/gestione/voce", headers=H, json={"chiave": KEY, "voce_id": "v1", "garanzie": True, "telegram_voce": False})
    d = c.get("/gestione/voci-agenti", headers=H).json()
    ok("con chiave: elenco voci", d["elevenlabs"] and d["voci"] == [{"id": "v1", "nome": "Aurora IT"}], str(d))
    ok("assegna voce a un agente NON manager", c.put(f"/gestione/voci-manager/{aid}", headers=H, json={"voce_id": "v1"}).status_code == 200)
    ok("la voce risulta nell'elenco", c.get("/gestione/voci-agenti", headers=H).json()["agenti"].get(str(aid)) == "v1")
    ok("agente inesistente: 404", c.put("/gestione/voci-manager/999999", headers=H, json={"voce_id": "v1"}).status_code == 404)
    chiamate.clear()
    r = c.post("/voce/leggi", headers=H, json={"testo": "Ciao", "agente_id": aid})
    ok("la lettura usa la voce dell'agente", r.status_code == 200 and chiamate and chiamate[0][0].endswith("/text-to-speech/v1"))
    ok("rimozione voce", c.put(f"/gestione/voci-manager/{aid}", headers=H, json={"voce_id": None}).status_code == 200
       and str(aid) not in c.get("/gestione/voci-agenti", headers=H).json()["agenti"])
js = open("app/static/agenti_carte.js").read(); ap = open("app/static/app.js").read(); ve_js = open("app/static/voce_el.js").read()
ok("riquadro agente ha il posto per la voce", "agente-voce-posto" in ap and "riempiVociAgenti(blocco)" in ap)
ok("la prova usa la voce dell'agente", "agenteId" in ve_js and "riempiVociAgenti" in js)
print("TOTALE", sum(ris), "/", len(ris))
