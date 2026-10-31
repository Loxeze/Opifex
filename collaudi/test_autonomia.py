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
from app.fornitori import Risposta
from app import richieste as rich, webpush, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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




copione, ricevuti = [], []
def finta_api(corpo):
    ricevuti.append(corpo)
    if not copione: print('EXTRA', corpo['system'][:60], str(corpo['messages'])[:200]); return blocco('fine')
    return copione.pop(0)
agente_browser._chiama_api = finta_api
uso = lambda: {"input_tokens": 10, "output_tokens": 5}
def blocco(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    def chiedi(nome, msg="ciao"):
        ricevuti.clear(); return c.post(f"/agenti/{ID(nome)}/chat", headers=H, json={"messaggio": msg, "fascia_dati": "pubblico"})
    # 1. la regola ordina: prima da soli, poi i colleghi, poi un'ipotesi, solo infine Lorenzo
    copione[:] = [blocco("ok")]; chiedi("Scout")
    s = ricevuti[0]["system"]
    ok("la regola di autonomia e' nelle istruzioni di ogni agente", "AUTONOMIA" in s and "ULTIMA RISORSA" in s and "Ipotesi:" in s and "NON chiedergli" in s and "spese" in s, s[-400:])
    # 2. la stessa domanda non viene richiesta a Lorenzo da un altro agente
    copione[:] = [blocco("[MANCA] Quali sono le sei imprese per cui cercare i bandi di finanziamento?")]; r1 = chiedi("Scout")
    copione[:] = [blocco("[MANCA] Quali sono le sei imprese per cui devo cercare i bandi di finanziamento?")]; r2 = chiedi("Marco")
    ok("una domanda quasi identica di un altro agente non crea una seconda richiesta", sql("SELECT count(*) FROM richieste_informazioni")[0][0] == 1 and r2.json()["richieste_create"] == 0, str(r2.json()))
    copione[:] = [blocco("[MANCA] Qual e' il budget massimo per le inserzioni social del prossimo trimestre?")]; chiedi("Giulia")
    ok("una domanda diversa viene invece posta", sql("SELECT count(*) FROM richieste_informazioni")[0][0] == 2)
    # 3. dopo la risposta di Lorenzo tutti gli agenti la conoscono e non la richiedono
    rid = sql("SELECT id FROM richieste_informazioni ORDER BY id LIMIT 1")[0][0]
    c.post(f"/gestione/richieste/{rid}/risposta", headers=H, json={"risposta": "Aquilia, Montarrenti, Evidens, Filigrana, Logos, Renovatio."})
    ok("la risposta e' salvata", sql("SELECT stato FROM richieste_informazioni WHERE id=%s", (rid,))[0][0] == "risposta")
    copione[:] = [blocco("ok")]; chiedi("Leo")
    ok("un agente che non aveva chiesto riceve cio' che Lorenzo ha gia' deciso", "GIA' DECISO" in ricevuti[0]["messages"][0]["content"] and "Filigrana" in ricevuti[0]["messages"][0]["content"], ricevuti[0]["messages"][0]["content"][:300])
    copione[:] = [blocco("[MANCA] Quali sono le sei imprese per cui cercare i bandi di finanziamento?")]; r3 = chiedi("Leo")
    ok("e se la richiede ugualmente non crea una nuova richiesta (gia' risposta di recente)", r3.json()["richieste_create"] == 0)
    sql("UPDATE richieste_informazioni SET risposta_il = NOW() - INTERVAL '90 days' WHERE id=%s", (rid,))
    copione[:] = [blocco("[MANCA] Quali sono le sei imprese per cui cercare i bandi di finanziamento?")]; r4 = chiedi("Leo")
    ok("dopo 60 giorni la risposta e' scaduta: si puo' richiedere", r4.json()["richieste_create"] == 1)
    ok("le risposte vecchie non sono piu' passate agli agenti", "Filigrana" not in (rich.decisioni_note(__import__("app.db", fromlist=["x"]).connessione().__enter__()) or ""))
    # 4. nei dialoghi tra agenti
    visti = []
    def dialogo_spia(f, m, sis, cont, mt, web=None):
        visti.append(sis); return Risposta("Risolto: usiamo il budget gia' indicato. [CHIARITO]", 5, 5)
    from app import dialoghi as dl
    dl.chiama_modello = dialogo_spia
    sql("UPDATE richieste_informazioni SET risposta_il = NOW() WHERE id=%s", (rid,))
    c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID("Marco"), "a_agente_id": ID("Scout"), "argomento": "coordinate la ricerca", "messaggi": 2})
    ok("nei dialoghi: regola 'risolvete tra voi' e decisioni gia' prese di Lorenzo", visti and "RISOLVETE TRA VOI" in visti[0] and "Filigrana" in visti[0] and "AUTONOMIA" in visti[0], visti[0][-300:] if visti else "nessun dialogo")
print("TOTALE", sum(ris), "/", len(ris))
