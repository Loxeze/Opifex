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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, impara_esempio, consegne, scheda_progetto, memoria, ginnasio, squadre
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
sql("UPDATE agenti SET modello='claude-sonnet-5-5'")
impara_esempio.SINCRONO = True
cas = ID("Padre Casati")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    chat = "Utente: voglio un sito vetrina per Logos, video in evidenza.\nChatGPT: ecco subito una pagina completa..." * 12
    ok("elenco agenti per l'apprendimento", c.get("/gestione/ginnasio/da-esempio", headers=H).status_code == 200)
    ok("Carla non puo'", c.post("/gestione/ginnasio/da-esempio", headers=HC, json={"agente_id": scout, "competenza": "Sito vetrina", "trascrizione": chat}).status_code == 403)
    ok("conversazione troppo corta rifiutata", c.post("/gestione/ginnasio/da-esempio", headers=H, json={"agente_id": scout, "competenza": "Sito vetrina", "trascrizione": "ciao"}).status_code == 422)
    copione[:] = [fine("DESCRIZIONE: Come costruire un sito vetrina completo al primo giro.\n1. QUANDO SI USA\nSiti vetrina.\n2. STILE DI LAVORO\nSi consegna subito una pagina completa e si migliora a giri. " + "Passo. " * 60)]
    ultimi_msg.clear()
    r = c.post("/gestione/ginnasio/da-esempio", headers=H, json={"agente_id": scout, "competenza": "Sito vetrina", "trascrizione": chat, "obiettivo": "Sito Logos"})
    ok("esempio accettato", r.status_code == 202, r.text[:200])
    ok("Padre Casati riceve la conversazione come materiale, non come istruzioni", "MATERIALE DA STUDIARE" in ultimi_msg[0] and "voglio un sito vetrina" in ultimi_msg[0])
    b = sql("SELECT l.stato, l.livello, l.descrizione, f.stato, f.agente_id FROM competenze_livelli l JOIN richieste_formazione f ON f.livello_id = l.id")
    ok("nasce una bozza da approvare legata all'agente", len(b) == 1 and b[0][0] == "bozza" and b[0][1] == 1 and b[0][3] == "da_approvare" and b[0][4] == scout and "sito vetrina" in b[0][2].lower(), str(b))
    ok("compare tra le bozze del Ginnasio", any(x["competenza"] == "Sito vetrina" for x in c.get("/gestione/ginnasio", headers=H).json()["da_approvare"]))
    lid = sql("SELECT id FROM competenze_livelli")[0][0]
    ok("approvazione: l'agente riceve la competenza", c.post(f"/gestione/ginnasio/livelli/{lid}/decisione", headers=H, json={"azione": "approva"}).status_code == 200 and sql("SELECT livello FROM agenti_competenze WHERE agente_id=%s", (scout,)) == [(1,)])
    ok("notifica", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Padre Casati ha ricavato il metodo%%'")[0][0] == 1)
    copione[:] = [fine("DESCRIZIONE: Livello due.\n" + "Altro passo importante. " * 40)]
    r = c.post("/gestione/ginnasio/da-esempio", headers=H, json={"agente_id": scout, "competenza": "Sito vetrina", "trascrizione": chat})
    ok("un secondo esempio sulla stessa competenza diventa il livello successivo", r.status_code == 202 and sql("SELECT livello FROM competenze_livelli WHERE stato='bozza'") == [(2,)])
    ok("una bozza aperta blocca un'altra sulla stessa competenza", c.post("/gestione/ginnasio/da-esempio", headers=H, json={"agente_id": scout, "competenza": "Sito vetrina", "trascrizione": chat}).status_code == 422)
    copione[:] = [fine("troppo corto")]
    c.post("/gestione/ginnasio/da-esempio", headers=H, json={"agente_id": scout, "competenza": "Altra cosa", "trascrizione": chat})
    ok("risposta inutilizzabile: errore chiaro, nessuna bozza", sql("SELECT stato FROM esempi_appresi ORDER BY id DESC LIMIT 1") == [("errore",)] and sql("SELECT count(*) FROM competenze_livelli WHERE stato='bozza' AND competenza_id=(SELECT id FROM competenze WHERE nome='Altra cosa')")[0][0] == 0)
    ok("vista servita", "vistaEsempio" in c.get("/app/controlli.js").text)
print("TOTALE", sum(ris), "/", len(ris))
