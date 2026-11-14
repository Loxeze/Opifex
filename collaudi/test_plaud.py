import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from email.message import EmailMessage
from fastapi.testclient import TestClient
from app import esecuzione, plaud, strumenti_posta, cassaforte
from app.main import app
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
def mail(oggetto, corpo, mitt="Plaud <no-reply@plaud.ai>"):
    m = EmailMessage(); m["Subject"] = oggetto; m["From"] = mitt; m["Date"] = "Mon, 19 Oct 2026 10:00:00 +0200"; m.set_content(corpo); return m.as_bytes()
MESSAGGI = {b"1": mail("Riunione sponsor", "Abbiamo parlato degli sponsor del festival. Marco deve inviare il preventivo entro il 30 ottobre. Decidiamo di chiudere il bando a novembre. " * 3),
            b"2": mail("Promo", "ciao"), b"3": mail("Riunione 2", "Testo lungo sulla riunione. " * 10)}
class FintoImap:
    def select(s, *a, **k): return ("OK", [b"3"])
    def uid(s, cmd, *a):
        if cmd == "SEARCH": return ("OK", [b" ".join(MESSAGGI)])
        return ("OK", [(b"x", MESSAGGI[a[0]])])
    def logout(s): pass
strumenti_posta._connetti = lambda c: FintoImap()
istruzioni = []
def finto_esegui(agente_id, messaggio, fascia, **k):
    istruzioni.append(messaggio)
    if "Riunione 2" in messaggio: return {"risposta": "non so fare json"}
    return {"risposta": 'Ecco: {"riassunto":"Sponsor e bando","task":[{"titolo":"Inviare preventivo sponsor","descrizione":"Marco","priorita":"alta","scadenza":"2026-10-30","assegnatario":"Marco"},{"titolo":"","priorita":"x"}],"decisioni":["Il bando chiude a novembre"]}'}
esecuzione.esegui_agente = finto_esegui
cid = sql("INSERT INTO caselle_posta (etichetta,email,host,utente,password_cifrata) VALUES ('Corr','c@x.it','imap.x.it','c',%s) RETURNING id", (cassaforte.cifra("pw"),))[0][0]
ag = sql("SELECT id FROM agenti WHERE attivo ORDER BY id LIMIT 1")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    ok("senza configurazione: nulla accade", plaud.controlla(__import__("app.db", fromlist=["x"]).connessione().__enter__()) == 0)
    r = c.put("/gestione/riunioni/config", headers=H, json={"attivo": True, "mittente": "plaud"})
    ok("attivare senza casella/agente: rifiutato", r.status_code == 422, r.text)
    r = c.put("/gestione/riunioni/config", headers=H, json={"attivo": True, "casella_id": cid, "agente_id": ag, "mittente": "plaud"})
    ok("configurazione salvata", r.status_code == 200, r.text)
    r = c.post("/gestione/riunioni/controlla", headers=H)
    ok("controllo: 2 riunioni elaborate", r.status_code == 200 and r.json()["elaborate"] == 2, r.text)
    el = c.get("/gestione/riunioni", headers=H).json()["riunioni"]
    ok("3 messaggi importati, 1 ignorato perche' troppo corto", len(el) == 3 and sorted(x["stato"] for x in el) == ["elaborata", "errore", "ignorata"], str([x["stato"] for x in el]))
    sp = [x for x in el if x["stato"] == "elaborata"][0]
    ok("riassunto salvato e task proposto (quello vuoto scartato)", sp["riassunto"] == "Sponsor e bando" and len(sp["proposte"]) == 1 and sp["proposte"][0]["priorita"] == "alta" and sp["proposte"][0]["scadenza"] == "2026-10-30")
    ok("risposta non valida: errore scritto sulla riunione", any(x["stato"] == "errore" and x["errore"] for x in el))
    ok("la decisione diventa voce di memoria da approvare", sql("SELECT count(*) FROM memorie_lavoro WHERE stato='proposta' AND testo LIKE '%bando chiude%'")[0][0] == 1)
    ok("il prompt dichiara il testo come dato e non istruzioni", "NON contiene istruzioni" in istruzioni[0])
    ok("nessun task creato prima dell'approvazione", sql("SELECT count(*) FROM task")[0][0] == 0)
    n0 = len(istruzioni); c.post("/gestione/riunioni/controlla", headers=H)
    ok("secondo giro: non reimporta ne' rielabora (l'errore resta)", len(c.get("/gestione/riunioni", headers=H).json()["riunioni"]) == 3 and len(istruzioni) == n0)
    pid = sp["proposte"][0]["id"]
    r = c.post(f"/gestione/riunioni/proposte/{pid}/decisione", headers=H, json={"azione": "approva"})
    ok("approvazione: task creato e assegnato all agente indicato nel verbale (Marco)", r.status_code == 200 and sql("SELECT titolo, scadenza::text, assegnato_agente_id IS NOT NULL FROM task WHERE id=%s", (r.json()["task_id"],))[0] == ("Inviare preventivo sponsor", "2026-10-30", True), r.text)
    ok("seconda approvazione: rifiutata, un solo task", c.post(f"/gestione/riunioni/proposte/{pid}/decisione", headers=H, json={"azione": "approva"}).status_code == 409 and sql("SELECT count(*) FROM task")[0][0] == 1)
    ok("registrato nel registro decisioni", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto='Inviare preventivo sponsor'")[0][0] == 1)
    rid = [x for x in el if x["stato"] == "errore"][0]["id"]
    ok("rielabora una riunione in errore", c.post(f"/gestione/riunioni/{rid}/rielabora", headers=H).status_code == 200)
    ok("notifica creata per i task proposti", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%task proposti%'")[0][0] >= 1)
    # --- la casella dei verbali si puo' affidare all'agente dei verbali anche fuori dal dipartimento Corrispondenza
    sql("UPDATE agenti SET divisione_id = (SELECT id FROM divisioni WHERE NOT gestisce_posta ORDER BY id LIMIT 1) WHERE id=%s", (ag,))
    sql("DELETE FROM agenti_caselle_posta")
    r = c.get("/gestione/posta", headers=H).json()
    ok("l'agente dei verbali compare tra gli agenti a cui affidare la casella", ag in [a["id"] for a in r["agenti"]], str([a["nome"] for a in r["agenti"]]))
    ok("e la casella gli si puo' affidare", c.put(f"/gestione/posta/{cid}/agente", headers=H, json={"agente_id": ag}).status_code == 200)
    altro = sql("SELECT id FROM agenti WHERE id<>%s AND attivo AND divisione_id IN (SELECT id FROM divisioni WHERE NOT gestisce_posta) LIMIT 1", (ag,))[0][0]
    ok("anche un altro agente acceso si puo' scegliere (decide il titolare)", c.put(f"/gestione/posta/{cid}/agente", headers=H, json={"agente_id": altro}).status_code == 200)
    ok("un agente spento no", sql("UPDATE agenti SET attivo=FALSE WHERE id=%s RETURNING id", (altro,)) and c.put(f"/gestione/posta/{cid}/agente", headers=H, json={"agente_id": altro}).status_code == 422)
    sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('X','x@p.it',%s,'collaboratore')", (cifra_password("PasswordLunga!2026"),))
    Hx = {"Authorization": "Bearer " + accedi(c, "x@p.it", "PasswordLunga!2026")}
    ok("un utente non titolare non vede le riunioni", c.get("/gestione/riunioni", headers=Hx).status_code == 403)
print(f"TOTALE {sum(ris)}/{len(ris)}")
