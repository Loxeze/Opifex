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
from app import esecuzione, fornitori
from app.fornitori import Risposta, ErroreFornitore, ErroreLocale
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
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato'")

# finto Ollama sul portatile
STATO = {"su": True, "tags": ["qwen3:8b", "nemotron-3-nano", "nomic-embed-text"], "chiamate": 0, "idle": None, "modello_assente": False}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/tags": self._j(200, {"models": [{"name": n} for n in STATO["tags"]]})
        else: self._j(404, {})
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); corpo = json.loads(self.rfile.read(n) or b"{}")
        STATO["chiamate"] += 1
        with psycopg.connect(DSN, autocommit=True) as c:
            STATO["idle"] = c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='agenti_test' AND state='idle in transaction'").fetchone()[0]
        if STATO["modello_assente"]: return self._j(404, {"error": "model not found"})
        self._j(200, {"choices": [{"message": {"content": "Risposta dal portatile (" + corpo["model"] + ")"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 7}})
srv = HTTPServer(("127.0.0.1", 11555), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:11555"

with TestClient(app) as c:
    Hd = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ok("il fornitore 'locale' esiste, riservato, senza conservazione", sql("SELECT fascia_dati_max, non_conservazione_attiva, dpa_firmato FROM fornitori_ai WHERE nome='locale'")[0] == ("riservato", True, True))
    r = c.put("/gestione/locale", headers=Hd, json={"url": "ftp://x", "ripiego": ""}); ok("indirizzo non http rifiutato", r.status_code == 422)
    r = c.put("/gestione/locale", headers=Hd, json={"url": URL, "ripiego": "inesistente"}); ok("ripiego inesistente rifiutato", r.status_code == 422)
    r = c.put("/gestione/locale", headers=Hd, json={"url": URL + "/", "ripiego": ""}); ok("salvataggio indirizzo", r.status_code == 200 and fornitori.url_locale() == URL)
    p = c.post("/gestione/locale/prova", headers=Hd).json(); ok("prova: raggiungibile, elenca i modelli", p["raggiungibile"] and "qwen3:8b" in p["modelli"], str(p))
    r = c.post("/gestione/locale/modelli/importa", headers=Hd).json()
    ok("importa i modelli (non gli embedding), a costo zero", r["nuovi"] == 2 and sql("SELECT count(*) FROM modelli_ai m JOIN fornitori_ai f ON f.id=m.fornitore_id WHERE f.nome='locale' AND m.costo_input_per_milione=0")[0][0] == 2, str(r))
    ok("importazione ripetuta: nessun doppione", c.post("/gestione/locale/modelli/importa", headers=Hd).json()["nuovi"] == 0)
    ok("solo il titolare", c.get("/gestione/locale").status_code in (401, 403))
    s = c.get("/gestione/locale", headers=Hd).json(); ok("stato: modelli registrati e candidati al ripiego", len(s["registrati"]) == 2 and "claude-sonnet-5-5" in s["candidati_ripiego"] and not any(x in s["candidati_ripiego"] for x in s["registrati"]))

    # chiamata diretta
    q = fornitori.chiama_modello("locale", "qwen3:8b", "sei un assistente", "ciao", 100)
    ok("chiamata al modello locale", q.testo == "Risposta dal portatile (qwen3:8b)" and q.token_input == 12 and q.token_output == 7)
    STATO["modello_assente"] = True
    try: fornitori.chiama_modello("locale", "xx", "s", "m", 10); e = None
    except ErroreFornitore as ex: e = ex
    ok("modello non scaricato: messaggio chiaro, non e' un ripiego", e is not None and not isinstance(e, ErroreLocale) and "ollama pull" in str(e))
    STATO["modello_assente"] = False
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('locale_url','http://127.0.0.1:1') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
    t0 = time.time()
    try: fornitori.chiama_modello("locale", "qwen3:8b", "s", "m", 10); e = None
    except ErroreLocale as ex: e = ex
    ok("portatile spento: errore subito (senza nuovi tentativi lunghi)", e is not None and time.time() - t0 < 8, str(time.time() - t0))
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='locale_url'", (URL,))

    # un agente sul modello locale
    ag = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    sql("UPDATE agenti SET livello='operativo' WHERE id=%s", (ag,)); sql("UPDATE progetti SET pm_agente_id=NULL WHERE pm_agente_id=%s", (ag,))
    sql("UPDATE agenti SET modello='qwen3:8b' WHERE id=%s", (ag,))
    nube = {"n": 0}
    TUTTI = esecuzione.STRUMENTI_FORNITORI; esecuzione.STRUMENTI_FORNITORI = ("anthropic",)   # agente senza strumenti: percorso semplice
    reale = esecuzione.chiama_modello
    def finta(fornitore, modello, istr, msg, mt, web=None):
        if fornitore == "locale": return reale(fornitore, modello, istr, msg, mt, web)
        nube["n"] += 1; return Risposta("Risposta dal cloud di ripiego", 30, 9, {})
    esecuzione.chiama_modello = finta
    STATO["chiamate"] = 0
    o = esecuzione.esegui_agente(ag, "ciao", "interno", None)
    ok("l'agente risponde dal modello locale", o["risposta"] == "Risposta dal portatile (qwen3:8b)" and nube["n"] == 0, o["risposta"][:80])
    ok("durante la risposta nessuna connessione resta aperta a meta' lavoro", STATO["idle"] == 0, str(STATO["idle"]))
    ok("registrato come uscita verso il fornitore locale, a costo zero", sql("SELECT f.nome FROM registro_uscite u JOIN fornitori_ai f ON f.id=u.fornitore_id WHERE u.agente_id=%s ORDER BY u.id DESC LIMIT 1", (ag,))[0][0] == "locale"
       and float(sql("SELECT costo_stimato FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (ag,))[0][0]) == 0)

    # portatile spento
    sql("UPDATE impostazioni_sistema SET valore='http://127.0.0.1:1' WHERE chiave='locale_url'")
    try: esecuzione.esegui_agente(ag, "ciao", "interno", None); e = None
    except Exception as ex: e = ex
    ok("senza ripiego: l'agente non risponde e l'errore dice perche'", e is not None and "portatile" in str(e) and nube["n"] == 0, str(e)[:100])
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('locale_ripiego','claude-sonnet-5-5') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
    sql("UPDATE agenti SET modello='qwen3:8b' WHERE id=%s", (ag,))
    o = esecuzione.esegui_agente(ag, "ciao", "interno", None)
    ok("dato interno con ripiego consentito: risponde il cloud", o["risposta"] == "Risposta dal cloud di ripiego" and nube["n"] == 1, o["risposta"][:80])
    ok("il ripiego e' registrato nel registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE agente_id=%s AND azione='ripiego_modello_locale'", (ag,))[0][0] == 1)
    ok("costi e uscite attribuiti al modello di ripiego", sql("SELECT modello FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (ag,))[0][0] == "claude-sonnet-5-5"
       and sql("SELECT f.nome FROM registro_uscite u JOIN fornitori_ai f ON f.id=u.fornitore_id WHERE u.agente_id=%s AND NOT u.bloccato ORDER BY u.id DESC LIMIT 1", (ag,))[0][0] == "anthropic")
    # dato riservato: niente cloud
    sql("UPDATE fornitori_ai SET fascia_dati_max='interno' WHERE nome='anthropic'")
    try: esecuzione.esegui_agente(ag, "dati riservati", "riservato", None); e = None
    except Exception as ex: e = ex
    ok("dato riservato: nessun ripiego sul cloud, resta in attesa", e is not None and nube["n"] == 1 and "resta in attesa" in str(e), str(e)[:140])
    ok("il tentativo bloccato e' tracciato", sql("SELECT count(*) FROM registro_uscite WHERE agente_id=%s AND bloccato AND motivo_blocco LIKE 'Ripiego dal modello locale%%'", (ag,))[0][0] == 1)
    # portatile di nuovo acceso
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='locale_url'", (URL,))
    o = esecuzione.esegui_agente(ag, "dati riservati", "riservato", None)
    ok("portatile riacceso: il dato riservato viene elaborato in locale", o["risposta"].startswith("Risposta dal portatile") and nube["n"] == 1)
    ok("il modello locale non viene scelto da solo per i dialoghi automatici", "locale" not in [r[0] for r in sql("SELECT f.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id=m.fornitore_id WHERE m.usa_per_dialoghi")])
    # con gli strumenti: il modello locale li usa e, se il portatile e' spento, NON c'e' ripiego sul cloud
    esecuzione.STRUMENTI_FORNITORI = TUTTI
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='locale_url'", (URL,)); sql("UPDATE fornitori_ai SET fascia_dati_max='riservato' WHERE nome='anthropic'")
    n0 = nube["n"]
    o = esecuzione.esegui_agente(ag, "ciao", "interno", None)
    ok("con gli strumenti il modello locale risponde (percorso a funzioni)", o["risposta"].startswith("Risposta dal portatile"), o["risposta"][:80])
    sql("UPDATE impostazioni_sistema SET valore='http://127.0.0.1:1' WHERE chiave='locale_url'")
    try: esecuzione.esegui_agente(ag, "ciao", "interno", None); e = None
    except Exception as ex: e = ex
    ok("con gli strumenti e portatile spento: errore, nessun ripiego sul cloud", e is not None and nube["n"] == n0, str(e)[:100])
    # ricerca online delegata
    from app import delega_online
    sql("UPDATE agenti SET accesso_web=TRUE, siti_consentiti='{}', max_ricerche=3 WHERE id=%s", (ag,))
    sql("UPDATE fornitori_ai SET fascia_dati_max='riservato', non_conservazione_attiva=TRUE, dpa_firmato=TRUE WHERE nome='anthropic'")
    viste = []
    reale_cm = delega_online.chiama_modello
    delega_online.chiama_modello = lambda f, m, i, t, mt, web=None: (viste.append((f, m, t, web)) or Risposta("Esito della ricerca con fonti", 40, 15, {}))
    fornitori_chiave = delega_online.fornitori.chiave; delega_online.fornitori.chiave = lambda n: "k"
    a_ = {"fascia_dati_max": "riservato", "siti_consentiti": [], "max_ricerche": 3}
    g = delega_online.strumento(ag, a_, "interno")
    out = g("cerca_online", {"domanda": "bandi europei cultura 2027"})
    ok("cerca_online: la domanda passa a Claude con la ricerca web e torna il risultato", out == "Esito della ricerca con fonti" and viste[0][0] == "anthropic" and viste[0][3] == {"siti": [], "max_ricerche": 3}, str(viste))
    ok("cerca_online: costi, uscita e azione registrati", sql("SELECT count(*) FROM costi_api WHERE agente_id=%s AND modello='claude-sonnet-5-5'", (ag,))[0][0] >= 1
       and sql("SELECT count(*) FROM registro_azioni WHERE agente_id=%s AND azione='ricerca_online_delegata'", (ag,))[0][0] == 1)
    sql("UPDATE fornitori_ai SET fascia_dati_max='pubblico' WHERE nome='anthropic'")
    g2 = delega_online.strumento(ag, a_, "riservato"); n_ = len(viste)
    out = g2("cerca_online", {"domanda": "x"})
    ok("cerca_online: dato riservato non esce verso Claude, tentativo tracciato", out.startswith("ERRORE") and len(viste) == n_ and sql("SELECT count(*) FROM registro_uscite WHERE agente_id=%s AND bloccato AND motivo_blocco LIKE 'Ricerca online%%'", (ag,))[0][0] == 1)
    sql("UPDATE fornitori_ai SET fascia_dati_max='riservato' WHERE nome='anthropic'")
    g3 = delega_online.strumento(ag, a_, "interno")
    for _ in range(4): g3("cerca_online", {"domanda": "y"})
    ok("cerca_online: al massimo 4 ricerche per compito", g3("cerca_online", {"domanda": "z"}).startswith("ERRORE: troppe"))
    # comunicazione esterna delegata: l'invio lo esegue Claude con i soli strumenti di uscita
    from app import agente_browser
    chiamate = []
    reale_es = agente_browser.esegui_con_strumenti
    def finto_es(modello, istr, msg, mt, nav, extra=None, gest=None, avv="", web=None):
        chiamate.append((modello, [e["name"] for e in extra], msg)); out = gest("posta_invia", {"a": "x@y.it"})
        return Risposta("Email inviata a x@y.it", 30, 10, {})
    agente_browser.esegui_con_strumenti = finto_es
    invii = []
    gu = delega_online.strumento_uscita(ag, a_, "interno", [{"name": "posta_invia"}], {"posta_invia": lambda n, d: invii.append(d) or "ok"}, "")
    out = gu("comunica_esterno", {"richiesta": "Manda a x@y.it: Gentile..."})
    ok("comunica_esterno: Claude esegue l'invio con i soli strumenti di uscita", out == "Email inviata a x@y.it" and chiamate[0][0] == "claude-sonnet-5-5" and chiamate[0][1] == ["posta_invia"] and len(invii) == 1, str(chiamate))
    ok("comunica_esterno: costi e azione registrati", sql("SELECT count(*) FROM registro_azioni WHERE agente_id=%s AND azione='comunicazione_esterna_delegata'", (ag,))[0][0] == 1)
    sql("UPDATE fornitori_ai SET fascia_dati_max='pubblico' WHERE nome='anthropic'")
    gu2 = delega_online.strumento_uscita(ag, a_, "riservato", [{"name": "posta_invia"}], {}, ""); n_ = len(chiamate)
    ok("comunica_esterno: dato riservato non esce, tentativo tracciato", gu2("comunica_esterno", {"richiesta": "x"}).startswith("ERRORE") and len(chiamate) == n_
       and sql("SELECT count(*) FROM registro_uscite WHERE agente_id=%s AND bloccato AND motivo_blocco LIKE 'Comunicazione esterna%%'", (ag,))[0][0] == 1)
    agente_browser.esegui_con_strumenti = reale_es
    delega_online.chiama_modello = reale_cm; delega_online.fornitori.chiave = fornitori_chiave
print("TOTALE %d / %d" % (sum(ris), len(ris)))
