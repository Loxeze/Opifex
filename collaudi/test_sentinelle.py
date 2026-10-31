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
from app import casi_prova, proposte_sentinelle, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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





from types import SimpleNamespace
punteggio = [8]
def finto_modello(fornitore, modello, sis, cont, mt=1500, web=None):
    if "valutatore" in sis:
        return SimpleNamespace(testo=json.dumps({"punteggio": punteggio[0], "giudizio": "ok"}), token_input=10, token_output=5)
    return SimpleNamespace(testo=json.dumps([{"richiesta": f"Domanda {i}", "criteri": f"Criterio {i}"} for i in range(3)]), token_input=10, token_output=5)
casi_prova.chiama_modello = finto_modello
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("solo titolare", c.get(f"/gestione/prove/{marco}", headers=HC).status_code == 403 and c.get("/gestione/sentinelle/proposte", headers=HC).status_code == 403)
    r = c.post(f"/gestione/prove/{marco}/genera", headers=H, json={"quanti": 3})
    ok("generazione dei casi", r.status_code == 200 and r.json()["creati"] == 3, r.text)
    ok("caso manuale", c.post(f"/gestione/prove/{marco}/casi", headers=H, json={"richiesta": "Scrivi un saluto", "criteri": "Breve e cortese"}).status_code == 201)
    ok("lancio senza casi rifiutato", c.post(f"/gestione/prove/{scout}/lancia", headers=H, json={}).status_code == 409)
    with connessione() as cn:
        l1 = casi_prova.avvia(cn, marco, "prima", sincrono=True)
    p = c.get(f"/gestione/prove/{marco}", headers=H).json()
    ok("prima prova: 4 esiti, media 8", p["lotti"][0]["stato"] == "finito" and p["lotti"][0]["media"] == 8.0 and sql("SELECT count(*) FROM prove_esiti WHERE lotto_id=%s", (l1,))[0][0] == 4, str(p["lotti"][0]))
    ok("senza secondo lotto niente confronto", p["confronto"]["differenza"] is None)
    sql("UPDATE agenti SET istruzioni = istruzioni || ' Rispondi sempre in modo telegrafico.' WHERE id=%s", (marco,)); punteggio[0] = 5
    with connessione() as cn:
        casi_prova.avvia(cn, marco, "dopo", sincrono=True)
    cf = c.get(f"/gestione/prove/{marco}", headers=H).json()["confronto"]
    ok("confronto prima/dopo: -3 e istruzioni cambiate", cf["differenza"] == -3.0 and cf["cambiato"] is True and len(cf["casi"]) == 4 and cf["casi"][0]["prima"] == 8 and cf["casi"][0]["dopo"] == 5, str(cf)[:300])
    ok("un caso disattivato non entra nella prova", c.put(f"/gestione/prove/casi/{sql('SELECT min(id) FROM casi_prova')[0][0]}?attivo=false", headers=H).status_code == 200)
    # sentinelle
    for i in range(6):
        sql("INSERT INTO valutazioni (agente_id, utente_id, oggetto, voto) VALUES (%s,NULL,'altro',%s)", (valut, -1 if i < 4 else 1))
    sql("UPDATE agenti SET modello_dialogo='claude-opus-4' WHERE id=%s", (dario,))
    sql("INSERT INTO modelli_ai (fornitore_id, nome, fascia) SELECT id, 'claude-opus-4', 'avanzato' FROM fornitori_ai WHERE nome='anthropic' ON CONFLICT DO NOTHING") if False else None
    if not sql("SELECT 1 FROM modelli_ai WHERE nome='claude-opus-4'"):
        sql("INSERT INTO modelli_ai (fornitore_id, nome, fascia) SELECT id, 'claude-opus-4', 'avanzato' FROM fornitori_ai WHERE nome='anthropic'")
    sql("INSERT INTO memorie_lavoro (testo, tipo, stato, agente_id, verifica_il) VALUES ('Scadenza bando X','fatto','approvata',%s,CURRENT_DATE - 3)", (giulia,))
    sql("UPDATE agenti SET creato_il = NOW() - INTERVAL '60 days' WHERE id=%s", (leo,)); sql("DELETE FROM registro_azioni WHERE agente_id=%s", (leo,))
    r = c.post("/gestione/sentinelle/scansiona", headers=H).json()
    ok("le quattro sentinelle trovano qualcosa", r["qualita"] >= 2 and r["costi"] >= 1 and r["fonti"] == 1 and r["evoluzione"] >= 1, str(r))
    ok("seconda scansione: nessun doppione", sum(c.post("/gestione/sentinelle/scansiona", headers=H).json().values()) == 0)
    el = c.get("/gestione/sentinelle/proposte", headers=H).json()
    tipi = {x["tipo"] for x in el}
    ok("tipi di proposta", {"revisione_istruzioni", "peggioramento_prove", "modello_economico", "riverifica", "inattivo"} <= tipi, str(tipi))
    ok("notifica per le nuove proposte", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Le sentinelle hanno%'")[0][0] == 1)
    pm_ = next(x for x in el if x["tipo"] == "modello_economico" and x["agente"] == "Dario")
    ok("approvando si applica", c.post(f"/gestione/sentinelle/proposte/{pm_['id']}/decisione", headers=H, json={"approva": True}).json()["stato"] == "approvata" and sql("SELECT modello_dialogo FROM agenti WHERE id=%s", (dario,))[0][0] is None)
    pi = next(x for x in el if x["tipo"] == "inattivo" and x["agente"] == "Leo")
    c.post(f"/gestione/sentinelle/proposte/{pi['id']}/decisione", headers=H, json={"approva": True})
    ok("agente inattivo spento su approvazione", sql("SELECT attivo FROM agenti WHERE id=%s", (leo,))[0][0] is False)
    pr = next(x for x in el if x["tipo"] == "riverifica")
    c.post(f"/gestione/sentinelle/proposte/{pr['id']}/decisione", headers=H, json={"approva": False})
    ok("respinta: stato e registro", sql("SELECT stato FROM proposte_sentinelle WHERE id=%s", (pr["id"],))[0][0] == "respinta" and sql("SELECT count(*) FROM registro_azioni WHERE azione='proposta_sentinella_decisa'")[0][0] == 3)
    ok("decidere due volte: 404", c.post(f"/gestione/sentinelle/proposte/{pr['id']}/decisione", headers=H, json={"approva": True}).status_code == 404)
    ok("pagina servita", "vistaSentinelle" in c.get("/app/sentinelle.js").text)
    d = c.get("/app/plancia.js").text
    ok("home: pannello unico da decidere con richieste e iniziative e approvazione", "Da decidere" in d and "/gestione/iniziative/" in d and "caricaIniziative" in d)
    ok("pagina richieste unita alle iniziative", "Richieste e iniziative" in c.get("/app/app.js").text)
print("TOTALE", sum(ris), "/", len(ris))
