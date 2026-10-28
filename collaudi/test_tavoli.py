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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, tavoli, consegne, scheda_progetto, memoria, ginnasio, squadre
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
tavoli.SINCRONO = True
aur = ID("Aurora")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    odg = "Valutare se avviare un laboratorio di restauro digitale per il borgo e con quali priorita'."
    ok("Carla non convoca", c.post("/gestione/tavoli", headers=HC, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario"]}).status_code == 403)
    ok("un solo partecipante rifiutato", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco"]}).status_code == 422)
    ok("partecipante sconosciuto rifiutato", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Nessuno"]}).status_code == 422)
    ok("ordine del giorno troppo corto", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": "breve", "partecipanti": ["Marco", "Dario"]}).status_code == 422)
    ok("giri fuori limite", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario"], "turni": 5}).status_code == 422)
    ok("moderatore sconosciuto", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario"], "moderatore": "Nessuno"}).status_code == 422)
    copione[:] = [fine("Marco: servono fondi e un responsabile."), fine("Dario: serve un sito dedicato."), fine("Marco: concordo sul sito, ma prima i fondi."), fine("Dario: ok, parto dal sito dopo i fondi."),
                  fine("SINTESI\nSi parte dai fondi.\nDECISIONI PROPOSTE\n1. Fondi\nAZIONI\nMarco: bando entro giugno")]
    ultimi_msg.clear()
    r = c.post("/gestione/tavoli", headers=H, json={"titolo": "Laboratorio restauro", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario", "Marco"], "turni": 2})
    ok("tavolo convocato", r.status_code == 201, r.text[:200]); tid = r.json()["id"]
    t = c.get(f"/gestione/tavoli/{tid}", headers=H).json()
    ok("tavolo concluso con verbale", t["stato"] == "conclusa" and "Si parte dai fondi" in t["verbale"], str(t)[:300])
    ok("quattro interventi: due giri per due partecipanti (doppioni ignorati)", [(i["turno"], i["nome"]) for i in t["interventi"]] == [(1, "Marco"), (1, "Dario"), (2, "Marco"), (2, "Dario")], str(t["interventi"]))
    ok("il secondo vede cio' che ha detto il primo", "servono fondi e un responsabile" in ultimi_msg[1])
    ok("nel secondo giro si risponde agli altri", "Rispondi agli altri" in ultimi_msg[2])
    ok("il moderatore e' Aurora e riceve tutti gli interventi", t["moderatore"] == "Aurora" and "concordo sul sito" in ultimi_msg[4] and "Ordine del giorno" in ultimi_msg[4])
    ok("notifica del verbale", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Tavolo %%concluso%%'")[0][0] == 1)
    el = c.get("/gestione/tavoli", headers=H).json()["tavoli"]
    ok("elenco con partecipanti", el[0]["partecipanti"] == "Marco, Dario" and el[0]["interventi"] == 4)
    # un partecipante in errore non ferma il tavolo
    sql("UPDATE agenti SET attivo = FALSE WHERE id = %s", (dario,))
    ok("agente spento non convocabile", c.post("/gestione/tavoli", headers=H, json={"titolo": "Prova", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario"]}).status_code == 422)
    sql("UPDATE agenti SET attivo = TRUE WHERE id = %s", (dario,))
    def guasto(*a, **k): raise RuntimeError("fornitore fuori servizio")
    orig = agente_browser._chiama_api
    n = {"i": 0}
    def mista(corpo):
        n["i"] += 1
        if n["i"] == 1: raise RuntimeError("fornitore fuori servizio")
        return orig(corpo)
    agente_browser._chiama_api = mista; copione[:] = [fine("Dario: io ci sono."), fine("Verbale senza Marco.")]
    r = c.post("/gestione/tavoli", headers=H, json={"titolo": "Secondo tavolo", "ordine_del_giorno": odg, "partecipanti": ["Marco", "Dario"], "turni": 1})
    t2 = c.get(f"/gestione/tavoli/{r.json()['id']}", headers=H).json()
    ok("il tavolo prosegue senza chi non riesce", t2["stato"] == "conclusa" and "non ha potuto intervenire" in t2["interventi"][0]["testo"] and "io ci sono" in t2["interventi"][1]["testo"], str(t2)[:300])
    ok("tavolo inesistente", c.get("/gestione/tavoli/99999", headers=H).status_code == 404)
    ok("vista servita", "vistaTavoli" in c.get("/app/tavoli.js").text)
print("TOTALE", sum(ris), "/", len(ris))
