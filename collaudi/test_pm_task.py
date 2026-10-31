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
    pid = c.post("/gestione/progetti", headers=H, json={"nome": "Mascia", "descrizione": "Progetto", "azienda_id": rn}).json()["id"]
    p = sql("SELECT pm_agente_id FROM progetti WHERE id=%s", (pid,))[0][0]
    copione[:] = [chiama("crea_task", {"titolo": "Creare i profili social del progetto", "scadenza": "2026-10-27", "priorita": "alta", "assegnata_a": "Lorenzo"}, "a"),
                  fine("Fatto")]; strumenti_visti.clear()
    r = c.post(f"/agenti/{p}/chat", headers=H, json={"messaggio": "crea una task per me che scade martedi", "fascia_dati": "interno"})
    ok("chat PM ok", r.status_code == 200, r.text[:200])
    ok("il PM vede gli strumenti", strumenti_visti and {"crea_task", "aggiorna_task", "crea_milestone"} <= set(strumenti_visti[0]), str(strumenti_visti[:1]))
    t = sql("SELECT titolo, scadenza, priorita, progetto_id, azienda_id, assegnato_utente_id, creato_da_agente_id FROM task WHERE progetto_id=%s", (pid,))
    lor = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    ok("task creata nel progetto, assegnata a Lorenzo, con scadenza", len(t) == 1 and str(t[0][1]) == "2026-10-27" and t[0][2] == "alta" and t[0][4] == rn and t[0][5] == lor and t[0][6] == p, str(t))
    ok("registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='task_creata' AND agente_id=%s", (p,))[0][0] == 1)
    from app import pm_strumenti
    g = pm_strumenti.gestore(connessione, p)
    ok("duplicato non creato", "gia'" in g("crea_task", {"titolo": "creare i profili social del progetto"}) and sql("SELECT count(*) FROM task WHERE progetto_id=%s", (pid,))[0][0] == 1)
    ok("data non valida", g("crea_task", {"titolo": "X task", "scadenza": "martedi"}).startswith("ERRORE"))
    ok("assegnatario sconosciuto", g("crea_task", {"titolo": "Y task", "assegnata_a": "Zzzz"}).startswith("ERRORE"))
    tid = t and sql("SELECT id FROM task WHERE progetto_id=%s", (pid,))[0][0]
    ok("aggiorna task + commento", "aggiornata" in g("aggiorna_task", {"id": tid, "stato": "in_corso", "scadenza": "2026-10-30", "commento": "Iniziato"})
       and sql("SELECT stato, scadenza FROM task WHERE id=%s", (tid,))[0][0] == "in_corso" and sql("SELECT count(*) FROM task_commenti WHERE task_id=%s", (tid,))[0][0] == 1)
    ok("task di un altro progetto non modificabile", g("aggiorna_task", {"id": 999999, "stato": "completata"}).startswith("ERRORE"))
    ok("milestone", "creata" in g("crea_milestone", {"titolo": "Profili online", "scadenza": "2026-11-15"}) and sql("SELECT count(*) FROM milestone WHERE progetto_id=%s", (pid,))[0][0] == 1
       and g("crea_milestone", {"titolo": "ab"}).startswith("ERRORE"))
    ag = ID("Marco")
    ok("assegnazione ad agente", "creata" in g("crea_task", {"titolo": "Bozza testi", "assegnata_a": "Marco"}) and sql("SELECT count(*) FROM task WHERE assegnato_agente_id=%s AND progetto_id=%s", (ag, pid))[0][0] == 1)
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("un agente non PM non ha gli strumenti", not any("crea_task" in x for x in strumenti_visti))
print("TOTALE", sum(ris), "/", len(ris))
