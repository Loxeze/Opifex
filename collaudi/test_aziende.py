import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ID = {n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0] for n in ["Scout", "Marco", "Aurora", "Leo", "Giulia", "Radar"]}
    ok("collaboratore: 403 su aziende", c.get("/gestione/aziende", headers=HS).status_code == 403)
    r = c.post("/gestione/aziende", headers=H, json={"nome": "Logos", "territorio": "Liguria", "colore": "#34d399"}); ok("crea azienda", r.status_code == 201, r.text)
    a1 = r.json()["id"]
    a2 = c.post("/gestione/aziende", headers=H, json={"nome": "Renovatio", "colore": "#fbbf24"}).json()["id"]
    ok("nome duplicato -> 409", c.post("/gestione/aziende", headers=H, json={"nome": "logos"}).status_code == 409)
    ok("colore non valido -> 422", c.post("/gestione/aziende", headers=H, json={"nome": "X", "colore": "rosso"}).status_code == 422)
    ok("modifica azienda", c.put(f"/gestione/aziende/{a1}", headers=H, json={"nome": "Logos srl", "colore": "#34d399", "profilo": "Servizi digitali"}).status_code == 200)
    ok("azienda inesistente -> 404", c.put("/gestione/aziende/9999", headers=H, json={"nome": "Z"}).status_code == 404)
    ok("assegna Scout a due aziende", c.put(f"/gestione/agenti/{ID['Scout']}/aziende", headers=H, json={"aziende": [a1, a2]}).status_code == 200)
    ok("azienda inesistente nell'assegnazione -> 422", c.put(f"/gestione/agenti/{ID['Scout']}/aziende", headers=H, json={"aziende": [9999]}).status_code == 422)
    ag = {x["nome"]: x for x in c.get("/gestione/agenti", headers=H).json()}
    ok("l'elenco agenti mostra le aziende", ag["Scout"]["aziende"] == [a1, a2] and ag["Leo"]["aziende"] == [])
    # dipartimenti
    r = c.post("/gestione/divisioni", headers=H, json={"nome": "Eventi", "descrizione": "Mostre ed eventi", "azienda_id": a2, "colore": "#f87171"}); ok("crea dipartimento", r.status_code == 201, r.text)
    did = r.json()["id"]
    ok("dipartimento duplicato -> 409", c.post("/gestione/divisioni", headers=H, json={"nome": "eventi"}).status_code == 409)
    ok("azienda inesistente nel dipartimento -> 422", c.post("/gestione/divisioni", headers=H, json={"nome": "Y", "azienda_id": 9999}).status_code == 422)
    ok("rinomina dipartimento", c.put(f"/gestione/divisioni/{did}", headers=H, json={"nome": "Eventi e mostre", "azienda_id": a2, "colore": "#f87171"}).status_code == 200)
    ok("sposto Leo nel nuovo dipartimento con nuovo superiore",
       c.put(f"/gestione/agenti/{ID['Leo']}", headers=H, json={"divisione_id": did, "superiore_id": ID["Aurora"]}).status_code == 200)
    ok("dipartimento con agenti non eliminabile -> 409", c.delete(f"/gestione/divisioni/{did}", headers=H).status_code == 409)
    ok("giro chiuso nella gerarchia -> 422 (Aurora sotto Leo)", c.put(f"/gestione/agenti/{ID['Aurora']}", headers=H, json={"superiore_id": ID["Leo"]}).status_code == 422)
    ok("giro chiuso indiretto (Marco sotto Scout) -> 422", c.put(f"/gestione/agenti/{ID['Marco']}", headers=H, json={"superiore_id": ID["Scout"]}).status_code == 422)
    ok("sposto Leo altrove e poi il dipartimento si elimina",
       c.put(f"/gestione/agenti/{ID['Leo']}", headers=H, json={"divisione_id": sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]}).status_code == 200
       and c.delete(f"/gestione/divisioni/{did}", headers=H).status_code == 200)
    sql("INSERT INTO compiti (titolo, azienda_id) VALUES ('t', %s)", (a1,))
    ok("azienda con compiti non eliminabile -> 409", c.delete(f"/gestione/aziende/{a1}", headers=H).status_code == 409)
    ok("azienda libera eliminabile e assegnazioni sparite", c.delete(f"/gestione/aziende/{a2}", headers=H).status_code == 200
       and sql("SELECT count(*) FROM agenti_aziende WHERE azienda_id=%s", (a2,))[0][0] == 0)
    # una seconda piramide indipendente
    nuova = c.post("/gestione/divisioni", headers=H, json={"nome": "Secondo gruppo", "azienda_id": a1}).json()["id"]
    r = c.post("/gestione/agenti", headers=H, json={"nome": "Capo2", "ruolo": "Responsabile", "divisione_id": nuova, "livello": "manager", "modello": "claude-haiku-5-5", "istruzioni": "x"})
    ok("nuova piramide: capo senza superiore", r.status_code == 201, r.text)
    cap = r.json()["id"]
    r = c.post("/gestione/agenti", headers=H, json={"nome": "Operaio2", "ruolo": "Operativo", "divisione_id": nuova, "superiore_id": cap, "modello": "claude-haiku-5-5", "istruzioni": "x"})
    ok("e un suo operativo", r.status_code == 201)
    c.put(f"/gestione/agenti/{cap}/aziende", headers=H, json={"aziende": [a1]})
    o = c.get("/gestione/organigramma", headers=H).json()
    ok("organigramma: aziende, dipartimenti e agenti", len(o["agenti"]) >= 20 and any(d["nome"] == "Secondo gruppo" for d in o["divisioni"]) and o["aziende"][0]["nome"] == "Logos srl")
    by = {x["nome"]: x for x in o["agenti"]}
    ok("la nuova piramide ha radice senza superiore", by["Capo2"]["superiore_id"] is None and by["Operaio2"]["superiore_id"] == cap and by["Capo2"]["aziende"] == [a1])
    sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,'dato',TRUE)", (ID["Radar"],))
    sql("UPDATE agenti SET budget_token_mensile=1000 WHERE id=%s", (ID["Scout"],))
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'m',900,0,0)", (ID["Scout"],))
    o = {x["nome"]: x for x in c.get("/gestione/organigramma", headers=H).json()["agenti"]}
    ok("stato reale: bloccante=difficolta', tetto 90%=pressione, altri sereno",
       o["Radar"]["stato"] == "difficolta" and o["Scout"]["stato"] == "pressione" and o["Scout"]["carico"] == 90 and o["Giulia"]["stato"] == "sereno")
    ok("opzioni include le aziende", "aziende" in c.get("/gestione/opzioni", headers=H).json())
    # --- impulsi (raggi di luce)
    r0 = c.get("/gestione/organigramma/impulsi", headers=H).json()
    ok("impulsi: senza istante restituisce solo l'ora del server", r0["impulsi"] == [] and r0["adesso"])
    ok("collaboratore: 403 sugli impulsi", c.get("/gestione/organigramma/impulsi", headers=HS).status_code == 403)
    conv = sql("INSERT INTO conversazioni (titolo) VALUES ('t') RETURNING id")[0][0]
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'ciao')", (conv, ID["Marco"], ID["Scout"]))
    sql("INSERT INTO richieste_informazioni (agente_id, domanda) VALUES (%s,'dato')", (ID["Radar"],))
    sql("INSERT INTO registro_azioni (agente_id, azione) VALUES (%s,'risposta_generata')", (ID["Giulia"],))
    from urllib.parse import quote
    r1 = c.get("/gestione/organigramma/impulsi?dopo=" + quote(r0["adesso"]), headers=H).json()
    tipi = {(x["tipo"], x["da"], x["a"]) for x in r1["impulsi"]}
    ok("impulsi: messaggio tra agenti, richiesta verso il centro, chat dal centro",
       tipi == {("messaggio", ID["Marco"], ID["Scout"]), ("richiesta", ID["Radar"], 0), ("chat", 0, ID["Giulia"])}, str(tipi))
    r2 = c.get("/gestione/organigramma/impulsi?dopo=" + quote(r1["adesso"]), headers=H).json()
    ok("impulsi: nessuna ripetizione al giro dopo", r2["impulsi"] == [])
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
