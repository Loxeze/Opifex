import os, sys, json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import esecuzione, fornitori, cantiere, budget_prompt
from app.fornitori import Risposta, ErroreFornitore
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato'")

# finto Ollama: registra i prompt ricevuti; risponde secondo la scheda
LOC = {"prompt": [], "ctx": 8192, "risposte": {}, "giu": False}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/ps": self._j(200, {"models": [{"name": "nemo", "size": 1, "size_vram": 1, "context_length": LOC["ctx"]}]})
        else: self._j(200, {"models": [{"name": "nemo"}]})
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); corpo = json.loads(self.rfile.read(n) or b"{}")
        utente = [m for m in corpo["messages"] if m["role"] == "user"][-1]["content"]; sistema = corpo["messages"][0]["content"]
        LOC["prompt"].append({"utente": utente, "sistema": sistema, "strumenti": len(corpo.get("tools") or [])})
        testo = "Risposta semplice del modello locale, scritta per intero e senza schede."
        for chiave, val in LOC["risposte"].items():
            if chiave in utente:
                testo = val(utente) if callable(val) else val
        self._j(200, {"choices": [{"message": {"role": "assistant", "content": testo}, "finish_reason": "stop"}], "usage": {"prompt_tokens": max(1, (len(utente) + len(sistema)) // 3), "completion_tokens": 30}})
srv = HTTPServer(("127.0.0.1", 11557), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('locale_url','http://127.0.0.1:11557') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
sql("INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione) SELECT id,'nemo',0,0 FROM fornitori_ai WHERE nome='locale'")

# finto Claude (capocantiere e collaudatore)
ON = {"chiamate": [], "piano": None, "collaudo": [], "errore": False}
def finto_online(fornitore, modello, sistema, testo, max_token=1500, web=None):
    assert fornitore == "anthropic"
    if ON["errore"]: raise ErroreFornitore("giu'")
    if sistema.startswith("Sei il capocantiere"):
        ON["chiamate"].append(("piano", testo)); return Risposta(json.dumps(ON["piano"]), 300, 200, {})
    if "Riga 1 della risposta" in sistema:
        ON["chiamate"].append(("collaudo", testo)); return Risposta(ON["collaudo"].pop(0), 900, 400, {})
    ON["chiamate"].append(("assembla", testo)); return Risposta("Risposta finale assemblata dal collaudatore con i risultati corretti.", 800, 300, {})
cantiere.chiama_modello = finto_online

PIANO = {"semplice": False, "schede": [
    {"id": 1, "titolo": "Raccolta dei requisiti", "compito": "Elenca i requisiti del bando ALFA-UNO.", "dipende_da": [], "criteri": ["almeno tre requisiti"]},
    {"id": 2, "titolo": "Bozza del piano", "compito": "Scrivi la bozza del piano BETA-DUE usando i requisiti.", "dipende_da": [1], "criteri": ["cita i requisiti"]}]}
COMPITO = "Analizza il bando e prepara un piano di candidatura dettagliato per Renovatio, con requisiti, attivita' e tempi."

with TestClient(app) as c:
    ag = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    sql("UPDATE agenti SET modello='nemo', accesso_web=FALSE WHERE id=%s", (ag,))
    # --- prompt a budget
    b = [("panoramica", "P" * 3000), ("memoria", "M" * 2000), ("storia", "inizio " + "S" * 3000 + " FINE-STORIA"), ("kpi", "K" * 900)]
    scelti, omessi, acc = budget_prompt.componi(b, 4000)
    ok("budget: entra prima cio' che conta (conversazione, poi memoria accorciata), il contesto generale e' omesso", any("FINE-STORIA" in x for x in scelti) and acc == ["memoria"] and set(omessi) == {"kpi", "panoramica"}, str((omessi, acc)))
    scelti, omessi, acc = budget_prompt.componi(b, 1500)
    ok("budget: la conversazione si accorcia dalla testa, tenendo gli ultimi scambi", acc == ["storia"] and len(scelti) == 1 and scelti[0].endswith("FINE-STORIA") and scelti[0].startswith("[…inizio omesso") and len(scelti[0]) <= 1500, str((omessi, acc)))
    ok("budget: tutto entra se c'e' spazio, nell'ordine originale", budget_prompt.componi(b, 99999) == ([x[1] for x in b], [], []))
    ok("budget: la nota dice all'agente che cosa manca", "NON hai davanti" in budget_prompt.nota(["kpi"], ["storia"]) and "indicatori" in budget_prompt.nota(["kpi"], []))
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('cantiere_modo','spento') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
    lunga = "RIGA-INIZIALE " + ("dato importante numero. " * 2500) + " RIGA-FINALE"
    LOC["ctx"] = 16384; fornitori._FINESTRE.clear(); LOC["prompt"].clear()
    o = esecuzione.esegui_agente(ag, "Dimmi a che punto siamo.", "interno", None, allegati=[("relazione.txt", lunga)])
    pr = LOC["prompt"][-1]
    tot = (len(pr["utente"]) + len(pr["sistema"])) / 3
    az = sql("SELECT dettagli FROM registro_azioni WHERE agente_id=%s AND azione IN ('prompt_a_budget','passaggio_online_finestra') ORDER BY id DESC LIMIT 1", (ag,))
    ok("finestra piccola: il prompt viene composto a budget e registrato (nessun taglio silenzioso)", bool(az) and pr["utente"].rstrip().endswith("Dimmi a che punto siamo.") and "RIGA-INIZIALE" in pr["utente"] and "RIGA-FINALE" not in pr["utente"] and "finestra del modello" in pr["utente"], str(az)[:200] + f" tot={int(tot)}")
    ok("finestra piccola: il prompt composto sta nella finestra (stima prudente)", tot <= 16384, f"tot={int(tot)}")
    LOC["ctx"] = 131072; fornitori._FINESTRE.clear(); n_az = sql("SELECT count(*) FROM registro_azioni WHERE azione='prompt_a_budget'")[0][0]
    esecuzione.esegui_agente(ag, "Dimmi a che punto siamo.", "interno", None, allegati=[("relazione.txt", lunga)])
    ok("finestra grande: il prompt resta intero", sql("SELECT count(*) FROM registro_azioni WHERE azione='prompt_a_budget'")[0][0] == n_az)

    # essenziale che non entra: passa al modello online (se il dato puo' uscire), altrimenti resta in locale col minimo
    from app import agente_browser
    viste = []
    reale_es = agente_browser.esegui_con_strumenti
    agente_browser.esegui_con_strumenti = lambda modello, *a_, **k_: (viste.append(modello) or Risposta("Risposta del modello online", 50, 20, {}))
    LOC["ctx"] = 1024; fornitori._FINESTRE.clear(); LOC["prompt"].clear()
    o = esecuzione.esegui_agente(ag, "Dimmi a che punto siamo.", "interno", None)
    ok("nemmeno l'essenziale entra nella finestra: questo passaggio lo fa il modello online, ed e' registrato", viste == ["claude-sonnet-5-5"] and not LOC["prompt"] and o["risposta"] == "Risposta del modello online"
       and sql("SELECT count(*) FROM registro_azioni WHERE agente_id=%s AND azione='passaggio_online_finestra'", (ag,))[0][0] == 1 and sql("SELECT modello FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (ag,))[0][0] == "claude-sonnet-5-5")
    sql("UPDATE fornitori_ai SET fascia_dati_max='pubblico' WHERE nome='anthropic'"); viste.clear()
    o = esecuzione.esegui_agente(ag, "Dimmi a che punto siamo.", "interno", None)
    ok("se il dato non puo' uscire resta in locale, con il solo essenziale", not viste and len(LOC["prompt"]) == 1 and LOC["prompt"][0]["utente"].rstrip().endswith("Dimmi a che punto siamo."))
    sql("UPDATE fornitori_ai SET fascia_dati_max='riservato' WHERE nome='anthropic'")
    agente_browser.esegui_con_strumenti = reale_es; LOC["ctx"] = 131072; fornitori._FINESTRE.clear()

    # --- cantiere
    sql("UPDATE impostazioni_sistema SET valore='sempre' WHERE chiave='cantiere_modo'")
    ok("complessita': saluto no, compito articolato si'", not cantiere.sembra_complesso("ciao, come va?") and cantiere.sembra_complesso(COMPITO))
    ON["piano"] = {"semplice": True, "schede": []}; LOC["prompt"].clear()
    o = esecuzione.esegui_agente(ag, "Che ore sono?", "interno", None)
    ok("compito semplice per il capocantiere: l'agente lo svolge come sempre", "cantiere" not in o and len(LOC["prompt"]) == 1 and sql("SELECT count(*) FROM cantieri")[0][0] == 0)

    ON["piano"] = PIANO; ON["chiamate"].clear(); LOC["prompt"].clear(); n_son = sql("SELECT count(*) FROM costi_api WHERE modello='claude-sonnet-5-5'")[0][0]
    LOC["risposte"] = {"ALFA-UNO": "Requisiti: 1) sede in Italia; 2) ente del terzo settore; 3) cofinanziamento del venti per cento.",
                       "BETA-DUE": "Bozza del piano: attivita' in tre fasi, coerenti con i requisiti di sede, natura dell'ente e cofinanziamento."}
    ON["collaudo"] = ['{"schede": [{"id": 1, "ok": true}, {"id": 2, "ok": true}]}\n=== RISPOSTA ===\nPiano di candidatura completo, costruito sui requisiti verificati.']
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("cantiere: due schede svolte in locale, una alla volta", len(LOC["prompt"]) == 2 and "SCHEDA DI LAVORO 1 di 2" in LOC["prompt"][0]["utente"] and "SCHEDA DI LAVORO 2 di 2" in LOC["prompt"][1]["utente"], str(len(LOC["prompt"])))
    ok("cantiere: la seconda scheda riceve il risultato della prima", "cofinanziamento del venti per cento" in LOC["prompt"][1]["utente"] and "cofinanziamento" not in LOC["prompt"][0]["utente"])
    ok("cantiere: il collaudatore vede richiesta, criteri e risultati", ON["chiamate"][-1][0] == "collaudo" and "almeno tre requisiti" in ON["chiamate"][-1][1] and "Bozza del piano: attivita'" in ON["chiamate"][-1][1])
    ok("cantiere: risposta finale del collaudatore, con il piede che dice com'e' andata", o["risposta"].startswith("Piano di candidatura completo") and "collaudo superato" in o["risposta"] and o["cantiere_stato"] == "riuscito", o["risposta"][-200:])
    r = sql("SELECT stato, rifatte, token_online, jsonb_array_length(piano) FROM cantieri WHERE id=%s", (o["cantiere"],))[0]
    ok("cantiere: registrato con piano, esiti, token e costo online", r[0] == "riuscito" and r[1] == 0 and r[2] == 300 + 200 + 900 + 400 and r[3] == 2 and sql("SELECT count(*) FROM costi_api WHERE modello='claude-sonnet-5-5'")[0][0] == n_son + 2, str(r))
    ok("cantiere: solo due chiamate online (piano e collaudo con risposta)", [x[0] for x in ON["chiamate"]] == ["piano", "collaudo"])

    # scheda respinta: si rifa' con la correzione, poi si assembla
    ON["chiamate"].clear(); LOC["prompt"].clear()
    LOC["risposte"]["BETA-DUE"] = lambda u: ("Bozza corretta: il piano ora cita uno per uno i requisiti di sede, natura dell'ente e cofinanziamento." if "RESPINTO" in u else "Bozza del piano, generica e senza riferimenti ai requisiti richiesti.")
    ON["collaudo"] = ['{"schede": [{"id": 1, "ok": true}, {"id": 2, "ok": false, "problemi": "non cita i requisiti", "correzione": "Cita esplicitamente i tre requisiti."}]}']
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("collaudo respinge una scheda: viene rifatta una volta con la correzione", len(LOC["prompt"]) == 3 and "Cita esplicitamente i tre requisiti." in LOC["prompt"][2]["utente"] and "generica e senza riferimenti" in LOC["prompt"][2]["utente"])
    ok("dopo la correzione il collaudatore assembla con il risultato nuovo e i problemi segnalati", ON["chiamate"][-1][0] == "assembla" and "Bozza corretta" in ON["chiamate"][-1][1] and "non cita i requisiti" in ON["chiamate"][-1][1] or "Cita esplicitamente" in ON["chiamate"][-1][1])
    ok("cantiere con correzione: registrato «1 rifatta»", sql("SELECT rifatte FROM cantieri WHERE id=%s", (o["cantiere"],))[0][0] == 1 and "1 rifatte" in o["risposta"])

    # risposta vuota del locale: secondo tentativo immediato
    ON["chiamate"].clear(); LOC["prompt"].clear()
    LOC["risposte"]["ALFA-UNO"] = lambda u: ("Requisiti completi: sede in Italia, ente del terzo settore, cofinanziamento del venti per cento." if "RESPINTO" in u else "ok")
    LOC["risposte"]["BETA-DUE"] = "Bozza del piano che cita i requisiti di sede, natura dell'ente e cofinanziamento, in tre fasi."
    ON["collaudo"] = ['{"schede": [{"id": 1, "ok": true}, {"id": 2, "ok": true}]}\n=== RISPOSTA ===\nPiano finale.' + " Testo." * 10]
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("risultato troppo corto: rifatto subito, prima del collaudo", len(LOC["prompt"]) == 3 and "RESPINTO" in LOC["prompt"][1]["utente"] and o["cantiere_stato"] == "riuscito")

    # riserve dichiarate
    ON["chiamate"].clear(); LOC["risposte"]["ALFA-UNO"] = "Requisiti: sede in Italia, ente del terzo settore, cofinanziamento del venti per cento."
    ON["collaudo"] = ['{"schede": [{"id": 1, "ok": true}, {"id": 2, "ok": true}]}\n=== RISPOSTA ===\nPiano finale completo.\n\nDa verificare\n- la percentuale di cofinanziamento non risulta da un documento.']
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("punti incerti: esito «con riserve» e nota salvata", o["cantiere_stato"] == "con_riserve" and "con riserve" in o["risposta"] and "cofinanziamento" in sql("SELECT da_verificare FROM cantieri WHERE id=%s", (o["cantiere"],))[0][0])

    # verdetto illeggibile
    ON["chiamate"].clear(); ON["collaudo"] = ["non so"]
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("collaudo illeggibile: si assembla dichiarando che il lavoro va riletto", o["cantiere_stato"] == "con_riserve" and ON["chiamate"][-1][0] == "assembla" and "va riletto" in ON["chiamate"][-1][1])

    # modello online giu': il lavoro non si ferma
    ON["errore"] = True; LOC["prompt"].clear(); n_c = sql("SELECT count(*) FROM cantieri")[0][0]
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("capocantiere non raggiungibile: l'agente lavora da solo, senza errori", "cantiere" not in o and len(LOC["prompt"]) == 1 and sql("SELECT count(*) FROM cantieri")[0][0] == n_c)
    ON["errore"] = False

    # riservatezza: se i dati dell'agente non possono uscire, niente cantiere
    sql("UPDATE fornitori_ai SET fascia_dati_max='interno' WHERE nome='anthropic'"); ON["chiamate"].clear(); LOC["prompt"].clear()
    o = esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("agente che legge dati riservati e Claude solo «interno»: niente cantiere, nulla esce", "cantiere" not in o and not ON["chiamate"])
    sql("UPDATE fornitori_ai SET fascia_dati_max='riservato' WHERE nome='anthropic'")

    # modo automatico: solo da dove si affidano lavori, e solo se complesso; mai su agenti non locali
    sql("UPDATE impostazioni_sistema SET valore='auto' WHERE chiave='cantiere_modo'"); ON["chiamate"].clear()
    esecuzione.esegui_agente(ag, COMPITO, "interno", None)
    ok("modo automatico: una chiamata che non viene da chat o incarichi non apre il cantiere", not ON["chiamate"])
    from app import chat_coda
    ON["piano"] = PIANO; ON["collaudo"] = ['{"schede": [{"id": 1, "ok": true}, {"id": 2, "ok": true}]}\n=== RISPOSTA ===\nFatto tutto.' + " Bene." * 10]
    exec("def _prova(ag, testo):\n    from app import cantiere as c_\n    return c_.da_usare(ag, testo, 'interno', False)\n", chat_coda.__dict__)
    ok("modo automatico: dalla chat, compito complesso → cantiere; saluto → no", chat_coda._prova(ag, COMPITO) is not None and chat_coda._prova(ag, "ciao") is None)
    sql("UPDATE agenti SET modello='claude-haiku-5-5' WHERE id=%s", (ag,))
    sql("UPDATE impostazioni_sistema SET valore='sempre' WHERE chiave='cantiere_modo'"); ON["chiamate"].clear()
    ok("agente su modello online: il cantiere non serve", cantiere.da_usare(ag, COMPITO, "interno", False) is None)
    sql("UPDATE agenti SET modello='nemo' WHERE id=%s", (ag,))
    ok("a voce (risposta veloce): niente cantiere", cantiere.da_usare(ag, COMPITO, "interno", True) is None)
    # pannello
    from app.sicurezza import cifra_password
    from aiuto2fa import accedi
    sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
    Hd = {"Authorization": "Bearer " + accedi(c, "l@p.it", "PasswordLunga!2026")}
    e = c.get("/gestione/locale/cantieri", headers=Hd).json()
    ok("pannello: modo, ultimi lavori e riepilogo del mese", e["modo"] == "sempre" and len(e["ultimi"]) >= 5 and e["mese"]["n"] == len(e["ultimi"]) and e["mese"]["riserve"] >= 2 and e["mese"]["costo"] > 0, str(e["mese"]))
    d = c.get("/gestione/locale/cantieri/%d" % e["ultimi"][0]["id"], headers=Hd).json()
    ok("pannello: dettaglio con piano ed esiti di ogni scheda", len(d["piano"]) == 2 and set(d["esiti"]) == {"1", "2"} and d["esiti"]["1"]["testo"])
    ok("pannello: il modo si cambia e i valori strani sono rifiutati", c.put("/gestione/locale/cantieri", headers=Hd, json={"modo": "spento"}).status_code == 200 and c.put("/gestione/locale/cantieri", headers=Hd, json={"modo": "boh"}).status_code == 422
       and cantiere.da_usare(ag, COMPITO, "interno", False) is None)
    ok("pannello: solo il titolare", c.get("/gestione/locale/cantieri").status_code in (401, 403))
print("TOTALE %d / %d" % (sum(ris), len(ris)))
