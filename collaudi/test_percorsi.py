import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import esecuzione, percorsi
from app.fornitori import Risposta, ErroreFornitore
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
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
sql("UPDATE fornitori_ai SET non_conservazione_attiva = TRUE, dpa_firmato = TRUE, fascia_dati_max = 'riservato'")
sql("UPDATE agenti SET fascia_dati_max = 'riservato'")
chiamate, guasto = [], {"si": False}
def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    chiamate.append(dict(istruzioni=istruzioni, messaggio=messaggio, max_token=max_token))
    if guasto["si"]: raise ErroreFornitore("servizio non disponibile")
    return Risposta("Output della fase.", 10, 5)
esecuzione.chiama_modello = finto
percorsi.SINCRONO = True
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
FASI = [{"titolo": "Proposte generali", "istruzioni": "Fai tre proposte diverse conoscendo l'azienda", "approvazione": True, "parere_superiore": True},
        {"titolo": "Sviluppo della proposta scelta", "istruzioni": "SEGRETO-FASE-DUE sviluppa in modo approfondito", "approvazione": True},
        {"titolo": "Progetto definitivo", "istruzioni": "SEGRETO-FASE-TRE scrivi il progetto", "approvazione": True}]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    scout, marco = ID("Scout"), ID("Marco")
    ok("senza fasi il percorso non parte (409)", c.post("/percorsi", headers=H, json={"agente_id": scout, "titolo": "x", "brief": "y"}).status_code == 409)
    r = c.put(f"/gestione/agenti/{scout}", headers=H, json={"fasi": FASI})
    ok("fasi salvate dal modulo agente", r.status_code == 200, r.text)
    ag = {a["nome"]: a for a in c.get("/gestione/agenti", headers=H).json()}
    ok("l'elenco agenti riporta le fasi in ordine", [f["titolo"] for f in ag["Scout"]["fasi"]] == [f["titolo"] for f in FASI] and ag["Marco"]["fasi"] == [])
    ok("piu' di 12 fasi -> 422", c.put(f"/gestione/agenti/{scout}", headers=H, json={"fasi": [{"titolo": f"f{i}"} for i in range(13)]}).status_code == 422)
    ok("fase senza titolo -> 422", c.put(f"/gestione/agenti/{scout}", headers=H, json={"fasi": [{"titolo": ""}]}).status_code == 422)
    ok("modificare altro non tocca le fasi", c.put(f"/gestione/agenti/{scout}", headers=H, json={"ruolo": "Cerca bandi"}).status_code == 200
       and sql("SELECT count(*) FROM fasi_agente WHERE agente_id=%s", (scout,))[0][0] == 3)
    chiamate.clear()
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("nella chat libera l'agente conosce le sue fasi", "FASI DI LAVORO" in chiamate[0]["istruzioni"] and "Proposte generali" in chiamate[0]["istruzioni"])
    ok("opzioni: solo agenti con fasi", [a["nome"] for a in c.get("/percorsi/opzioni", headers=H).json()["agenti"]] == ["Scout"])

    # --- fase 1
    chiamate.clear()
    r = c.post("/percorsi", headers=H, json={"agente_id": scout, "titolo": "Bando Borghi", "brief": "Candidare Renovatio al bando Borghi", "fascia_dati": "interno"})
    pid = r.json()["id"]
    p = c.get(f"/percorsi/{pid}", headers=H).json()
    ok("dopo la fase 1 il percorso attende la decisione", r.status_code == 201 and p["stato"] == "in_attesa" and p["fase_corrente"] == 1 and len(p["esiti"]) == 1, str(p["stato"]))
    m1 = chiamate[0]["messaggio"]
    ok("la fase 1 riceve solo le proprie istruzioni (non quelle delle fasi successive)", "SEI ALLA FASE 1 DI 3" in m1 and "tre proposte diverse" in m1 and "SEGRETO-FASE-DUE" not in m1 and "SEGRETO-FASE-TRE" not in m1)
    ok("la fase 1 vede l'elenco completo e il lavoro richiesto", "Progetto definitivo" in m1 and "Candidare Renovatio" in m1)
    ok("i token di una fase sono almeno 4000", chiamate[0]["max_token"] >= 4000)
    ok("il superiore ha scritto il parere", p["esiti"][0]["parere_superiore"] == "Output della fase." and any("Valuta" in x["messaggio"] or "parere" in x["messaggio"] for x in chiamate[1:]))
    ok("la notifica e' accodata", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%Bando Borghi%'")[0][0] == 1)
    # --- decisioni
    ok("modifiche senza nota -> 422", c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "modifiche"}).status_code == 422)
    chiamate.clear()
    ok("chiedo modifiche", c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "modifiche", "nota": "Aggiungi una proposta sul turismo"}).status_code == 200)
    ok("la fase 1 viene rifatta con le mie note e la versione precedente", "respinta" in chiamate[0]["messaggio"] and "proposta sul turismo" in chiamate[0]["messaggio"] and "SEI ALLA FASE 1" in chiamate[0]["messaggio"])
    p = c.get(f"/percorsi/{pid}", headers=H).json()
    ok("tentativo 2 registrato, tentativo 1 marcato 'modifiche'", [e["tentativo"] for e in p["esiti"] if e["posizione"] == 1] == [1, 2] and p["esiti"][0]["decisione"] == "modifiche")
    chiamate.clear()
    ok("approvo scegliendo la proposta 2", c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "approva", "nota": "Sviluppa la proposta 2"}).status_code == 200)
    m2 = chiamate[0]["messaggio"]
    ok("la fase 2 parte solo dopo l'approvazione e riceve la scelta", "SEI ALLA FASE 2 DI 3" in m2 and "SEGRETO-FASE-DUE" in m2 and "SEGRETO-FASE-TRE" not in m2
       and "Sviluppa la proposta 2" in m2 and "APPROVATO della fase 1" in m2)
    # --- fine
    chiamate.clear()
    c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "approva", "nota": "ok"})
    ok("fase 3", "SEI ALLA FASE 3 DI 3" in chiamate[0]["messaggio"] and "SEGRETO-FASE-TRE" in chiamate[0]["messaggio"])
    r = c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "approva", "nota": "Perfetto"})
    p = c.get(f"/percorsi/{pid}", headers=H).json()
    ok("approvata l'ultima fase il percorso e' completato", r.json()["stato"] == "completato" and p["stato"] == "completato")
    ok("un percorso completato non accetta altre decisioni (409)", c.post(f"/percorsi/{pid}/decisione", headers=H, json={"azione": "approva"}).status_code == 409)

    # --- fasi senza approvazione: proseguono da sole
    sql("DELETE FROM fasi_agente WHERE agente_id=%s", (scout,))
    c.put(f"/gestione/agenti/{scout}", headers=H, json={"fasi": [{"titolo": "Raccolta", "approvazione": False}, {"titolo": "Sintesi", "approvazione": False}, {"titolo": "Consegna", "approvazione": True}]})
    chiamate.clear()
    pid2 = c.post("/percorsi", headers=H, json={"agente_id": scout, "titolo": "Automatico", "brief": "prova"}).json()["id"]
    p = c.get(f"/percorsi/{pid2}", headers=H).json()
    ok("le fasi senza approvazione proseguono da sole fino a quella che richiede la decisione", p["stato"] == "in_attesa" and p["fase_corrente"] == 3 and len(chiamate) == 3, f"{p['stato']} {p['fase_corrente']} {len(chiamate)}")
    ok("annullo il percorso", c.post(f"/percorsi/{pid2}/decisione", headers=H, json={"azione": "annulla"}).json()["stato"] == "annullato")
    ok("un percorso annullato non si approva (409)", c.post(f"/percorsi/{pid2}/decisione", headers=H, json={"azione": "approva"}).status_code == 409)
    # --- errore e riprova
    guasto["si"] = True
    pid3 = c.post("/percorsi", headers=H, json={"agente_id": scout, "titolo": "Guasto", "brief": "prova"}).json()["id"]
    p = c.get(f"/percorsi/{pid3}", headers=H).json()
    ok("errore del modello: il percorso va in 'errore' con il motivo", p["stato"] == "errore" and "servizio" in (p["errore"] or ""))
    guasto["si"] = False
    ok("riprova dopo l'errore", c.post(f"/percorsi/{pid3}/decisione", headers=H, json={"azione": "riprova"}).status_code == 200 and c.get(f"/percorsi/{pid3}", headers=H).json()["stato"] == "in_attesa")
    # --- permessi
    ok("collaboratore senza accessi: non vede i percorsi", c.get("/percorsi", headers=HS).json() == [] and c.get(f"/percorsi/{pid3}", headers=HS).status_code == 404)
    ok("collaboratore senza accessi: non avvia (403)", c.post("/percorsi", headers=HS, json={"agente_id": scout, "titolo": "x", "brief": "y"}).status_code == 403)
    ok("il collaboratore non modifica le fasi (403)", c.put(f"/gestione/agenti/{scout}", headers=HS, json={"fasi": []}).status_code == 403)
    ok("senza accesso non si decide (404)", c.post(f"/percorsi/{pid3}/decisione", headers=HS, json={"azione": "annulla"}).status_code == 404)
    # --- riavvio del servizio
    sql("UPDATE percorsi_lavoro SET stato='in_elaborazione' WHERE id=%s", (pid3,))
    percorsi.recupera_interrotti()
    ok("dopo un riavvio i percorsi 'in elaborazione' diventano 'errore' e si possono riprovare", sql("SELECT stato FROM percorsi_lavoro WHERE id=%s", (pid3,))[0][0] == "errore")
print(f"TOTALE {sum(ris)}/{len(ris)}")
