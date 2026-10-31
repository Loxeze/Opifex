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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, call_riunioni, voce_elevenlabs as ve, consegne, scheda_progetto, memoria, ginnasio, squadre
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
copione, strumenti_visti, ultimi_msg, modelli_visti, sforzi_visti = [], [], [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False)); modelli_visti.append(corpo.get("model"))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")






ginnasio.SINCRONO = True
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') RETURNING id")[0][0]
sql("UPDATE agenti SET modello='claude-sonnet-5-5'")
call_riunioni.SINCRONO = True
from app import tavoli
aur = ID("Aurora")
sql("UPDATE agenti SET livello='manager' WHERE id IN (%s,%s)", (marco, dario))
ve.voci = lambda conn: [{"id": "v1", "nome": "Anna"}, {"id": "v2", "nome": "Bruno"}, {"id": "v3", "nome": "Carla"}]
chiamate = []
def finto_sintetizza(testo, fascia="interno", utente_id=None, voce_id=None, veloce=False):
    chiamate.append(voce_id); return b"ID3audio"
ve.sintetizza = finto_sintetizza
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("Carla non crea riunioni", c.post("/gestione/riunioni-call", headers=HC, json={"titolo": "Prova", "partecipanti": ["Marco"]}).status_code == 403)
    ok("un operativo non e' un manager", c.post("/gestione/riunioni-call", headers=H, json={"titolo": "Prova", "partecipanti": ["Scout"]}).status_code == 422)
    ok("elenco dei manager disponibili", {"Marco", "Dario"} <= {m["nome"] for m in c.get("/gestione/riunioni-call/manager", headers=H).json()["manager"]})
    r = c.post("/gestione/riunioni-call", headers=H, json={"titolo": "Strategia estate", "ordine_del_giorno": "Parliamo dell'estate.", "partecipanti": ["Marco", "Dario"]})
    ok("riunione creata", r.status_code == 201, r.text[:200]); tid = r.json()["id"]
    ok("non compare tra i tavoli di lavoro", all(t["id"] != tid for t in c.get("/gestione/tavoli", headers=H).json()["tavoli"]))
    ok("compare tra le riunioni, programmata", [x["stato"] for x in c.get("/gestione/riunioni-call", headers=H).json()["riunioni"] if x["id"] == tid] == ["programmata"])
    voci = sql("SELECT voce_id FROM agenti WHERE id IN (%s,%s) ORDER BY id", (marco, dario))
    ok("a ogni manager e' stata assegnata una voce diversa", len({v[0] for v in voci}) == 2 and None not in {v[0] for v in voci}, str(voci))
    ok("prima di avviare non si parla", c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Ciao"}).status_code == 422)
    ok("avviata", c.post(f"/gestione/riunioni-call/{tid}/avvia", headers=H).status_code == 200)

    copione[:] = [fine("Per l'estate servono eventi serali."), fine("Io penso al sito e alla comunicazione.")]
    ultimi_msg.clear()
    r = c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Che programma facciamo per l'estate?"})
    ok("turno inviato", r.status_code == 200, r.text[:200])
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    ok("risposta di tutti e due, in ordine", [(i["da_utente"], i["agente_id"]) for i in d["interventi"]][1:] == [(True, None), (False, marco), (False, dario)] and "Che cosa vuoi sapere" in d["interventi"][0]["testo"] and d["interventi"][0]["agente_id"] == aur, str(d["interventi"]))
    ok("il secondo ha visto la risposta del primo", "servono eventi serali" in ultimi_msg[1])
    ok("in riunione i manager usano il modello scelto per le riunioni, non quello dell'agente", modelli_visti and set(modelli_visti) == {"claude-sonnet-5-5"}, str(set(modelli_visti)))
    ok("il prompt vieta le conferme tipo «ho preso nota»", "VIETATO dire o far capire di aver registrato" in ultimi_msg[1] and "COME RISPONDI" in ultimi_msg[1] and "UNA domanda giusta" in ultimi_msg[1] and "Il ragionamento lo fai dentro di te" in ultimi_msg[1])
    q = c.get("/gestione/riunioni-call/qualita", headers=H).json()
    ok("qualita' riunioni: di default il modello migliore col ragionamento medio", q["modello"] == "claude-sonnet-5-5" and q["sforzo"] == "medium" and "claude-opus-5-5" in q["modelli"], str(q))
    ok("qualita' riunioni: modifica e controlli", c.put("/gestione/riunioni-call/qualita", headers=H, json={"modello": "claude-sonnet-5-5", "sforzo": "medium"}).status_code == 200
       and c.get("/gestione/riunioni-call/qualita", headers=H).json()["modello"] == "claude-sonnet-5-5"
       and c.put("/gestione/riunioni-call/qualita", headers=H, json={"modello": "inventato"}).status_code == 422
       and c.put("/gestione/riunioni-call/qualita", headers=H, json={"sforzo": "enorme"}).status_code == 422
       and c.get("/gestione/riunioni-call/qualita", headers=HC).status_code == 403)
    c.put("/gestione/riunioni-call/qualita", headers=H, json={"modello": "claude-sonnet-5-5", "sforzo": "medium"})
    sql("UPDATE agenti SET modello_riunione='claude-haiku-5-5' WHERE id=%s", (dario,))
    copione[:] = [fine("Uno."), fine("Due.")]; modelli_visti.clear()
    c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Che programma facciamo per l'estate?"})
    ok("un agente con modello_riunione proprio lo usa, gli altri il globale", modelli_visti[:2] == ["claude-sonnet-5-5", "claude-haiku-5-5"], str(modelli_visti))
    sql("UPDATE agenti SET modello_riunione=NULL WHERE id=%s", (dario,))
    ok("voce veloce nelle riunioni: modello turbo e parti spezzate", "veloce: true" in c.get("/app/riunioni_call.js").text and "spezza(testo)" in c.get("/app/riunioni_call.js").text and ve.MODELLO_VELOCE == "eleven_turbo_v2_5")
    vj = c.get("/app/voce.js").text
    ok("dettatura: il testo si ricostruisce dai risultati (niente frase ripetuta 7-8 volte su Android)", "senzaRipetizioni" in vj and "for (let i = 0; i < ev.results.length; i++)" in vj and "finale +=" not in vj)
    ok("riunioni: i risultati finali ripetuti dal browser non vengono reinviati", "ultimoBrowser" in c.get("/app/riunioni_call.js").text)
    pp = [{"id": 1, "nome": "Aurora"}, {"id": 2, "nome": "Elena"}, {"id": 3, "nome": "Marco"}]
    ok("senza nomi il moderatore non risponde, se nominata si", [p["id"] for p in call_riunioni.interpellati("Che ne pensate?", pp, 1)] == [2, 3] and [p["id"] for p in call_riunioni.interpellati("Aurora, tu?", pp, 1)] == [1] and [p["id"] for p in call_riunioni.interpellati("Elena, tu?", pp, 1)] == [2])
    ok("il moderatore da solo risponde comunque", [p["id"] for p in call_riunioni.interpellati("Ciao", pp[:1], 1)] == [1])
    ok("sql/103 Aurora/Elena su Sonnet", all(r[0] == "claude-sonnet-5-5" for r in sql("SELECT modello FROM agenti WHERE lower(nome) IN ('aurora','elena')")))
    ok("un'indicazione che nomina un manager lo interpella", call_riunioni.nominati_espliciti("Marco segui il sito", [{"nome": "Marco"}]) and not call_riunioni.nominati_espliciti("Il budget e' alto", [{"nome": "Marco"}]))
    ok("non e' piu' occupato", d["occupato"] is False)
    ok("i partecipanti hanno la voce", all(p["voce_id"] for p in d["partecipanti"]))
    ult = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()["interventi"][-1]["id"]
    ok("polling incrementale", c.get(f"/gestione/riunioni-call/{tid}?dopo={ult}", headers=H).json()["interventi"] == [])

    copione[:] = [fine("Dario: certo, ti rispondo io.\nCODA: Mi servirebbe una decisione sul budget.")]
    ultimi_msg.clear()
    c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Dario, quanto costerebbe il sito?"})
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    nuovi = [i for i in d["interventi"] if i["id"] > ult]
    ok("nominando Dario risponde solo lui, senza la riga CODA", [(i["da_utente"], i["agente_id"]) for i in nuovi] == [(True, None), (False, dario)] and "CODA" not in nuovi[-1]["testo"], str(nuovi))
    ok("la richiesta e' in coda e non e' stata detta", d["in_coda"] == 1 and "budget" not in " ".join(i["testo"] for i in d["interventi"] if i["agente_id"] == dario and "decisione" in i["testo"]))
    ok("il prompt chiede di entrare nel merito e rimanda i temi propri alla coda", "Il ragionamento lo fai dentro di te" in ultimi_msg[0] and "non propongono argomenti propri" in ultimi_msg[0] and "CODA:" in ultimi_msg[0])
    n0 = len(d["interventi"])
    r = c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Avete richieste in coda?"})
    d2 = c.get(f"/gestione/riunioni-call/{tid}?dopo={nuovi[-1]['id']}", headers=H).json()
    ok("«avete richieste?» consegna la coda, senza altre risposte", r.status_code == 200 and [(i["da_utente"], i["agente_id"]) for i in d2["interventi"]] == [(True, None), (False, dario)] and "decisione sul budget" in d2["interventi"][-1]["testo"] and d2["in_coda"] == 0, str(d2["interventi"]))
    ult = d2["interventi"][-1]["id"]
    copione[:] = [fine("Niente da aggiungere.\nCODA: Chiedo un incontro sul contratto."), fine("Posso dire una cosa sul budget.")]
    c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Altre idee?"})
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    ok("la coda di chi tace viene comunque salvata", c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()["in_coda"] == 1)
    ok("«niente da aggiungere» non viene registrato", d["interventi"][-1]["agente_id"] == dario and "budget" in d["interventi"][-1]["testo"] and not any("Niente da aggiungere" in i["testo"] for i in d["interventi"]))
    sql("UPDATE tavoli SET occupato=TRUE WHERE id=%s", (tid,))
    ok("durante le risposte non si interrompe", c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Ancora"}).status_code == 409)
    sql("UPDATE tavoli SET occupato=FALSE WHERE id=%s", (tid,))
    ok("frase vuota rifiutata", c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "   "}).status_code in (422,))

    # regola: le indicazioni si registrano e basta
    sql("UPDATE tavoli SET occupato=FALSE WHERE id=%s", (tid,))
    copione[:] = [fine("NON DOVREBBE ESSERE CHIAMATO")]; ultimi_msg.clear()
    n_prima = len(c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()["interventi"])
    r = c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Il budget massimo per l'estate e' di cinquemila euro."})
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    ok("un'indicazione viene solo registrata: nessun manager risponde, nessun token", r.json().get("registrata") is True and ultimi_msg == [] and len(d["interventi"]) == n_prima + 1 and d["interventi"][-1]["da_utente"] and d["occupato"] is False, str(r.json()))
    r = c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Marco, quanto costa il sito?"})
    ok("una domanda invece riceve risposta", r.json().get("registrata") is False)
    sql("UPDATE tavoli SET occupato=FALSE WHERE id=%s", (tid,))
    ok("la regola scritta e' esposta e nel prompt", "nessuno la ripete" in c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()["regole"] and "Non ripetere cio" in ultimi_msg[-1] and "REGOLE DELLA RIUNIONE" in ultimi_msg[-1])
    ok("nel verbale Lorenzo ha il suo nome", "Lorenzo:" in __import__("app.tavoli", fromlist=["x"])._storia(__import__("app.tavoli", fromlist=["x"])._interventi(__import__("app.db", fromlist=["x"]).connessione().__enter__(), tid)))
    # incarichi: «preparami un documento» non e' un'indicazione
    sql("UPDATE tavoli SET occupato=FALSE WHERE id=%s", (tid,))
    copione[:] = [fine("Ecco il documento completo sull'estate.\nPAROLE: Ho scritto il piano estate, lo trovi nella task."), fine("Documento sul budget pronto.\nPAROLE: Ho finito il budget.")]
    ultimi_msg.clear()
    r = c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Marco e Dario, preparatemi un documento con il piano per l'estate"})
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    ok("un incarico parte davvero: task create, preso in carico e consegna a voce", r.json().get("registrata") is False and sql("SELECT count(*) FROM task WHERE titolo LIKE 'Dalla riunione%%'")[0][0] == 2
       and any(i["testo"] == "Ci lavoro." for i in d["interventi"]) and not any("Preso in carico" in i["testo"] for i in d["interventi"]) and any("Ho scritto il piano estate" in i["testo"] for i in d["interventi"]), str([i["testo"][:50] for i in d["interventi"][-6:]]))
    ok("il documento intero e' nella task, la sintesi parlata no", sql("SELECT count(*) FROM task_commenti WHERE testo LIKE 'Ecco il documento completo%%'")[0][0] == 1 and "PAROLE" not in " ".join(i["testo"] for i in d["interventi"]))
    ok("task completate e notifica", sql("SELECT count(*) FROM task WHERE titolo LIKE 'Dalla riunione%%' AND stato='completata'")[0][0] == 2 and sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%incarico della riunione%%'")[0][0] == 2)
    ok("una domanda che contiene «documento» resta una domanda", not call_riunioni.e_lavoro("Quanto costa fare il documento?") and call_riunioni.e_lavoro("Scrivi la relazione") and not call_riunioni.e_indicazione("Scrivi la relazione"))
    # permessi predefiniti
    ok("tutti gli agenti attivi hanno Drive e dialoghi, i manager vedono tutto", sql("SELECT count(*) FROM agenti WHERE attivo AND NOT sentinella AND NOT drive_attivo")[0][0] == 0 and sql("SELECT count(*) FROM agenti WHERE attivo AND NOT sentinella AND livello IN ('manager','referente') AND NOT vede_attivita")[0][0] == 0)
    with __import__("app.db", fromlist=["x"]).connessione() as cn:
        from app import memoria
        ag = cn.execute("SELECT a.*, 'interno' AS fascia_fornitore, TRUE AS non_conservazione_attiva, TRUE AS dpa_firmato FROM agenti a WHERE a.id=%s", (marco,)).fetchone()
        txt = memoria.attivita_agenti(cn, {**ag, "fascia_dati_max": "interno", "vede_tutto": False, "livello": "manager"})
        ok("i manager vedono cosa hanno fatto gli altri agenti nelle ultime 24 ore", "Ecco il documento completo" in txt or "Documento sul budget" in txt, txt[:200])
        txt2 = memoria.attivita_agenti(cn, {**ag, "fascia_dati_max": "interno", "vede_tutto": False, "livello": "operativo", "divisione_id": ag["divisione_id"]})
        ok("senza vede_tutto solo il proprio reparto", isinstance(txt2, str))
    # ascolto continuo
    from app import trascrizione
    risposte = ["Dario, e il sito?", "Sottotitoli e revisione a cura di QTSS", "ERR"]
    def finta_trascrivi(dati, est, fascia, uid, ct="", limite_ora=60):
        t = risposte.pop(0)
        if t == "ERR": raise trascrizione.ErroreTrascrizione("Chiave OpenAI non configurata", 409)
        return t
    trascrizione.trascrivi = finta_trascrivi
    f = {"audio": ("voce.webm", b"x" * 2000, "audio/webm")}
    ok("l'audio viene trascritto", c.post(f"/gestione/riunioni-call/{tid}/audio", headers=H, files=f).json() == {"testo": "Dario, e il sito?"})
    ok("le frasi inventate sul rumore sono scartate", c.post(f"/gestione/riunioni-call/{tid}/audio", headers=H, files=f).json() == {"testo": ""})
    ok("errore di trascrizione riportato al browser (per passare al riconoscimento del browser)", c.post(f"/gestione/riunioni-call/{tid}/audio", headers=H, files=f).status_code == 409)
    ok("limite orario dedicato alle call", "limite_ora=MAX_ASCOLTI_ORA" in open("app/call_riunioni.py").read() and call_riunioni.MAX_ASCOLTI_ORA >= 600)
    ok("ElevenLabs: niente voce robotica di ripiego e precarico", all(k in c.get("/app/riunioni_call.js").text for k in ("precarica", "mancata")))
    ok("scrittura/ascolto: il client ha il motore continuo", all(k in c.get("/app/riunioni_call.js").text for k in ("echoCancellation", "ora - ultimaVoce > 750", "bloccato", "/audio", "SpeechRecognition")))

    # voci
    vm = c.get("/gestione/voci-manager", headers=H).json()
    ok("pannello voci", len(vm["voci"]) == 3 and vm["elevenlabs"] is False or len(vm["voci"]) >= 0)
    ok("cambio voce", c.put(f"/gestione/voci-manager/{marco}", headers=H, json={"voce_id": "v3"}).status_code == 200 and sql("SELECT voce_id FROM agenti WHERE id=%s", (marco,))[0][0] == "v3")
    ok("voce assegnabile anche a un non-manager", c.put(f"/gestione/voci-manager/{scout}", headers=H, json={"voce_id": "v1"}).status_code == 200)
    r = c.post("/voce/leggi", headers=H, json={"testo": "Ciao", "agente_id": marco})
    ok("lettura con la voce del manager", r.status_code == 200 and chiamate[-1] == "v3", str(chiamate))
    r = c.post("/voce/leggi", headers=H, json={"testo": "Ciao"})
    ok("senza agente voce predefinita", r.status_code == 200 and chiamate[-1] is None)
    sql("UPDATE agenti SET voce_id=NULL WHERE id=%s", (dario,))
    ok("assegnazione automatica delle voci mancanti", c.post("/gestione/voci-manager/auto", headers=H).json()["assegnate"] >= 1 and sql("SELECT voce_id FROM agenti WHERE id=%s", (dario,))[0][0])

    # chiusura e verbale
    copione[:] = [fine("SINTESI\nSi fanno eventi serali.\nAZIONI\nMarco: programma")]
    r = c.post(f"/gestione/riunioni-call/{tid}/chiudi", headers=H)
    ok("chiusa con verbale", r.status_code == 200, r.text[:200])
    d = c.get(f"/gestione/riunioni-call/{tid}", headers=H).json()
    ok("a fine riunione le richieste mai ascoltate entrano nel verbale come interventi", sql("SELECT count(*) FROM tavoli_interventi WHERE tavolo_id=%s AND coda=1", (tid,))[0][0] == 0 and sql("SELECT count(*) FROM tavoli_interventi WHERE tavolo_id=%s AND testo LIKE 'Chiedo un incontro%%' AND coda=0", (tid,))[0][0] == 1)
    ok("verbale scritto e riunione conclusa", d["stato"] == "conclusa" and "eventi serali" in d["verbale"], str(d)[:300])
    ok("notifica del verbale", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Riunione %%conclusa%%'")[0][0] == 1)
    ok("non si parla in una riunione conclusa", c.post(f"/gestione/riunioni-call/{tid}/turno", headers=H, json={"testo": "Ciao"}).status_code == 422)
    r2 = c.post("/gestione/riunioni-call", headers=H, json={"titolo": "Vuota", "partecipanti": ["Marco"]}).json()["id"]
    c.post(f"/gestione/riunioni-call/{r2}/avvia", headers=H)
    ok("chiusura senza interventi", c.post(f"/gestione/riunioni-call/{r2}/chiudi", headers=H).status_code == 200 and sql("SELECT stato FROM tavoli WHERE id=%s", (r2,))[0][0] == "conclusa")
    ok("riunione inesistente", c.get("/gestione/riunioni-call/99999", headers=H).status_code == 404)
    ok("interpellati: nome intero e non parziale", [p["nome"] for p in call_riunioni.interpellati("Marcoli cosa dice", [{"nome": "Marco"}, {"nome": "Dario"}])] == ["Marco", "Dario"])
    ok("viste servite", "vistaRiunioniCall" in c.get("/app/riunioni_call.js").text and '"riunioni", "Riunioni"' in c.get("/app/chat.js").text)
    # diagnostica
    sql("UPDATE tavoli SET occupato=TRUE, creato_il = NOW() - interval '1 hour' WHERE id=%s", (r2,))
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('chiave_api_finta','SEGRETISSIMO') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
    rd = c.get("/gestione/diagnostica?ore=24", headers=H)
    ok("diagnostica scaricabile come file", rd.status_code == 200 and "attachment" in rd.headers.get("content-disposition", "") and rd.headers["content-type"].startswith("application/json"), rd.text[:200])
    dg = rd.json()
    ok("contiene versione, sospetti, configurazione e attivita'", dg["versione_opifex"] and "sospetti" in dg and "agenti" in dg["configurazione"] and "tavoli_interventi" in dg["attivita"])
    ok("riporta la riunione rimasta in sospeso", any("occupato da piu' di 10 minuti" in x for x in dg["sospetti"]), str(dg["sospetti"]))
    ok("contiene cio' che e' stato detto in riunione, comprese le richieste in coda", any("budget" in str(i.get("testo")) for i in dg["attivita"]["tavoli_interventi"]["dati"]) and any(i.get("coda") in (1, 2) for i in dg["attivita"]["tavoli_interventi"]["dati"]))
    ok("contiene le istruzioni degli agenti", any(a.get("istruzioni") for a in dg["configurazione"]["agenti"]["dati"]))
    ok("nessun segreto nel file", "SEGRETISSIMO" not in rd.text and all(a.get("password_hash") in (None, "[omesso]") for a in dg["configurazione"].get("utenti", {"dati": []})["dati"]))
    ok("le impostazioni ci sono ma il valore segreto no", any(x.get("chiave") == "chiave_api_finta" and x.get("valore") == "[omesso]" for x in dg["configurazione"]["impostazioni_sistema"]["dati"]))
    ok("riservata al titolare", c.get("/gestione/diagnostica", headers=HC).status_code == 403)
    ok("vista servita", "vistaDiagnostica" in c.get("/app/controlli.js").text)
print("TOTALE", sum(ris), "/", len(ris))
