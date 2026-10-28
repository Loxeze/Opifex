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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, scheda_impresa, consegne, scheda_progetto, memoria, ginnasio, squadre
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
from app.esecuzione import esegui_agente
sql("UPDATE agenti SET modello='claude-sonnet-5-5'"); sql("DELETE FROM agenti_aziende")
reno = sql("INSERT INTO aziende (nome, colore) VALUES ('Montarrenti', '#111111') RETURNING id")[0][0]
sql("INSERT INTO agenti_aziende (agente_id, azienda_id) VALUES (%s,%s),(%s,%s)", (marco, az, dario, reno))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("Carla non vede le schede", c.get("/gestione/imprese", headers=HC).status_code == 403)
    el = c.get("/gestione/imprese", headers=H).json()
    ok("elenco imprese", any(x["nome"] == "Renovatio" for x in el["imprese"]) and el["totale_campi"] == 9)
    r = c.put(f"/gestione/imprese/{az}/identita", headers=H, json={"testo": "Renovatio Group: restauro e rilancio di borghi storici in Toscana."})
    ok("campo scritto", r.status_code == 200)
    c.put(f"/gestione/imprese/{az}/regole", headers=H, json={"testo": "Mai promettere date di consegna senza il via libera di Lorenzo."})
    c.put(f"/gestione/imprese/{reno}/identita", headers=H, json={"testo": "Castello di Montarrenti: struttura ricettiva e eventi."})
    ok("campo sconosciuto rifiutato", c.put(f"/gestione/imprese/{az}/boh", headers=H, json={"testo": "x"}).status_code == 422)
    ok("impresa inesistente rifiutata", c.put("/gestione/imprese/99999/identita", headers=H, json={"testo": "x"}).status_code == 422)
    ok("testo troppo lungo rifiutato", c.put(f"/gestione/imprese/{az}/offerta", headers=H, json={"testo": "x" * 9000}).status_code == 422)
    d = c.get(f"/gestione/imprese/{az}", headers=H).json()
    ok("scheda letta", d["scheda"]["identita"]["testo"].startswith("Renovatio Group") and d["scheda"]["offerta"]["testo"] == "")
    c.put(f"/gestione/imprese/{az}/identita", headers=H, json={"testo": "Renovatio Group: restauro, rilancio e gestione di borghi storici."})
    v = c.get(f"/gestione/imprese/{az}/identita/versioni", headers=H).json()["versioni"]
    ok("la versione precedente resta", len(v) == 1 and v[0]["testo"].startswith("Renovatio Group: restauro e rilancio"))

    # nei prompt: solo la propria impresa
    copione[:] = [fine("ok")] * 4; ultimi_msg.clear()
    esegui_agente(marco, "ciao", "interno", None)
    m1 = ultimi_msg[-1]
    ok("Marco riceve la scheda di Renovatio", "SCHEDA D'IMPRESA" in m1 and "gestione di borghi storici" in m1 and "Mai promettere date" in m1)
    ok("ma non quella di Montarrenti", "Castello di Montarrenti" not in m1)
    esegui_agente(dario, "ciao", "interno", None)
    ok("Dario riceve quella di Montarrenti", "Castello di Montarrenti" in ultimi_msg[-1] and "Renovatio Group" not in ultimi_msg[-1])
    esegui_agente(nico, "ciao", "interno", None)
    ok("chi non appartiene a nessuna impresa non riceve nulla", "SCHEDA D'IMPRESA" not in ultimi_msg[-1])
    sql("UPDATE agenti SET vede_tutto=TRUE WHERE id=%s", (scout,))
    esegui_agente(scout, "ciao", "interno", None)
    ok("chi vede tutto le riceve tutte", "Castello di Montarrenti" in ultimi_msg[-1] and "Renovatio Group" in ultimi_msg[-1])

    # proposte degli agenti
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    sql("UPDATE agenti SET livello='manager' WHERE id=%s", (marco,))
    esegui_agente(marco, "ciao", "interno", None)
    ok("il manager ha lo strumento impresa_proponi", any("impresa_proponi" in s for s in strumenti_visti), str(strumenti_visti)[:200])
    ok("proposta: impresa sconosciuta", scheda_impresa.strumento(marco)("impresa_proponi", {"impresa": "Boh", "campo": "offerta", "testo": "Restauri"}).startswith("ERRORE"))
    ok("proposta: campo sconosciuto", scheda_impresa.strumento(marco)("impresa_proponi", {"impresa": "Renovatio", "campo": "boh", "testo": "Restauri"}).startswith("ERRORE"))
    msg = scheda_impresa.strumento(marco)("impresa_proponi", {"impresa": "Renovatio", "campo": "offerta", "testo": "Restauro di edifici storici e gestione di eventi culturali.", "motivo": "Emerso nel bando"})
    ok("proposta registrata", msg.startswith("Proposta registrata"), msg)
    ok("la scheda non e' ancora cambiata", c.get(f"/gestione/imprese/{az}", headers=H).json()["scheda"]["offerta"]["testo"] == "")
    ok("proposta identica rifiutata", scheda_impresa.strumento(marco)("impresa_proponi", {"impresa": "Renovatio", "campo": "offerta", "testo": "Restauro di edifici storici e gestione di eventi culturali."}).startswith("ERRORE"))
    pr = c.get("/gestione/imprese/proposte", headers=H).json()["proposte"]
    ok("la proposta e' in elenco", len(pr) == 1 and pr[0]["agente"] == "Marco" and pr[0]["impresa"] == "Renovatio")
    pd = c.get("/v1/decisioni", headers=H).json()["decisioni"]
    ok("compare nella posta delle decisioni", any(x["tipo"] == "impresa" for x in pd), str(pd)[:200])
    r = c.post(f"/v1/decisioni/impresa/{pr[0]['id']}", headers=H, json={"azione": "approva"})
    ok("approvata dalla posta", r.status_code == 200 and c.get(f"/gestione/imprese/{az}", headers=H).json()["scheda"]["offerta"]["testo"].startswith("Restauro di edifici"), r.text[:200])
    ok("non si decide due volte", c.post(f"/gestione/imprese/proposte/{pr[0]['id']}", headers=H, json={"azione": "approva"}).status_code == 422)
    scheda_impresa.strumento(marco)("impresa_proponi", {"impresa": "Renovatio", "campo": "voce", "testo": "Tono caldo e istituzionale."})
    pid2 = c.get("/gestione/imprese/proposte", headers=H).json()["proposte"][0]["id"]
    ok("respinta", c.post(f"/gestione/imprese/proposte/{pid2}", headers=H, json={"azione": "respingi"}).status_code == 200
       and c.get(f"/gestione/imprese/{az}", headers=H).json()["scheda"]["voce"]["testo"] == "")
    ok("azione errata", c.post(f"/gestione/imprese/proposte/{pid2}", headers=H, json={"azione": "boh"}).status_code == 422)
    ok("vista servita", "vistaImprese" in c.get("/app/imprese.js").text)
print("TOTALE", sum(ris), "/", len(ris))
