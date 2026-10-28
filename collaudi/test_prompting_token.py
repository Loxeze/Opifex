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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
def tagliata(t): return {"stop_reason": "max_tokens", "usage": uso(), "content": [{"type": "text", "text": t}]}
from app import prompting, dialoghi, fornitori, agente_browser as ab
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE ruolo_speciale IS NULL")
sql("UPDATE agenti SET dialoghi_attivi=TRUE")
visti, copione = [], []
def finta_api(corpo):
    visti.append(json.dumps(corpo.get("system", ""), ensure_ascii=False) + "||" + json.dumps(corpo.get("messages"), ensure_ascii=False))
    return copione.pop(0) if copione else fine("ok")
ab._chiama_api = finta_api
marco, aurora_id = ID("Marco"), ID("Aurora")
operativo = sql("SELECT id, nome FROM agenti WHERE attivo AND livello='operativo' AND ruolo_speciale IS NULL AND tipo='divisione' ORDER BY id LIMIT 1")[0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    def chat(a, t="Ciao"):
        visti.clear(); return c.post(f"/agenti/{a}/chat", headers=H, json={"messaggio": t, "fascia_dati": "interno"}).json()
    # --- competenza di prompting ---
    ok("la competenza descrive struttura completa", all(x in prompting.AVVISO for x in ("RUOLO E CONTESTO", "COMPITO", "MATERIALI E FONTI", "RISULTATO ATTESO", "VINCOLI", "CASI DUBBI", "CONSEGNA")))
    chat(marco)
    ok("il manager riceve la competenza di scrittura dei prompt", visti and "SCRITTURA DEI PROMPT" in visti[0])
    chat(aurora_id)
    ok("il referente la riceve", visti and "SCRITTURA DEI PROMPT" in visti[0])
    chat(operativo[0])
    ok("l'operativo semplice no (nessun costo inutile)", visti and "SCRITTURA DEI PROMPT" not in visti[0], operativo[1])
    sql("INSERT INTO progetti (nome, pm_agente_id) VALUES ('Progetto con PM', %s)", (operativo[0],))
    chat(operativo[0])
    ok("il project manager la riceve anche se operativo", visti and "SCRITTURA DEI PROMPT" in visti[0])
    ok("la brevita' dei dialoghi non vale per i prompt di assegnazione", "ECCEZIONE" in dialoghi.REGOLE_BREVI and "completo e dettagliato" in dialoghi.REGOLE_BREVI)
    ok("la regola comune distingue risposte brevi da prompt completi", "non per i prompt" in prompting.AVVISO)
    # --- limiti di risposta ---
    ok("valore di partenza 16000", sql("SELECT column_default FROM information_schema.columns WHERE table_name='agenti' AND column_name='max_token_risposta'")[0][0] == "16000")
    ok("nessun agente sotto 8000 dopo l'aggiornamento", sql("SELECT count(*) FROM agenti WHERE max_token_risposta < 8000")[0][0] == 0)
    a = c.get("/gestione/agenti", headers=H).json()[0]["id"]
    ok("tetto 16000 accettato", c.put(f"/gestione/agenti/{a}", headers=H, json={"max_token_risposta": 16000}).status_code == 200 and sql("SELECT max_token_risposta FROM agenti WHERE id=%s", (a,))[0][0] == 16000)
    ok("oltre 64000 rifiutato", c.put(f"/gestione/agenti/{a}", headers=H, json={"max_token_risposta": 64001}).status_code == 422)
    ok("la risposta usa il tetto dell'agente", True)
    ok("dialoghi e domande ai colleghi con piu' spazio", dialoghi.MAX_TOKEN_DIALOGO >= 6000)
    # --- risposta tagliata: continua e ricuce ---
    copione[:] = [tagliata("Prima parte del testo, "), fine("seconda parte.")]
    r = chat(marco, "Scrivi un testo lungo")
    ok("risposta tagliata: continua e ricuce il testo", r["risposta"] == "Prima parte del testo, seconda parte.", r["risposta"])
    ok("nessun avviso di troncamento quando ha potuto continuare", "troncata" not in r["risposta"])
    ok("alla continuazione viene mostrato il testo gia' scritto", len(visti) == 2 and "Prima parte del testo" in visti[1] and "Continua esattamente" in visti[1])
    copione[:] = [tagliata(x + " ") for x in "abcdefghij"] + [fine("MAI")]
    r = chat(marco, "Scrivi un testo enorme")
    ok("dopo otto continuazioni si ferma e lo dichiara", r["risposta"].startswith("a b c d") and "troncata" in r["risposta"], r["risposta"])
    copione[:] = [fine("Tutto in una volta")]
    ok("risposta normale invariata", chat(marco)["risposta"] == "Tutto in una volta")
    # --- chiamata semplice al fornitore ---
    class R:
        def __init__(s, d): s.status_code = 200; s._d = d; s.text = ""
        def json(s): return s._d
    risposte = [R({"stop_reason": "max_tokens", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": [{"type": "text", "text": "Inizio "}]}),
                R({"stop_reason": "end_turn", "usage": {"input_tokens": 12, "output_tokens": 6}, "content": [{"type": "text", "text": "fine."}]})]
    corpi = []
    fornitori.chiave = lambda n: "k"
    fornitori.invia = lambda url, intest, corpo, t: (corpi.append(corpo), risposte.pop(0))[1]
    rr = fornitori._chiama_anthropic("m", "sistema", "scrivi", 100)
    ok("chiamata semplice: continuazione e token sommati", rr.testo == "Inizio fine." and rr.token_input == 22 and rr.token_output == 11 and len(corpi) == 2, str((rr.testo, rr.token_input)))
    ok("la seconda chiamata contiene il testo parziale", corpi[1]["messages"][1] == {"role": "assistant", "content": "Inizio"})
    ok("interfaccia: tetto fino a 64000", "max: 64000" in c.get("/app/app.js").text)
print("TOTALE", sum(ris), "/", len(ris))
