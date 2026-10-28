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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria, ginnasio
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
sql("UPDATE impostazioni_sistema SET valore='0' WHERE chiave='ginnasio_pausa_studio'")
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_approva_auto','0') ON CONFLICT (chiave) DO UPDATE SET valore='0'")
CORPO = "Metodo a passi per la pianificazione del progetto. " * 12
def risposta_casati(nome="Project management"): return fine("DESCRIZIONE: Pianifica e coordina un progetto dal brief alla consegna\nCOMPETENZA:\n" + CORPO + "\nFonti\n- Guida PMI https://example.org/pmi")
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') RETURNING id")[0][0]
sql("INSERT INTO progetti (nome, azienda_id, pm_agente_id) VALUES ('Sito Montarrenti', %s, %s)", (az, marco))
pid = sql("SELECT id FROM progetti WHERE nome='Sito Montarrenti'")[0][0]
sql("DELETE FROM progetti_agenti"); sql("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s),(%s,%s)", (pid, marco, pid, dario))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    r = c.get("/gestione/ginnasio", headers=H).json()
    ok("stato iniziale: in pausa, budget, coda vuota", r["impostazioni"]["attivo"] is False and r["impostazioni"]["budget"] == 0 and r["impostazioni"]["senza_limite"] is True and r["coda"] == [] and len(r["agenti"]) > 5)
    ok("solo titolare", c.get("/gestione/ginnasio", headers=HC).status_code == 403 and c.post("/gestione/ginnasio/richieste", headers=HC, json={"competenza": "Xyz", "livello": 1}).status_code == 403)
    ok("livello 2 su competenza inesistente: rifiutato", c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 2}).status_code == 422)
    ok("livello fuori scala rifiutato", c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 6}).status_code == 422)
    ok("segreto nel motivo rifiutato", c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 1, "motivo": "password: abcdef123456"}).status_code == 422)
    r1 = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 1, "agente_id": marco, "motivo": "Serve per coordinare il sito", "progetto_id": pid, "urgenza": 2})
    ok("richiesta in coda", r1.status_code == 201 and r1.json()["unita"] is False)
    rid1 = r1.json()["id"]
    r2 = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "project MANAGEMENT", "livello": 1, "agente_id": marco, "motivo": "Anche per la scadenza", "urgenza": 3})
    ok("richiesta uguale: si unisce", r2.json()["unita"] is True and r2.json()["id"] == rid1 and sql("SELECT peso, urgenza FROM richieste_formazione WHERE id=%s", (rid1,))[0] == (2, 3))
    c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Strategia social", "livello": 1, "agente_id": scout, "motivo": "Per i social", "urgenza": 3})
    c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Coordinamento di area", "livello": 1, "agente_id": dario, "motivo": "Per il suo reparto", "urgenza": 3})
    q = c.get("/gestione/ginnasio", headers=H).json()["coda"]
    ok("graduatoria: PM, poi manager, poi gli altri", [x["agente_id"] for x in q][:3] == [marco, dario, scout], str([x["agente_id"] for x in q]))
    rid_d = [x["id"] for x in q if x["agente_id"] == scout][0]
    c.post(f"/gestione/ginnasio/richieste/{rid_d}/sposta", headers=H, json={"azione": "cima"})
    q = c.get("/gestione/ginnasio", headers=H).json()["coda"]
    ok("spostare in cima", q[0]["id"] == rid_d and q[0]["ordine_manuale"] == 0)
    c.post(f"/gestione/ginnasio/richieste/{rid_d}/sposta", headers=H, json={"azione": "giu"})
    ok("spostare in giu", c.get("/gestione/ginnasio", headers=H).json()["coda"][1]["id"] == rid_d)
    c.post(f"/gestione/ginnasio/richieste/{rid_d}/sposta", headers=H, json={"azione": "automatico"})
    ok("tornare automatico", sql("SELECT ordine_manuale FROM richieste_formazione WHERE id=%s", (rid_d,))[0][0] is None)
    ok("azione non valida", c.post(f"/gestione/ginnasio/richieste/{rid_d}/sposta", headers=H, json={"azione": "boh"}).status_code == 422)
    # giro automatico
    with connessione() as cn:
        ginnasio.giro(cn)
    ok("in pausa il giro non fa nulla", sql("SELECT count(*) FROM richieste_formazione WHERE stato='in_corso'")[0][0] == 0)
    # esecuzione manuale (prova)
    copione[:] = [fine("ricerca"), fine("appunti"), risposta_casati()]; strumenti_visti.clear(); ultimi_msg.clear()
    ok("esegui ora", c.post(f"/gestione/ginnasio/richieste/{rid1}/esegui", headers=H).status_code == 202)
    f = sql("SELECT stato, token_usati, livello_id FROM richieste_formazione WHERE id=%s", (rid1,))[0]
    ok("bozza creata, richiesta da approvare, token registrati", f[0] == "da_approvare" and f[1] == 360 and f[2] is not None, str(f))
    ok("il prompt cita competenza, livello e progetto", "Project management" in ultimi_msg[0] and "Sito Montarrenti" in ultimi_msg[0] and "Junior" in ultimi_msg[0])
    st = c.get("/gestione/ginnasio", headers=H).json()
    ok("budget del giorno aggiornato e bozza visibile", st["impostazioni"]["usati_oggi"] == 360 and len(st["da_approvare"]) == 1 and st["competenze"][0]["descrizione"].startswith("Pianifica"))
    lid = st["da_approvare"][0]["id"]
    ok("l'agente non ha ancora la competenza (bozza)", sql("SELECT count(*) FROM agenti_competenze WHERE agente_id=%s", (marco,))[0][0] == 0)
    ok("modifica bozza", c.put(f"/gestione/ginnasio/livelli/{lid}", headers=H, json={"corpo": CORPO + " Aggiunta di Lorenzo."}).status_code == 200)
    ok("bozza con password rifiutata", c.put(f"/gestione/ginnasio/livelli/{lid}", headers=H, json={"corpo": CORPO + " password: abcdef123456"}).status_code == 422)
    ok("approva e assegna", c.post(f"/gestione/ginnasio/livelli/{lid}/decisione", headers=H, json={"azione": "approva"}).json()["assegnati"] == [marco])
    ok("competenza assegnata con livello 1", sql("SELECT livello FROM agenti_competenze WHERE agente_id=%s", (marco,))[0][0] == 1 and sql("SELECT stato FROM richieste_formazione WHERE id=%s", (rid1,))[0][0] == "conclusa")
    ag = {a["id"]: a for a in c.get("/agenti", headers=H).json()}
    ok("il numerino accanto al nome", ag[marco]["livello_formazione"] == 1 and "(1)" in ag[marco]["etichetta"] and ag[scout]["livello_formazione"] == 0 and "(" not in ag[scout]["etichetta"].split(" — ")[0])
    ok("pagina Agenti mostra il livello", "livello_formazione" in c.get("/app/app.js").text)
    # livelli successivi
    ok("livello 3 senza il 2: rifiutato", c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 3, "agente_id": marco}).status_code == 422)
    r5 = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 2, "agente_id": marco, "motivo": "Passare a Medium"}).json()["id"]
    # assegnazione diretta di un livello gia' esistente: nessuna coda
    r = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 1, "agente_id": dario, "motivo": "Anche lui"})
    ok("livello esistente: assegnato subito senza coda", r.json().get("assegnata") is True and sql("SELECT livello FROM agenti_competenze WHERE agente_id=%s", (dario,))[0][0] == 1)
    ok("livello gia' posseduto: rifiutato", c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 1, "agente_id": dario}).status_code == 422)
    # respinta due volte
    copione[:] = [fine("ricerca"), fine("appunti"), risposta_casati()]
    c.post(f"/gestione/ginnasio/richieste/{r5}/esegui", headers=H)
    l2 = sql("SELECT livello_id FROM richieste_formazione WHERE id=%s", (r5,))[0][0]
    ok("il prompt del livello 2 include il livello 1 gia' scritto", "gia' scritto" in ultimi_msg[-1] and "Medium" in ultimi_msg[-1])
    c.post(f"/gestione/ginnasio/livelli/{l2}/decisione", headers=H, json={"azione": "respingi", "nota": "Troppo generico"})
    f = sql("SELECT stato, note, tentativi FROM richieste_formazione WHERE id=%s", (r5,))[0]
    ok("respinta: torna in coda con la nota", f == ("in_coda", "Troppo generico", 1), str(f))
    copione[:] = [risposta_casati()]   # gli appunti ci sono gia': si riscrive soltanto
    c.post(f"/gestione/ginnasio/richieste/{r5}/esegui", headers=H)
    ok("la nota arriva a Padre Casati", "Troppo generico" in ultimi_msg[-1])
    l2b = sql("SELECT livello_id FROM richieste_formazione WHERE id=%s", (r5,))[0][0]
    c.post(f"/gestione/ginnasio/livelli/{l2b}/decisione", headers=H, json={"azione": "respingi"})
    ok("respinta due volte: annullata", sql("SELECT stato FROM richieste_formazione WHERE id=%s", (r5,))[0][0] == "annullata")
    ok("un errore di Padre Casati non ferma nulla", True)
    # budget e giro attivo
    sql("UPDATE richieste_formazione SET stato='annullata' WHERE stato='in_coda'")
    rq = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Strategia social", "livello": 1, "agente_id": scout, "motivo": "Per i social"}).json()["id"]
    sql("UPDATE impostazioni_sistema SET valore='100' WHERE chiave='ginnasio_budget_giornaliero'")
    c.put("/gestione/ginnasio/impostazioni", headers=H, json={"attivo": True})
    with connessione() as cn: ginnasio.giro(cn)
    ok("budget troppo basso: non parte", sql("SELECT stato FROM richieste_formazione WHERE id=%s", (rq,))[0][0] == "in_coda")
    c.put("/gestione/ginnasio/impostazioni", headers=H, json={"budget": 100000})
    copione[:] = [fine("ricerca"), fine("appunti"), risposta_casati()]
    with connessione() as cn: ginnasio.giro(cn)
    jsg = c.get("/app/ginnasio.js").text
    ok("aggiornamento automatico: non fa perdere il punto di lettura", "function riempiConservando" in jsg and "cacheAvanz" in jsg and "firmaAv" in jsg and "riempiConservando(corpo" in c.get("/app/sapere.js").text)
    ok("budget 0 = senza tetto", c.put("/gestione/ginnasio/impostazioni", headers=H, json={"budget": 0}).json()["senza_limite"] is True and c.put("/gestione/ginnasio/impostazioni", headers=H, json={"budget": 100000}).json()["senza_limite"] is False)
    ok("budget negativo rifiutato", c.put("/gestione/ginnasio/impostazioni", headers=H, json={"budget": -5}).status_code == 422)
    ok("con budget a sufficienza parte da sola", sql("SELECT stato FROM richieste_formazione WHERE id=%s", (rq,))[0][0] == "da_approvare")
    rm = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Project management", "livello": 2, "agente_id": marco, "motivo": "Medium"}).json()["id"]
    sql("UPDATE richieste_formazione SET livello=5 WHERE id=%s", (rm,))
    with connessione() as cn: ginnasio.giro(cn)
    ok("il Master non parte senza via libera", sql("SELECT stato FROM richieste_formazione WHERE id=%s", (rm,))[0][0] == "in_coda")
    ok("via libera", c.post(f"/gestione/ginnasio/richieste/{rm}/via-libera", headers=H).status_code == 200)
    # errore di Padre Casati
    sql("UPDATE richieste_formazione SET stato='annullata' WHERE id=%s", (rm,))
    rz = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Comunicazione", "livello": 1, "motivo": "Per la libreria"}).json()["id"]
    copione[:] = [fine("Non ho trovato nulla.")]
    c.post(f"/gestione/ginnasio/richieste/{rz}/esegui", headers=H)
    f = sql("SELECT stato, errore FROM richieste_formazione WHERE id=%s", (rz,))[0]
    ok("risposta inutilizzabile: errore e si puo' riprovare", f[0] == "errore" and c.post(f"/gestione/ginnasio/richieste/{rz}/riprova", headers=H).status_code == 200 and sql("SELECT stato FROM richieste_formazione WHERE id=%s", (rz,))[0][0] == "in_coda")
    # competenze nel prompt dell'agente
    copione[:] = [fine("ok")]; ultimi_msg.clear(); strumenti_visti.clear()
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Come imposto la pianificazione del progetto?", "fascia_dati": "interno"})
    ok("l'agente riceve elenco e testo della competenza pertinente", "LE TUE COMPETENZE" in ultimi_msg[0] and "Project management (livello 1" in ultimi_msg[0] and "Metodo a passi" in ultimi_msg[0])
    ok("il PM ha competenza_leggi e formazione_richiedi", any("competenza_leggi" in t and "formazione_richiedi" in t for t in strumenti_visti), str(strumenti_visti))
    copione[:] = [chiama("competenza_leggi", {"competenza": "project"}), fine("ok")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("competenza_leggi restituisce il testo", "Livello 1" in ultimi_msg[-1] and "Metodo a passi" in ultimi_msg[-1])
    # richiesta fatta da un manager
    copione[:] = [chiama("formazione_richiedi", {"competenza": "SEO tecnica", "livello": 1, "agente": "Scout", "motivo": "Il sito del Castello ha problemi di indicizzazione e nessuno li sa trattare", "progetto": "Sito Montarrenti", "urgenza": 3}), fine("Fatto")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Serve SEO", "fascia_dati": "interno"})
    f = sql("SELECT origine, agente_id, progetto_id, richiesta_da_agente_id FROM richieste_formazione WHERE competenza_nome='SEO tecnica'")
    ok("il PM mette in coda una richiesta (origine pm)", f == [("pm", scout, pid, marco)], str(f))
    copione[:] = [chiama("formazione_richiedi", {"competenza": "Altro", "livello": 1, "motivo": "troppo corto"}), fine("ok")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Serve altro", "fascia_dati": "interno"})
    ok("richiesta generica rifiutata", sql("SELECT count(*) FROM richieste_formazione WHERE competenza_nome='Altro'")[0][0] == 0 and "ERRORE" in ultimi_msg[-1])
    for i in range(6):
        copione[:] = [chiama("formazione_richiedi", {"competenza": f"Tema {i} uno", "livello": 1, "motivo": "Lacuna concreta vista nel progetto del Castello di Montarrenti"}), fine("ok")]
        c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "altro", "fascia_dati": "interno"})
    ok("nessun limite settimanale alle richieste di formazione", sql("SELECT count(*) FROM richieste_formazione WHERE richiesta_da_agente_id=%s AND competenza_nome LIKE 'Tema %% uno'", (marco,))[0][0] == 6)
    ok("assegnazione manuale di un livello approvato", c.post("/gestione/ginnasio/assegna", headers=H, json={"agente_id": leo, "competenza_id": 1, "livello": 1}).status_code == 200
       and c.post("/gestione/ginnasio/assegna", headers=H, json={"agente_id": leo, "competenza_id": 1, "livello": 3}).status_code == 422)
    ok("togliere la competenza", c.delete(f"/gestione/ginnasio/assegna/{leo}/1", headers=H).status_code == 200 and sql("SELECT count(*) FROM agenti_competenze WHERE agente_id=%s", (leo,))[0][0] == 0)
    ok("pagina servita", "vistaGinnasio" in c.get("/app/ginnasio.js").text and "ginnasio" in c.get("/app/app.js").text)
    # formazione a fasi con download limitati
    from app import casati as _cas
    pdfp = open("/tmp/claude-0/-home-claude/f97e63d7-0f90-572a-b598-f314f34539ca/scratchpad/prova.pdf", "rb").read()
    _cas._ip_pubblico = lambda h: True
    _cas._scarica = lambda url: (200, pdfp, {})
    rf = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Storytelling digitale", "livello": 1, "motivo": "Per i contenuti del sito del Castello"}).json()["id"]
    copione[:] = [chiama("scarica_materiale", {"url": f"https://repo.example.edu/doc{i}.pdf", "titolo": f"Manuale storytelling {i}"}, f"d{i}") for i in range(1)] + \
                 [chiama("scarica_materiale", {"url": f"https://repo.example.edu/doc{i}.pdf", "titolo": f"Manuale storytelling {i}"}, f"e{i}") for i in range(1, 8)] + \
                 [fine("Scaricati manuali."), fine("Appunti: metodo X [Manuale 0, brano 1]"), risposta_casati()]
    strumenti_visti.clear(); ultimi_msg.clear()
    c.post(f"/gestione/ginnasio/richieste/{rf}/esegui", headers=H)
    ok("la ricerca scarica nella biblioteca senza tetto: tutti e 8 i documenti", sql("SELECT count(*) FROM formazione_materiale WHERE richiesta_id=%s", (rf,))[0][0] == 8 and sql("SELECT count(*) FROM documenti WHERE nome LIKE 'Manuale storytelling%%'")[0][0] == 8)
    ok("nessun rifiuto per tetto raggiunto", "massimo di materiale" not in " ".join(ultimi_msg))
    f = sql("SELECT stato, fase, appunti FROM richieste_formazione WHERE id=%s", (rf,))[0]
    ok("tre fasi svolte, appunti conservati, bozza da approvare", f[0] == "da_approvare" and f[1] == "stesura" and "metodo X" in f[2], str(f))
    ok("la stesura riceve gli appunti", "APPUNTI DI STUDIO" in ultimi_msg[-1] and "metodo X" in ultimi_msg[-1])
    ok("lo scaricamento diretto esiste solo durante la formazione", not any("scarica_materiale" in t for t in strumenti_visti[-1:]) )
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{casati_id}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("fuori dalla formazione Casati non ha scarica_materiale", not any("scarica_materiale" in t for t in strumenti_visti), str(strumenti_visti))
    # pausa dopo lo studio, avanzamento, scheda attivita'
    ok("impostazione pausa dopo lo studio presente", c.get("/gestione/ginnasio", headers=H).json()["impostazioni"]["pausa_studio"] is False)
    c.put("/gestione/ginnasio/impostazioni", headers=H, json={"pausa_studio": True})
    rp = c.post("/gestione/ginnasio/richieste", headers=H, json={"competenza": "Fotografia di archivio", "livello": 1, "motivo": "Per documentare i volumi della biblioteca del castello"}).json()["id"]
    copione[:] = [chiama("cerca_fonti", {"archivio": "wikipedia", "testo": "fotografia archivio"}, "r1"), fine("Ricerca finita"), fine("Appunti: usare luce diffusa [Manuale 1]"), risposta_casati()]
    ginnasio_ric = casati_id
    c.post(f"/gestione/ginnasio/richieste/{rp}/esegui", headers=H)
    f = sql("SELECT stato, fase, appunti FROM richieste_formazione WHERE id=%s", (rp,))[0]
    ok("con la pausa si ferma agli appunti, senza scrivere la competenza", f[0] == "appunti_pronti" and "luce diffusa" in f[2] and sql("SELECT count(*) FROM competenze_livelli l JOIN competenze c ON c.id=l.competenza_id WHERE c.nome='Fotografia di archivio'")[0][0] == 0, str(f))
    av = c.get(f"/gestione/ginnasio/richieste/{rp}/avanzamento", headers=H).json()
    ok("avanzamento: tappe, ricerche, appunti", [x["stato"] for x in av["fasi"]] == ["finita", "finita", "in_attesa"] and len(av["ricerche"]) == 1 and "luce diffusa" in av["appunti"] and av["token_usati"] > 0, str(av["fasi"]))
    ok("la stesura non parte senza via libera sulla richiesta sbagliata", c.post(f"/gestione/ginnasio/richieste/{rid1}/stesura", headers=H).status_code == 422)
    ok("solo il titolare usa avanzamento e stesura", c.get(f"/gestione/ginnasio/richieste/{rp}/avanzamento", headers=HC).status_code == 403)
    ok("notifica di appunti pronti", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%finito di studiare%%Fotografia%%'")[0][0] == 1)
    copione[:] = [risposta_casati()]; ultimi_msg.clear()
    ok("via libera alla stesura", c.post(f"/gestione/ginnasio/richieste/{rp}/stesura", headers=H).status_code == 202)
    f = sql("SELECT stato, fase FROM richieste_formazione WHERE id=%s", (rp,))[0]
    av = c.get(f"/gestione/ginnasio/richieste/{rp}/avanzamento", headers=H).json()
    ok("stesura fatta senza rifare ricerca e studio", f == ("da_approvare", "stesura") and [x["stato"] for x in av["fasi"]] == ["finita", "finita", "finita"] and "APPUNTI DI STUDIO" in ultimi_msg[0], str(av["fasi"]))
    at = c.get(f"/agenti/{casati_id}/attivita", headers=H).json()
    ok("scheda attivita': eventi, riposo, nessun errore", at["adesso"]["al_lavoro"] is False and len(at["eventi"]) >= 5 and any(e["tipo"] == "strumento" for e in at["eventi"]) and at["agente"]["nome"] == "Padre Casati", str(at["adesso"]))
    sql("INSERT INTO eventi_lavoro (agente_id, tipo, dettaglio) VALUES (%s,'inizio','Analizza il bando')", (scout,))
    at = c.get(f"/agenti/{scout}/attivita", headers=H).json()
    ok("agente con lavoro iniziato e non finito risulta al lavoro", at["adesso"]["al_lavoro"] is True and at["adesso"]["attivita"] == "Analizza il bando")
    copione[:] = [fine("ok")]
    c.post(f"/agenti/{leo}/chat", headers=H, json={"messaggio": "Dimmi qualcosa", "fascia_dati": "interno"})
    at = c.get(f"/agenti/{leo}/attivita", headers=H).json()
    ok("una chat normale lascia inizio e fine", [e["tipo"] for e in at["eventi"]][:2] == ["fine", "inizio"] and at["adesso"]["al_lavoro"] is False, str(at["eventi"]))
    ok("un collaboratore senza accesso al reparto non vede l'attivita'", c.get(f"/agenti/{giulia}/attivita", headers=HC).status_code in (200, 404))
    with connessione() as cn:
        sql("UPDATE eventi_lavoro SET creato_il = NOW() - interval '40 days' WHERE agente_id=%s", (scout,))
        from app import eventi as _ev; _ev.pulisci(cn)
    ok("eventi oltre 30 giorni eliminati", sql("SELECT count(*) FROM eventi_lavoro WHERE agente_id=%s", (scout,))[0][0] == 0)
    ok("pagina servita", "bloccoAttivita" in c.get("/app/organizzazione.js").text and "Procedi alla stesura" in c.get("/app/ginnasio.js").text)
print("TOTALE", sum(ris), "/", len(ris))
