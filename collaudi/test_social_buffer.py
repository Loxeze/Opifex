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
from app import buffer, strumenti_social
from app.sicurezza import cifra_password
from app.db import connessione
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
inviati = []
def finto(conn, query):
    if "organizations" in query: return {"account": {"organizations": [{"id": "ORG1", "name": "Lorenzo"}]}}
    if "channels(" in query: return {"channels": [{"id": "CH1", "name": "lorenzo.zeppa", "service": "instagram"}, {"id": "CH2", "name": "Lorenzo Zeppa", "service": "facebook"}]}
    if "createPost" in query:
        inviati.append(query); return {"createPost": {"post": {"id": "BP" + str(len(inviati))}}}
    return {}
buffer._gql = finto
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    ok("Buffer non collegato all'inizio", c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False)
    ok("solo il titolare collega Buffer", c.put("/gestione/social/buffer", headers=HA, json={"chiave": "x" * 20}).status_code == 403)
    r = c.put("/gestione/social/buffer", headers=H, json={"chiave": "chiave-di-prova-buffer"})
    ok("collegamento con chiave", r.status_code == 200 and len(r.json()["canali"]) == 2, r.text)
    ok("la chiave e' cifrata e mai restituita", "chiave-di-prova" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='buffer_chiave_cifrata'")[0][0] and "chiave-di-prova" not in c.get("/gestione/social/buffer", headers=H).text)
    ok("i canali Buffer compaiono tra i canali assegnabili", {x["id"] for x in c.get("/gestione/social/canali", headers=H).json()["canali"]} >= {"CH1", "CH2"})
    # post preparato da un agente e approvato
    ag = sql("SELECT id FROM agenti WHERE nome='Sofia'")[0][0]
    with connessione() as conn:
        g = strumenti_social.gestore(conn, ag)
        esito = g("social_prepara_post", {"canale_id": "CH1", "testo": "Ciao dal castello!"})
    ok("l'agente prepara un post per un canale Buffer", "preparato" in esito and sql("SELECT stato FROM post_social WHERE canale_id='CH1'")[0][0] == "da_approvare", esito)
    pid = sql("SELECT id FROM post_social WHERE canale_id='CH1'")[0][0]
    ok("non parte prima dell'approvazione", not inviati)
    r = c.post(f"/gestione/social/post/{pid}/decisione", headers=H, json={"azione": "approva"})
    ok("approvato: parte verso Buffer", r.status_code == 200 and r.json()["stato"] == "inviato" and len(inviati) == 1, r.text)
    ok("lo stato e l'id Buffer sono registrati", sql("SELECT stato, buffer_post_id FROM post_social WHERE id=%s", (pid,))[0] == ("inviato", "BP1"))
    # scrivi e pubblica da qui
    r = c.post("/gestione/social/buffer/post", headers=H, json={"canale_id": "CH2", "testo": "Post dalla pagina Social"})
    ok("pubblica dalla pagina su un canale Buffer", r.status_code == 201 and len(inviati) == 2, r.text)
    ok("canale inesistente: 404", c.post("/gestione/social/buffer/post", headers=H, json={"canale_id": "XX", "testo": "a"}).status_code == 404)
    ok("orario passato: 422", c.post("/gestione/social/buffer/post", headers=H, json={"canale_id": "CH2", "testo": "a", "programmato_il": "2020-01-01T10:00:00+00:00"}).status_code == 422)
    ok("media non https: 409/422", c.post("/gestione/social/buffer/post", headers=H, json={"canale_id": "CH2", "testo": "a", "media": [{"tipo": "image", "url": "http://x/y.jpg"}]}).status_code in (409, 422))
    ok("Anna non pubblica", c.post("/gestione/social/buffer/post", headers=HA, json={"canale_id": "CH2", "testo": "a"}).status_code == 403)
    ok("i canali diretti restano in elenco (nessun conflitto)", c.get("/gestione/social-nativo/stato", headers=H).status_code == 200)
    ok("scollega Buffer", c.delete("/gestione/social/buffer", headers=H).status_code == 200 and c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False)
    ok("le migrazioni non cancellano piu' la chiave", "DELETE FROM impostazioni_sistema" not in open("sql/24_zz_social_estesi.sql").read())
print("TOTALE", sum(ris), "/", len(ris)); sys.exit(0 if all(ris) else 1)
