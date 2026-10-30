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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria, ginnasio, squadre, memoria_vettoriale as mv, documenti, documenti_blocco, giro_domande
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
import io, zipfile
def fake_embed(testi):
    gruppi = [("auto", "macchina", "veicolo"), ("mare", "spiaggia", "oceano")]
    out = []
    for t in testi:
        v = [0.0] * mv.DIM; tl = t.lower()
        for i, g in enumerate(gruppi): v[i] = float(sum(tl.count(p) for p in g))
        v[100 + sum(map(ord, tl)) % 50] = 0.01
        out.append(v)
    return out
mv._embed = fake_embed
documenti_blocco.SINCRONO = True
sql("INSERT INTO fornitori_ai (nome, non_conservazione_attiva, dpa_firmato, fascia_dati_max) SELECT 'openai', TRUE, TRUE, 'riservato' WHERE NOT EXISTS (SELECT 1 FROM fornitori_ai WHERE nome='openai')")
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato' WHERE nome='openai'")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    # --- blocco ---
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cartella/auto1.txt", "La macchina aziendale e il veicolo costano poco. " * 5)
        z.writestr("cartella/auto2.txt", "Il veicolo elettrico e la macchina del reparto. " * 5)
        z.writestr("cartella/mare.txt", "Spiaggia e mare e oceano blu. " * 5)
        z.writestr("cartella/programma.exe", "MZ")
        z.writestr("__MACOSX/auto1.txt", "x"); z.writestr("cartella/.nascosto.txt", "x")
    r = c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("cartella.zip", buf.getvalue())), ("file", ("nota.txt", b"Appunto veloce sul progetto Evidens e sul suo sviluppo."))], data={"fascia_dati": "interno", "per_tutti": "true"})
    ok("blocco accettato", r.status_code == 202, r.text[:200])
    b = sql("SELECT stato, totale, caricati, saltati FROM caricamenti_blocco")
    ok("zip aperto: 4 file validi + exe saltato, nascosti ignorati", b == [("concluso", 5, 4, 1)], str(b))
    ok("documenti creati per tutti", sql("SELECT count(*) FROM documenti WHERE per_tutti")[0][0] == 4)
    ok("motivo del file saltato registrato", "programma.exe" in json.dumps(c.get("/gestione/documenti-blocco", headers=H).json()))
    c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("nota.txt", b"Appunto veloce sul progetto Evidens e sul suo sviluppo."))])
    ok("stesso file non duplicato", sql("SELECT count(*) FROM documenti WHERE nome_file='nota.txt'")[0][0] == 1)
    ok("zip non valido rifiutato", c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("x.zip", b"non zip"))]).status_code == 422)
    ok("Carla non puo'", c.post("/gestione/documenti-blocco", headers=HC, files=[("file", ("n.txt", b"ciao ciao ciao"))]).status_code == 403)
    ok("fascia non valida", c.post("/gestione/documenti-blocco", headers=H, files=[("file", ("n.txt", b"ciao ciao ciao"))], data={"fascia_dati": "boh"}).status_code == 422)
    # --- relazioni ---
    with connessione() as cn:
        mv.indicizza(cn)
        n = mv.relaziona(cn)
        ok("relazioni trovate (auto1-auto2)", n >= 1, str(n))
        a1, a2, m1 = [sql("SELECT id FROM documenti WHERE nome_file=%s", (f,))[0][0] for f in ("auto1.txt", "auto2.txt", "mare.txt")]
        ok("auto1 correlato ad auto2, non al mare", mv.correlati(cn, marco, [a1]) == ["auto2.txt"], str(mv.correlati(cn, marco, [a1])))
        ok("seconda volta non ricalcola", mv.relaziona(cn) == 0)
        sql("UPDATE documenti SET per_tutti=FALSE WHERE id=%s", (a2,))
        ok("non suggerisce documenti che l'agente non vede", mv.correlati(cn, marco, [a1]) == [])
        sql("UPDATE documenti SET per_tutti=TRUE WHERE id=%s", (a2,))
        a = dict(sql_dict) if False else None
        ag = {**cn.execute("SELECT * FROM agenti WHERE id=%s", (marco,)).fetchone(), "fascia_fornitore": "riservato", "non_conservazione_attiva": True, "dpa_firmato": True}
        txt, usati, _e = memoria.contesto_documenti(cn, ag, "quanto costano poco")
        ok("l'agente riceve l'indicazione di piu' fonti", "Sullo stesso tema esistono anche" in txt and "auto" in txt, txt[:300])
    d = c.get("/gestione/memoria-vettoriale", headers=H).json()
    ok("la vista espone i collegamenti", d["relazioni"] >= 1)
    # --- giro ---
    copione[:] = [fine("Che relazione ha Renovatio con il Comune di Genova?\nA che punto e' il progetto Evidens?\nUna terza in piu'?")]
    r = c.post("/gestione/giro/avvia", headers=H)
    ok("giro avviato", r.status_code == 201, r.text[:200])
    v = c.get("/gestione/giro", headers=H).json()
    ok("al massimo 2 domande per agente, tutte brevi", v["aperto"] and 1 <= len(v["domande"]) and all(len(q["domanda"]) < 200 for q in v["domande"]) and sum(1 for q in v["domande"] if q["agente"] == "Aurora") <= 2, str(v["domande"]))
    ok("notifica a Lorenzo", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Giro di aggiornamento:%%'")[0][0] == 1)
    ok("non si avvia un secondo giro", c.post("/gestione/giro/avvia", headers=H).status_code == 409)
    q0 = v["domande"][0]["id"]
    ok("Carla non puo' rispondere", c.post(f"/gestione/giro/domande/{q0}/risposta", headers=HC, json={"risposta": "x"}).status_code == 403)
    ok("risposta registrata come fatto", c.post(f"/gestione/giro/domande/{q0}/risposta", headers=H, json={"risposta": "Siamo partner dal 2024 per il progetto Borghi"}).status_code == 200
       and sql("SELECT count(*) FROM fatti_condivisi WHERE testo LIKE '%%partner dal 2024%%'")[0][0] == 1)
    ok("non si risponde due volte", c.post(f"/gestione/giro/domande/{q0}/risposta", headers=H, json={"risposta": "x"}).status_code == 404)
    for q in c.get("/gestione/giro", headers=H).json()["domande"]:
        if q["stato"] == "attesa": c.post(f"/gestione/giro/domande/{q['id']}/salta", headers=H)
    ok("giro chiuso quando non restano domande", sql("SELECT stato FROM giri_aggiornamento")[0][0] == "chiuso")
    with connessione() as cn:
        ag = cn.execute("SELECT * FROM agenti WHERE id=%s", (leo,)).fetchone()
        blocco = giro_domande.fatti_per_agente(cn, "Parlami del Comune")
        ok("i fatti arrivano agli agenti", "partner dal 2024" in blocco, blocco[:200])
    ultimi_msg.clear(); copione[:] = [fine("ok")]
    c.post("/gestione/chat", headers=H, json={"agente_id": leo, "messaggio": "ciao"}) if False else None
    copione[:] = [fine("Che relazione ha Renovatio con il Comune di Genova?")]
    ok("domanda gia' posta non ripetuta", c.post("/gestione/giro/avvia", headers=H).status_code == 409)
    ok("aggiunta manuale di un fatto", c.post("/gestione/giro/fatti", headers=H, json={"testo": "Evidens ha chiuso il prototipo a ottobre"}).status_code == 201)
    fid = sql("SELECT id FROM fatti_condivisi WHERE testo LIKE 'Evidens ha chiuso%%'")[0][0]
    ok("fatto rimosso non arriva piu' agli agenti", c.delete(f"/gestione/giro/fatti/{fid}", headers=H).status_code == 200 and "prototipo" not in giro_domande.fatti_per_agente(connessione().__enter__(), "Evidens"))
    ok("frequenza impostabile", c.put("/gestione/giro/impostazioni", headers=H, json={"giorni": 3}).json()["giorni"] == 3 and c.put("/gestione/giro/impostazioni", headers=H, json={"giorni": 200}).status_code == 422)
    # automatico
    with connessione() as cn:
        sql("UPDATE giri_aggiornamento SET creato_il = NOW() - interval '10 days'")
        copione[:] = [fine("Chi decide sul budget di Marketing?")] * 8
        giro_domande.giro(cn)
        ok("giro automatico quando e' ora", sql("SELECT count(*) FROM giri_aggiornamento WHERE stato='aperto'")[0][0] == 1)
        giro_domande.giro(cn)
        ok("non ne apre un altro", sql("SELECT count(*) FROM giri_aggiornamento")[0][0] == 2)
        sql("UPDATE giri_aggiornamento SET creato_il = NOW() - interval '5 days' WHERE stato='aperto'")
        giro_domande.giro(cn)
        ok("giro dimenticato scade", sql("SELECT count(*) FROM domande_giro WHERE stato='attesa'")[0][0] == 0)
print("TOTALE", sum(ris), "/", len(ris))
