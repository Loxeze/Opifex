import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import esecuzione
from app.fornitori import Risposta
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password

DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None

sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))
chiamate = []
def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    chiamate.append(dict(modello=modello, istruzioni=istruzioni, max_token=max_token, web=web))
    return Risposta("ok", 100, 50)
esecuzione.chiama_modello = finto

sql("UPDATE agenti SET dialoghi_attivi = FALSE")  # questi collaudi provano il percorso semplice; i dialoghi hanno i loro

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ok("/ porta all'interfaccia", c.get("/", follow_redirects=False).headers["location"] == "/app/")
    p = c.get("/app/")
    ok("pagina interfaccia servita", p.status_code == 200 and "Opifex" in p.text)
    ok("script e stile serviti", c.get("/app/app.js").status_code == 200 and c.get("/app/stile.css").status_code == 200)
    ok("gestione senza token -> 401", c.get("/gestione/agenti").status_code == 401)
    ok("gestione per collaboratore -> 403", c.get("/gestione/agenti", headers=HS).status_code == 403)
    ag = c.get("/gestione/agenti", headers=H).json()
    ok("gestione elenca 18 agenti con i nuovi campi", len(ag) == 18 and "max_token_risposta" in ag[0] and "token_mese" in ag[0])
    scout = next(a for a in ag if a["nome"] == "Scout")
    ok("Scout ha accesso al web di default", scout["accesso_web"] is True)
    op = c.get("/gestione/opzioni", headers=H).json()
    ok("opzioni: 5 modelli, 4 divisioni, 3 fornitori", (len(op["modelli"]), len(op["divisioni"]), len(op["fornitori"])) == (5, 4, 3))

    nuovo = dict(nome="Canvas", ruolo="Grafico", divisione_id=2, superiore_id=7, livello="operativo", modello="claude-haiku-5-5",
                 istruzioni="Prepari bozze grafiche.", fascia_dati_max="pubblico", max_token_risposta=700, budget_token_mensile=500,
                 accesso_web=True, siti_consentiti=["https://www.Esempio.it/pagina", "esempio.it", "bandi.regione.it", "non un sito"], max_ricerche=2)
    r = c.post("/gestione/agenti", headers=H, json=nuovo)
    ok("crea agente dall'interfaccia -> 201", r.status_code == 201, r.text)
    aid = r.json()["id"]
    riga = sql("SELECT siti_consentiti, tipo, max_token_risposta FROM agenti WHERE id=%s", (aid,))[0]
    ok("siti ripuliti (solo domini, senza doppioni)", riga[0] == ["www.esempio.it", "esempio.it", "bandi.regione.it"], str(riga))
    ok("agente in divisione e' di tipo 'divisione'", riga[1] == "divisione")
    ok("nome doppio -> 409", c.post("/gestione/agenti", headers=H, json=nuovo | {"nome": "canvas"}).status_code == 409)
    ok("modello inesistente -> 422", c.post("/gestione/agenti", headers=H, json=nuovo | {"nome": "X1", "modello": "boh"}).status_code == 422)
    ok("fascia non valida -> 422", c.post("/gestione/agenti", headers=H, json=nuovo | {"nome": "X2", "fascia_dati_max": "segreto"}).status_code == 422)
    ok("token fuori scala -> 422", c.post("/gestione/agenti", headers=H, json=nuovo | {"nome": "X3", "max_token_risposta": 999999}).status_code == 422)

    c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"})
    ok("la chat usa tetto token e web dell'agente", chiamate[-1]["max_token"] == 700 and chiamate[-1]["web"]["max_ricerche"] == 2 and "bandi.regione.it" in chiamate[-1]["web"]["siti"], str(chiamate[-1]))
    r = c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "ancora", "fascia_dati": "pubblico"})
    ok("tetto mensile non ancora superato (150 < 500)", r.status_code == 200, r.text)
    for _ in range(3): c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    r = c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    ok("budget mensile esaurito -> 409", r.status_code == 409 and "Budget" in r.json()["detail"], r.text)

    r = c.put(f"/gestione/agenti/{aid}", headers=H, json={"budget_token_mensile": None, "accesso_web": False, "istruzioni": "Nuove istruzioni."})
    ok("modifica parziale -> 200", r.status_code == 200, r.text)
    riga = sql("SELECT budget_token_mensile, accesso_web, istruzioni, nome FROM agenti WHERE id=%s", (aid,))[0]
    ok("modifica applicata, resto invariato", riga == (None, False, "Nuove istruzioni.", "Canvas"), str(riga))
    r = c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    ok("senza limite e senza web l'agente riprende", r.status_code == 200 and chiamate[-1]["web"] is None and chiamate[-1]["istruzioni"].startswith("Nuove istruzioni.") and "NON INVENTARE MAI" in chiamate[-1]["istruzioni"])
    ok("agente non puo' rispondere a se stesso", c.put(f"/gestione/agenti/{aid}", headers=H, json={"superiore_id": aid}).status_code == 422)
    ok("agente inesistente -> 404", c.put("/gestione/agenti/9999", headers=H, json={"attivo": False}).status_code == 404)
    ok("modifica vuota -> 422", c.put(f"/gestione/agenti/{aid}", headers=H, json={}).status_code == 422)
    c.put(f"/gestione/agenti/{aid}", headers=H, json={"divisione_id": None})
    ok("senza divisione diventa agente di sistema", sql("SELECT tipo FROM agenti WHERE id=%s", (aid,))[0][0] == "sistema")
    c.put(f"/gestione/agenti/{aid}", headers=H, json={"attivo": False})
    ok("spegnere un agente lo ferma (409)", c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"}).status_code == 409)
    reg = sql("SELECT azione, utente_id FROM registro_azioni WHERE agente_id=%s AND azione LIKE 'agente_%%'", (aid,))
    ok("creazioni e modifiche registrate con l'autore", len(reg) >= 4 and all(r[1] is not None for r in reg), str(reg))

    r = c.post("/gestione/connessioni", headers=H, json={"nome": "Canva", "tipo": "app", "descrizione": "Grafica"})
    ok("crea connessione", r.status_code == 201, r.text)
    cid = r.json()["id"]
    ok("connessione doppia -> 409", c.post("/gestione/connessioni", headers=H, json={"nome": "canva"}).status_code == 409)
    ok("tipo connessione non valido -> 422", c.post("/gestione/connessioni", headers=H, json={"nome": "Z", "tipo": "x"}).status_code == 422)
    ok("collega connessione ad agente", c.put(f"/gestione/agenti/{aid}", headers=H, json={"connessioni": [cid]}).status_code == 200)
    ok("collegamento visibile in elenco", c.get("/gestione/connessioni", headers=H).json()[0]["agenti"] == [aid])
    ok("connessione inesistente -> 422", c.put(f"/gestione/agenti/{aid}", headers=H, json={"connessioni": [999]}).status_code == 422)
    ok("modifica connessione", c.put(f"/gestione/connessioni/{cid}", headers=H, json={"nome": "Canva", "tipo": "app", "stato": "attiva"}).status_code == 200)
    ok("elimina connessione e legami", c.delete(f"/gestione/connessioni/{cid}", headers=H).status_code == 200 and sql("SELECT count(*) FROM agenti_connessioni")[0][0] == 0)

f = ris.count(False); print(f"\nTOTALE: {len(ris)-f}/{len(ris)}"); sys.exit(1 if f else 0)
