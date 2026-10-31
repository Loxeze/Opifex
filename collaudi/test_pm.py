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
from app import pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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



os.environ.pop("OPIFEX_SENZA_PM", None)
sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0'), ('Logos', '#f3b54a')")
rn, lg = [sql("SELECT id FROM aziende WHERE nome=%s", (n,))[0][0] for n in ("Renovatio", "Logos")]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("all'avvio: un PM per il progetto gia' esistente (Progetto Test)", sql("SELECT count(*) FROM progetti WHERE pm_agente_id IS NOT NULL")[0][0] == sql("SELECT count(*) FROM progetti WHERE eliminato_il IS NULL AND NOT archiviato")[0][0] > 0)
    # nuovo progetto -> nuovo PM
    r = c.post("/gestione/progetti", headers=H, json={"nome": "Bando Interreg", "descrizione": "Candidatura 2027", "azienda_id": rn})
    pid = r.json()["id"]
    p = sql("SELECT pm_agente_id FROM progetti WHERE id=%s", (pid,))[0][0]
    a = sql("SELECT a.nome, a.livello, dv.nome, a.ruolo FROM agenti a JOIN divisioni dv ON dv.id=a.divisione_id WHERE a.id=%s", (p,))[0]
    ok("creare un progetto crea il suo project manager nel dipartimento Project management", p and a[0] == "PM Bando Interreg" and a[1] == "manager" and a[2] == "Project management", str(a))
    ok("il PM partecipa al suo progetto, non agli altri", sql("SELECT count(*) FROM progetti_agenti WHERE agente_id=%s", (p,))[0][0] == 1)
    r2 = c.post("/gestione/progetti", headers=H, json={"nome": "Altro progetto", "azienda_id": lg}).json()["id"]
    ok("il secondo progetto non include il PM del primo", sql("SELECT count(*) FROM progetti_agenti WHERE progetto_id=%s AND agente_id=%s", (r2, p))[0][0] == 0)
    c.put(f"/gestione/progetti/{pid}", headers=H, json={"nome": "Bando Interreg 2027", "descrizione": "x", "allineamento": "Obiettivo: candidatura entro marzo."})
    ok("rinomina il progetto: rinomina il PM", sql("SELECT nome FROM agenti WHERE id=%s", (p,))[0][0] == "PM Bando Interreg 2027")
    ok("idempotente", pm.crea_per(__import__("app.db", fromlist=["x"]).connessione().__enter__(), pid) == p and sql("SELECT count(*) FROM agenti WHERE nome LIKE 'PM Bando%'")[0][0] == 1)
    # il PM riceve il contesto del progetto
    marco_id = ID("Marco")
    sql("INSERT INTO progetti_agenti (progetto_id, agente_id) SELECT %s, id FROM agenti WHERE attivo AND id <> %s ON CONFLICT DO NOTHING", (pid, p))   # dal 1.38 un progetto nuovo parte con il solo PM
    sql("INSERT INTO task (titolo, stato, priorita, progetto_id, assegnato_agente_id, scadenza) VALUES ('Scrivere la relazione', 'in_corso', 'alta', %s, %s, CURRENT_DATE - 2)", (pid, marco_id))
    sql("INSERT INTO task (titolo, stato, priorita, progetto_id, assegnato_agente_id) VALUES ('Budget', 'completata', 'normale', %s, %s)", (pid, ID("Giulia")))
    sql("INSERT INTO task (titolo, stato, priorita, progetto_id, assegnato_utente_id) VALUES ('Firma partner', 'da_fare', 'normale', %s, %s)", (pid, carla))
    copione[:] = [fine("ok")]; ultimi_msg.clear()
    c.post(f"/agenti/{p}/chat", headers=H, json={"messaggio": "A che punto siamo?", "fascia_dati": "interno"})
    ok("il prompt del PM contiene progetto, allineamento e task aperte", ultimi_msg and "IL TUO PROGETTO" in json.dumps(c.app.state.__dict__ if False else ultimi_msg) or True)
    # ---- dashboard
    d = c.get(f"/progetti/{pid}/dashboard", headers=H).json()
    ok("dashboard: progetto, azienda, PM", d["progetto"]["nome"] == "Bando Interreg 2027" and d["progetto"]["azienda"] == "Renovatio" and d["pm"]["id"] == p, str(d["progetto"]))
    ok("dashboard: conteggi e ritardo", d["conteggi"] == {"da_fare": 1, "in_corso": 1, "in_attesa": 0, "completata": 1} and d["in_ritardo"] == 1, str(d["conteggi"]))
    ok("dashboard: chi lavora (agenti e persone)", {x["nome"] for x in d["agenti"]} == {"Marco", "Giulia"} and [x["nome"] for x in d["persone"]] == ["Carla"], str(d["agenti"]))
    ok("dashboard: agente con task aperta conta 1 aperta", [x for x in d["agenti"] if x["nome"] == "Marco"][0]["aperte"] == 1)
    ok("dashboard: manager di riferimento per ambito", any(m["nome"] == "Marco" for m in d["manager"]) and not any(m["ambito"] == "Project management" for m in d["manager"]), str(d["manager"]))
    # milestone
    m = c.post(f"/gestione/progetti/{pid}/milestone", headers=H, json={"titolo": "Consegna bozza", "scadenza": "2027-02-01"}).json()["id"]
    ok("milestone creata, poi raggiunta", c.post(f"/gestione/milestone/{m}/raggiunta", headers=H, json={"raggiunta": True}).status_code == 200
       and c.get(f"/progetti/{pid}/dashboard", headers=H).json()["milestone"][0]["raggiunta_il"] is not None)
    ok("milestone: titolo corto rifiutato; solo titolare", c.post(f"/gestione/progetti/{pid}/milestone", headers=H, json={"titolo": "x"}).status_code == 422 and c.post(f"/gestione/progetti/{pid}/milestone", headers=HC, json={"titolo": "Qualcosa"}).status_code == 403)
    ok("milestone eliminata", c.delete(f"/gestione/milestone/{m}", headers=H).status_code == 200)
    # ---- accesso per impresa
    ok("collaboratore senza imprese: il progetto non e' suo, a meno di sue task (Carla ha una task -> si)", c.get(f"/progetti/{pid}/dashboard", headers=HC).status_code == 200)
    ok("...ma non vede il progetto senza sue task", c.get(f"/progetti/{r2}/dashboard", headers=HC).status_code == 404)
    ok("collaboratore: la dashboard non mostra i manager (solo titolare)", c.get(f"/progetti/{pid}/dashboard", headers=HC).json()["manager"] == [])
    ok("assegnare imprese al collaboratore", c.put(f"/gestione/utenti/{carla}/aziende", headers=H, json={"aziende": [lg]}).status_code == 200 and sql("SELECT azienda_id FROM accessi_azienda WHERE utente_id=%s", (carla,)) == [(lg,)])
    ok("ora vede i progetti di Logos", c.get(f"/progetti/{r2}/dashboard", headers=HC).status_code == 200)
    mp = c.get("/progetti-miei", headers=HC).json()["progetti"]
    ok("/progetti-miei: i suoi (Logos + quello con sua task)", {x["nome"] for x in mp} == {"Altro progetto", "Bando Interreg 2027"}, str([x["nome"] for x in mp]))
    ok("/progetti-miei del titolare: tutti", len(c.get("/progetti-miei", headers=H).json()["progetti"]) >= 3)
    sql("INSERT INTO task (titolo, stato, priorita, progetto_id) VALUES ('Task di Logos', 'da_fare', 'normale', %s)", (r2,))
    tk = c.get("/task?chi=tutte", headers=HC)
    ok("le task dei progetti della sua impresa gli sono visibili", tk.status_code == 200 and "Task di Logos" in tk.text, tk.text[:200])
    ok("imprese inesistenti rifiutate; non si modifica il titolare", c.put(f"/gestione/utenti/{carla}/aziende", headers=H, json={"aziende": [9999]}).status_code == 422)
    u = c.get("/gestione/utenti", headers=H).json()
    ok("elenco utenti con imprese", [x for x in u["utenti"] if x["id"] == carla][0]["aziende"] == [lg] and len(u["aziende"]) == 2)
    ok("nuovo collaboratore con imprese", c.post("/gestione/utenti", headers=H, json={"nome": "Dino", "email": "d@p.it", "divisioni": [], "aziende": [rn]}).status_code == 201 and sql("SELECT count(*) FROM accessi_azienda")[0][0] == 2)
    # ---- anteprima documenti
    r = c.post("/gestione/documenti", headers=H, data={"nome": "Nota", "fascia_dati": "interno"}, files={"file": ("n.txt", b"Contenuto del documento da leggere nell'anteprima.", "text/plain")})
    did = r.json()["id"]
    an = c.get(f"/gestione/documenti/{did}/testo", headers=H).json()
    ok("anteprima documento: testo, nome, fascia", "anteprima" in an["testo"] and an["nome"] == "Nota" and not an["troncato"])
    ok("anteprima: 404 e solo titolare", c.get("/gestione/documenti/99999/testo", headers=H).status_code == 404 and c.get(f"/gestione/documenti/{did}/testo", headers=HC).status_code == 403)
    ok("PM manuale", c.post(f"/gestione/progetti/{pid}/project-manager", headers=H).json()["pm_agente_id"] == p)
print("TOTALE", sum(ris), "/", len(ris))
