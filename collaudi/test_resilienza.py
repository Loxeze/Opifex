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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, spesa, dipendenze, consegne, scheda_progetto, memoria, ginnasio, squadre
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
from app.esecuzione import esegui_agente, EsecuzioneBloccata
mk_id = mk
div_di = lambda n: sql("SELECT divisione_id FROM agenti WHERE id=%s", (n,))[0][0]
ok("Giulia e' nel reparto Marketing (prova)", div_di(giulia) is not None)
dv = div_di(giulia)
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("Carla non vede la spesa per reparto", c.get("/gestione/spesa-reparti", headers=HC).status_code == 403)
    ok("elenco reparti", len(c.get("/gestione/spesa-reparti", headers=H).json()["reparti"]) >= 2)
    ok("tetto negativo rifiutato", c.put(f"/gestione/spesa-reparti/{dv}", headers=H, json={"tetto": -1}).status_code == 422)
    ok("reparto inesistente", c.put("/gestione/spesa-reparti/99999", headers=H, json={"tetto": 5}).status_code == 404)
    ok("Carla non imposta tetti", c.put(f"/gestione/spesa-reparti/{dv}", headers=HC, json={"tetto": 5}).status_code == 403)
    ok("tetto impostato", c.put(f"/gestione/spesa-reparti/{dv}", headers=H, json={"tetto": 1.0}).status_code == 200)
    copione[:] = [fine("risposta")] * 6
    esegui_agente(giulia, "ciao", "interno", None)
    ok("sotto il tetto lavora", True)
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'m',1,1,0.85)", (giulia,))
    esegui_agente(giulia, "ciao", "interno", None)
    ok("all'80% lavora ancora", True)
    n80 = sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Reparto %%' AND critica = FALSE")[0][0]
    ok("avviso all'80% una sola volta", n80 == 1, str(n80))
    esegui_agente(giulia, "ciao", "interno", None)
    ok("l'avviso non si ripete", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Reparto %%' AND critica = FALSE")[0][0] == 1)
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'m',1,1,0.30)", (giulia,))
    try:
        esegui_agente(giulia, "ciao", "interno", None); bloccato = False
    except EsecuzioneBloccata as e:
        bloccato = "reparto" in str(e)
    ok("al 100% il reparto si ferma", bloccato)
    ok("avviso critico al 100%", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Reparto %%' AND critica = TRUE")[0][0] == 1)
    altro = sql("SELECT id FROM agenti WHERE attivo AND divisione_id IS NOT NULL AND divisione_id <> %s AND tipo <> 'sistema' LIMIT 1", (dv,))[0][0]
    esegui_agente(altro, "ciao", "interno", None)
    ok("un altro reparto lavora", True)
    esegui_agente(ID("Aurora"), "ciao", "interno", None)
    ok("Aurora non si ferma", True)
    r = c.get("/gestione/spesa-reparti", headers=H).json()["reparti"]
    mio = [x for x in r if x["id"] == dv][0]
    ok("la spesa del reparto e' calcolata", abs(mio["speso"] - 1.15) < 0.01 and mio["tetto"] == 1.0, str(mio))
    c.put(f"/gestione/spesa-reparti/{dv}", headers=H, json={"tetto": 10})
    esegui_agente(giulia, "ciao", "interno", None)
    ok("alzando il tetto riparte", True)
    c.put(f"/gestione/spesa-reparti/{dv}", headers=H, json={"tetto": None})
    ok("senza tetto nessun limite", sql("SELECT tetto_spesa_mese FROM divisioni WHERE id=%s", (dv,))[0][0] is None)

    # dipendenze
    req = tmp / "requirements.txt"; req.write_text("fastapi==0.1.0\nrequests==2.0.0  # vecchia\n\n# commento\npsycopg[binary]==3.3.6\n")
    ok("lettura requirements", dipendenze.librerie(req) == [("fastapi", "0.1.0"), ("requests", "2.0.0"), ("psycopg", "3.3.6")], str(dipendenze.librerie(req)))
    dipendenze._interroga = lambda lib: [[], ["GHSA-aaaa", "PYSEC-1"], []]
    with connessione() as cn:
        ok("mai controllato: da fare", dipendenze.da_fare(cn))
        r = dipendenze.controlla(cn, req)
    ok("trovata la libreria vulnerabile", r["esito"] == "vulnerabilita" and r["dettagli"][0]["libreria"] == "requests" and "GHSA-aaaa" in r["dettagli"][0]["vulnerabilita"], str(r))
    ok("avviso a Lorenzo", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Controllo dipendenze%%' AND urgente")[0][0] == 1)
    with connessione() as cn:
        ok("controllato oggi: non si ripete", not dipendenze.da_fare(cn))
    dipendenze._interroga = lambda lib: [[], [], []]
    with connessione() as cn:
        ok("tutto pulito", dipendenze.controlla(cn, req)["esito"] == "ok")
    def giu(lib): raise OSError("rete assente")
    dipendenze._interroga = giu
    with connessione() as cn:
        ok("rete assente: registrato e non blocca", dipendenze.controlla(cn, req)["esito"] == "non_raggiungibile")
    s = c.get("/gestione/dipendenze", headers=H).json()
    ok("stato via API", s["ultimo"]["esito"] == "non_raggiungibile" and s["librerie"] > 5, str(s)[:200])
    ok("Carla non vede le dipendenze", c.get("/gestione/dipendenze", headers=HC).status_code == 403)
    dipendenze._interroga = lambda lib: [[] for _ in lib]
    ok("controllo manuale", c.post("/gestione/dipendenze/controlla", headers=H).json()["esito"] == "ok")
    ok("viste servite", "vistaSpesaReparti" in c.get("/app/controlli.js").text)
print("TOTALE", sum(ris), "/", len(ris))
