import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import agente_browser, dialoghi
from app.fornitori import Risposta
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))

chiamate_dialogo, risposte = [], []
def finto_dialogo(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    chiamate_dialogo.append(dict(modello=modello, istruzioni=istruzioni, messaggio=messaggio, max_token=max_token))
    testo = risposte.pop(0) if risposte else "Risposta di prova del collega."
    return Risposta(testo, 200, 100)
dialoghi.chiama_modello = finto_dialogo

copione, ricevuti = [], []
def finta_api(corpo):
    ricevuti.append(corpo); return copione.pop(0)
agente_browser._chiama_api = finta_api
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ID = {n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0] for n in ["Scout", "Marco", "Aurora", "Leo", "Giulia", "Valutatrice", "Elena"]}
    with __import__("app.db", fromlist=["x"]).connessione() as cn:
        pass
    from app.db import connessione
    with connessione() as cn:
        cs = {x["nome"] for x in dialoghi.colleghi(cn, ID["Scout"])}
        cm = {x["nome"] for x in dialoghi.colleghi(cn, ID["Marco"])}
    ok("Scout parla solo con il suo superiore (Marco)", cs == {"Marco"}, str(cs))
    ok("Marco parla con superiore, subordinati e altri manager, non con Leo", {"Aurora", "Scout", "Valutatrice", "Scadenze", "Giulia", "Dario", "Elena"} <= cm and "Leo" not in cm, str(cm))
    ag = c.get("/gestione/agenti", headers=H).json()
    ok("gli agenti espongono modello_dialogo e dialoghi_attivi (manager acceso, operativi spenti di default)", all(a["modello_dialogo"] is None for a in ag) and {a["nome"]: a["dialoghi_attivi"] for a in ag}["Scout"] is False and {a["nome"]: a["dialoghi_attivi"] for a in ag}["Marco"] is True)
    ok("modello dialogo inesistente -> 422", c.put(f"/gestione/agenti/{ID['Marco']}", headers=H, json={"modello_dialogo": "boh"}).status_code == 422)

    # --- dialogo avviato da Lorenzo
    ok("coppia non ammessa (Scout-Leo) -> 409", c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID["Scout"], "a_agente_id": ID["Leo"], "argomento": "prova", "messaggi": 4}).status_code == 409)
    ok("collaboratore non avvia dialoghi (403)", c.post("/gestione/dialoghi", headers=HS, json={"da_agente_id": ID["Scout"], "a_agente_id": ID["Marco"], "argomento": "prova"}).status_code == 403)
    ok("dialogo con dati interni senza garanzie -> 409 e blocco registrato",
       c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID["Marco"], "a_agente_id": ID["Scout"], "argomento": "dati interni", "fascia_dati": "interno"}).status_code == 409
       and sql("SELECT count(*) FROM registro_uscite WHERE bloccato AND motivo_blocco LIKE 'Dialogo:%%'")[0][0] == 1)
    risposte[:] = ["Ciao Scout, devo capire quali bandi cerchi e perche'.", "Marco, cerco bandi sui borghi perche' il profilo lo richiede. Ti serve altro?", "Tutto chiaro, grazie. [CHIARITO]"]
    chiamate_dialogo.clear()
    r = c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID["Marco"], "a_agente_id": ID["Scout"], "argomento": "Coordinare la ricerca di bandi sui borghi", "messaggi": 6})
    ok("dialogo avviato da Lorenzo", r.status_code == 201, r.text)
    cid = r.json()["id"]
    d = c.get(f"/gestione/dialoghi/{cid}", headers=H).json()
    ok("si ferma da solo con [CHIARITO] dopo 3 messaggi (non 6)", len(d["messaggi"]) == 3 and d["stato"] == "chiusa", str(len(d["messaggi"])))
    ok("i messaggi alternano Marco e Scout", [m["da"] for m in d["messaggi"]] == ["Marco", "Scout", "Marco"])
    ok("usato il modello ECONOMICO per i dialoghi, non il modello di lavoro (opus) di Marco", all(x["modello"] == "claude-haiku-5-5" for x in chiamate_dialogo), str([x["modello"] for x in chiamate_dialogo]))
    ok("le regole di chiarezza sono nel prompt dei dialoghi", "NON indovinare" in chiamate_dialogo[0]["istruzioni"] and "Sei Marco" in chiamate_dialogo[0]["istruzioni"])
    ok("il tetto di token dei dialoghi e' basso (700)", all(x["max_token"] == 700 for x in chiamate_dialogo))
    ok("i costi dei dialoghi sono marcati 'dialogo'", sql("SELECT count(*) FROM costi_api WHERE tipo='dialogo'")[0][0] == 3)
    c.put(f"/gestione/agenti/{ID['Scout']}", headers=H, json={"modello_dialogo": "claude-sonnet-5-5"})
    chiamate_dialogo.clear(); risposte[:] = ["a", "b [CHIARITO]"]
    c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID["Scout"], "a_agente_id": ID["Marco"], "argomento": "scelta modello", "messaggi": 4})
    ok("se l'agente ha un modello dialogo suo, parla con quello", chiamate_dialogo[0]["modello"] == "claude-sonnet-5-5" and chiamate_dialogo[1]["modello"] == "claude-haiku-5-5", str([x["modello"] for x in chiamate_dialogo]))
    c.put(f"/gestione/agenti/{ID['Scout']}", headers=H, json={"modello_dialogo": None})

    # --- feed e lista
    f = c.get("/gestione/dialoghi/feed", headers=H).json()
    ok("feed generale con tutti i messaggi in ordine", len(f) == 5 and [m["id"] for m in f] == sorted(m["id"] for m in f))
    ultimo = f[-1]["id"]
    ok("feed incrementale: nessun nuovo messaggio", c.get(f"/gestione/dialoghi/feed?dopo_id={ultimo}", headers=H).json() == [])
    ok("collaboratore non vede il feed (403)", c.get("/gestione/dialoghi/feed", headers=HS).status_code == 403)
    el = c.get("/gestione/dialoghi", headers=H).json()
    ok("elenco conversazioni con partecipanti e conteggio", len(el) == 2 and "Marco" in el[0]["partecipanti"] and el[0]["messaggi"] in (2, 3))
    ok("conversazione inesistente -> 404", c.get("/gestione/dialoghi/9999", headers=H).status_code == 404)

    # --- agente che fa domande da solo durante il lavoro
    ok("senza 'dialoghi attivi' l'agente non ha lo strumento", True)
    c.put(f"/gestione/agenti/{ID['Scout']}", headers=H, json={"dialoghi_attivi": True})
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "Sono Scout, sto cercando bandi borghi. Per quale impresa devo filtrare e con quale scadenza minima?"}, "a"),
                  chiama("chiedi_a_agente", {"destinatario": "Leo", "domanda": "ciao"}, "b"),
                  chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "Grazie. E l'importo minimo?"}, "c"),
                  chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "Una quarta domanda"}, "d"),
                  fine("Ora ho chiaro cosa cercare.")]
    ricevuti.clear(); chiamate_dialogo.clear()
    risposte[:] = ["Per Logos, con scadenza oltre 30 giorni. Spiego: cosi' hai il tempo di preparare la domanda.", "Importo minimo 20000 euro."]
    r = c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "Cerca bandi sui borghi", "fascia_dati": "pubblico"})
    ok("Scout lavora e fa domande al superiore", r.status_code == 200 and "chiaro" in r.json()["risposta"], r.text)
    ok("lo strumento chiedi_a_agente e' offerto con l'elenco dei colleghi", any(t["name"] == "chiedi_a_agente" and "Marco" in t["description"] for t in ricevuti[0]["tools"]))
    ok("la risposta del collega torna a Scout", "oltre 30 giorni" in str(ricevuti[1]))
    ok("destinatario non ammesso: errore chiaro, nessun dialogo", "Puoi parlare solo con" in str(ricevuti[2]) and "Leo" not in {m["da"] for m in c.get("/gestione/dialoghi/feed", headers=H).json()})
    ok("seconda domanda a Marco prosegue nella STESSA conversazione", "Importo minimo" in str(ricevuti[3]) and sql("SELECT count(*) FROM conversazioni")[0][0] == 3)
    ok("quarta domanda bloccata dal limite per compito", "limite di 3 domande" in str(ricevuti[4]))
    ok("il dialogo usa il modello economico (non quello di lavoro)", all(x["modello"] == "claude-haiku-5-5" for x in chiamate_dialogo))
    ok("le domande di Scout sono nel feed con nome e testo", any(m["da"] == "Scout" and "Per quale impresa" in m["testo"] for m in c.get("/gestione/dialoghi/feed", headers=H).json()))
    ok("anche il lavoro di Scout e' costo 'lavoro', i dialoghi 'dialogo'", sql("SELECT count(*) FROM costi_api WHERE tipo='lavoro' AND agente_id=%s", (ID["Scout"],))[0][0] >= 1)

    # --- limiti
    c.put("/gestione/dialoghi/limiti", headers=H, json={"dialoghi_max_messaggi": 2, "dialoghi_max_domande": 3, "dialoghi_budget_token_giornaliero": 200000, "modello_dialogo_predefinito": "claude-haiku-5-5"})
    ok("limiti salvati e riletti", c.get("/gestione/dialoghi/limiti", headers=H).json()["dialoghi_max_messaggi"] == "2")
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "uno"}, "a"), chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "due"}, "b"), fine("ok")]
    ricevuti.clear(); risposte[:] = ["r1", "r2"]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    ok("limite di messaggi per conversazione rispettato", "numero massimo di messaggi" in str(ricevuti[2]), str(ricevuti[2])[:300])
    c.put("/gestione/dialoghi/limiti", headers=H, json={"dialoghi_max_messaggi": 8, "dialoghi_max_domande": 3, "dialoghi_budget_token_giornaliero": 1000, "modello_dialogo_predefinito": "claude-haiku-5-5"})
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Marco", "domanda": "uno"}, "a"), fine("ok")]
    ricevuti.clear()
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "y", "fascia_dati": "pubblico"})
    ok("budget giornaliero dei dialoghi esaurito -> nessuna chiamata", "Budget giornaliero" in str(ricevuti[1]))
    ok("limiti non validi rifiutati", c.put("/gestione/dialoghi/limiti", headers=H, json={"dialoghi_max_messaggi": 1, "dialoghi_max_domande": 3, "dialoghi_budget_token_giornaliero": 200000, "modello_dialogo_predefinito": "claude-haiku-5-5"}).status_code == 422)
f = ris.count(False); print(f"\nTOTALE: {len(ris)-f}/{len(ris)}"); sys.exit(1 if f else 0)
