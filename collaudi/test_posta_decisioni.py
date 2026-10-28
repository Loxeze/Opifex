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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, note_aurora, consegne, memoria_lavoro as ml, consegne, scheda_progetto, memoria, ginnasio, squadre
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")






ginnasio.SINCRONO = True
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') RETURNING id")[0][0]
consegne.SINCRONO = True
aur = ID("Aurora")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    r = c.get("/v1/decisioni", headers=H)
    ok("posta vuota", r.status_code == 200 and r.json()["decisioni"] == "" or r.json()["decisioni"] == [], r.text[:200])
    ok("sintesi vuota", "Non hai decisioni" in r.json()["sintesi"])
    ok("Carla non vede la posta", c.get("/v1/decisioni", headers=HC).status_code == 403)
    rid = sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,'Qual e'' il budget del sito?',TRUE) RETURNING id", (scout,))[0][0]
    with connessione() as cn:
        mid = ml.proponi(cn, "Per il frantoio non si partecipa a bandi sotto 20.000 euro", "decisione")
    regid = sql("INSERT INTO regole_smistamento (quando, a_agente_id, stato) VALUES ('arriva un bando di cultura', %s, 'proposta') RETURNING id", (marco,))[0][0]
    iid = sql("INSERT INTO iniziative (titolo, stato, aperta_da_agente_id) VALUES ('Raccolta fondi estate','da_approvare',%s) RETURNING id", (marco,))[0][0]
    with connessione() as cn:
        nid = note_aurora.crea(cn, 1, "Nota di prova per la posta")
        note_aurora.proponi(cn, nid, "Marco", "Analizza la nota di prova e dimmi cosa ne pensi")
    sql("INSERT INTO post_social (canale_id, canale_nome, testo, stato) VALUES ('c1','Instagram','Ciao a tutti','da_approvare')")
    d = c.get("/v1/decisioni", headers=H).json()
    tipi = [x["tipo"] for x in d["decisioni"]]
    ok("tutte le decisioni in un elenco", sorted(tipi) == sorted(["richiesta", "memoria", "regola", "iniziativa", "nota"]), str(tipi))
    ok("la richiesta bloccante e' prima e urgente", d["decisioni"][0]["tipo"] == "richiesta" and d["decisioni"][0]["urgente"])
    ok("numerazione 1..5", [x["n"] for x in d["decisioni"]] == [1, 2, 3, 4, 5])
    ok("i post social restano da vedere dal computer", any(x["tipo"] == "social" and x["quanti"] == 1 for x in d["solo_computer"]))
    ok("sintesi parlata", "5 decisioni" in d["sintesi"] and "computer" in d["sintesi"], d["sintesi"])

    ok("azione errata rifiutata", c.post(f"/v1/decisioni/memoria/{mid}", headers=H, json={"azione": "boh"}).status_code == 422)
    ok("tipo sconosciuto rifiutato", c.post("/v1/decisioni/xx/1", headers=H, json={"azione": "approva"}).status_code == 422)
    ok("rispondere senza testo rifiutato", c.post(f"/v1/decisioni/richiesta/{rid}", headers=H, json={"azione": "rispondi"}).status_code == 422)
    r = c.post(f"/v1/decisioni/richiesta/{rid}", headers=H, json={"azione": "rispondi", "testo": "Ottomila euro"})
    ok("risposta alla richiesta", r.status_code == 200 and sql("SELECT stato, risposta FROM richieste_informazioni WHERE id=%s", (rid,))[0] == ("risposta", "Ottomila euro"), r.text[:200])
    ok("la risposta genera una proposta di memoria", sql("SELECT count(*) FROM memorie_lavoro WHERE stato='proposta' AND id<>%s", (mid,))[0][0] == 1)
    sql("UPDATE memorie_lavoro SET stato='scartata' WHERE stato='proposta' AND id<>%s", (mid,))
    r = c.post(f"/v1/decisioni/memoria/{mid}", headers=H, json={"azione": "approva"})
    ok("memoria approvata", r.status_code == 200 and sql("SELECT stato FROM memorie_lavoro WHERE id=%s", (mid,))[0][0] == "approvata", r.text[:200])
    r = c.post(f"/v1/decisioni/regola/{regid}", headers=H, json={"azione": "approva"})
    ok("regola attivata", r.status_code == 200 and sql("SELECT stato FROM regole_smistamento WHERE id=%s", (regid,))[0][0] == "attiva", r.text[:200])
    ok("regola gia' decisa: 404", c.post(f"/v1/decisioni/regola/{regid}", headers=H, json={"azione": "respingi"}).status_code == 404)
    r = c.post(f"/v1/decisioni/iniziativa/{iid}", headers=H, json={"azione": "respingi"})
    ok("iniziativa rifiutata", r.status_code == 200 and sql("SELECT stato FROM iniziative WHERE id=%s", (iid,))[0][0] == "rifiutata", r.text[:200])
    ok("nota respinta torna in bozza", c.post(f"/v1/decisioni/nota/{nid}", headers=H, json={"azione": "respingi"}).status_code == 200
       and sql("SELECT stato, manager_id FROM note_aurora WHERE id=%s", (nid,))[0] == ("bozza", None))
    ok("restano solo i post nel computer", c.get("/v1/decisioni", headers=H).json()["decisioni"] == [])

    # a voce: due passaggi con conferma
    copione[:] = [fine("ok")]
    with connessione() as cn:
        m2 = ml.proponi(cn, "I preventivi sopra 5.000 euro li vede sempre Lorenzo", "regola")
        n2 = note_aurora.crea(cn, 1, "Seconda nota per la voce")
        note_aurora.proponi(cn, n2, "Marco", "Analizza la seconda nota e proponi tre passi")
    voci = c.get("/v1/decisioni", headers=H).json()["decisioni"]
    ok("due decisioni in elenco", len(voci) == 2, str(voci))
    r = c.post("/v1/conferme", headers=H, json={"azione": "decisione.prendi", "parametri": {"n": 1, "azione": "approva"}})
    ok("riepilogo da confermare", r.status_code in (200, 201) and r.json()["riepilogo"].startswith("Approvo"), r.text[:200])
    ok("prima della conferma nulla cambia", sql("SELECT stato FROM memorie_lavoro WHERE id=%s", (m2,))[0][0] == "proposta")
    r2 = c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r.json()["conferma_token"]})
    ok("dopo la conferma e' approvata", r2.status_code == 200 and sql("SELECT stato FROM memorie_lavoro WHERE id=%s", (m2,))[0][0] == "approvata", r2.text[:200])
    r = c.post("/v1/conferme", headers=H, json={"azione": "decisione.prendi", "parametri": {"n": 9, "azione": "approva"}})
    ok("numero inesistente rifiutato", r.status_code == 422)
    r = c.post("/v1/conferme", headers=H, json={"azione": "decisione.prendi", "parametri": {"n": 1, "azione": "rispondi", "testo": "x"}})
    ok("azione non prevista per quel tipo rifiutata", r.status_code == 422)
    ok("comandi vocali presenti", "decisione.prendi" in c.get("/app/voce-app/voce-app.js").text)
print("TOTALE", sum(ris), "/", len(ris))
