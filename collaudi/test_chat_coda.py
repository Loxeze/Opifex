import os, sys, tempfile, json
from pathlib import Path
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
from app import chat_coda, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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





import time
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    copione[:] = [fine("Risposta differita")]
    t0 = time.time()
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno", "asincrono": True})
    ok("invio senza attesa: 202 con id", r.status_code == 202 and "coda_id" in r.json(), r.text)
    cid = r.json()["coda_id"]
    for _ in range(100):
        s_ = c.get(f"/chat-coda/{cid}", headers=H).json()
        if s_["stato"] in ("finito", "errore"): break
        time.sleep(0.1)
    ok("risposta pronta in sottofondo", s_["stato"] == "finito" and s_["risultato"]["risposta"] == "Risposta differita" and s_["secondi"] is not None, str(s_))
    ok("lo scambio e' nella cronologia della chat", sql("SELECT count(*) FROM chat_messaggi WHERE agente_id=%s", (marco,))[0][0] == 2)
    ok("un altro utente non vede il messaggio", c.get(f"/chat-coda/{cid}", headers=HC).status_code == 404)
    ok("fascia dati non valida rifiutata subito", c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "boh", "asincrono": True}).status_code == 422)
    # errore: agente sospeso/bloccato -> l'errore arriva nello stato, non rompe l'invio
    sql("UPDATE agenti SET attivo=FALSE WHERE id=%s", (scout,))
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno", "asincrono": True})
    cid2 = r.json()["coda_id"]
    for _ in range(100):
        s2 = c.get(f"/chat-coda/{cid2}", headers=H).json()
        if s2["stato"] in ("finito", "errore"): break
        time.sleep(0.1)
    ok("errore consegnato come stato, con messaggio", s2["stato"] == "errore" and s2["errore"], str(s2))
    # in corso e ripresa
    sql("INSERT INTO chat_coda (agente_id, utente_id, messaggio, stato) VALUES (%s,(SELECT id FROM utenti WHERE email='l@p.it'),'pendente','in_lavoro')", (marco,))
    ok("messaggi in attesa elencati per riprendere", [x["messaggio"] for x in c.get("/chat-coda", headers=H).json()] == ["pendente"] and c.get("/chat-coda", headers=HC).json() == [])
    with connessione() as cn:
        chat_coda.riavvio(cn)
    ok("al riavvio i lavori a meta' risultano interrotti", sql("SELECT stato FROM chat_coda WHERE messaggio='pendente'") == [("errore",)])
    # allegati asincroni
    copione[:] = [fine("Letto")]
    r = c.post(f"/agenti/{marco}/chat-allegati", headers=H, data={"messaggio": "guarda", "fascia_dati": "interno", "asincrono": "true"}, files=[("file", ("a.txt", ("contenuto di prova per il test. " * 10).encode(), "text/plain"))])
    ok("allegati: anche questi senza attesa", r.status_code == 202, r.text[:300])
    cid3 = r.json()["coda_id"]
    for _ in range(100):
        s3 = c.get(f"/chat-coda/{cid3}", headers=H).json()
        if s3["stato"] in ("finito", "errore"): break
        time.sleep(0.1)
    ok("allegati letti riportati nel risultato", s3["stato"] == "finito" and s3["risultato"]["allegati_letti"] == ["a.txt"], str(s3)[:200])
    # le richieste di uno stesso agente vanno una dopo l'altra
    copione[:] = [fine("uno"), fine("due")]
    ids = [chat_coda.accoda(marco, sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0], f"m{i}", "interno") for i in range(2)]
    for _ in range(150):
        if all(sql("SELECT stato FROM chat_coda WHERE id=%s", (i,))[0][0] in ("finito", "errore") for i in ids): break
        time.sleep(0.1)
    ok("due messaggi allo stesso agente: entrambi risposti, in ordine", [sql("SELECT risultato->>'risposta' FROM chat_coda WHERE id=%s", (i,))[0][0] for i in ids] == ["uno", "due"])
    ok("il vecchio invio sincrono funziona ancora", (lambda: (copione.__setitem__(slice(None), [fine("sync")]), c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "x"}).json()["risposta"])[1])() == "sync")
    ok("interfaccia: invio senza attesa e aggiornamento sul posto", "asincrono: true" in c.get("/app/chat.js").text and "aggiornaConversazione" in c.get("/app/chat.js").text)
print("TOTALE", sum(ris), "/", len(ris))
