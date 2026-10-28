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
from app.fornitori import ErroreFornitore
from app import webpush, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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
    ricevuti.append(corpo); return copione.pop(0)
agente_browser._chiama_api = finta_api
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, testo="", i="t"):
    return {"stop_reason": "tool_use", "usage": uso(), "content": ([{"type": "text", "text": testo}] if testo else []) + [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def blocco(t, stop="end_turn"): return {"stop_reason": stop, "usage": uso(), "content": ([{"type": "text", "text": t}] if t else [])}
dialoghi.chiama_modello = lambda *a, **k: __import__("app.fornitori", fromlist=["x"]).Risposta("ok", 1, 1)
ELENA = ID("Elena")
def azioni_vuote(): return sql("SELECT count(*) FROM registro_azioni WHERE azione='risposta_vuota'")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    def chiedi(msg="Come guadagno con video per hotel?"):
        return c.post(f"/agenti/{ELENA}/chat", headers=H, json={"messaggio": msg})
    # 1. ultimo giro vuoto dopo uno strumento: scatta il secondo tentativo e arriva il testo
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Radar", "domanda": "idee hotel?"}, "Chiedo a Radar."), blocco(""), blocco("Tre modi: pacchetti, abbonamento, eventi.")]
    ricevuti.clear(); r = chiedi()
    ok("ultimo giro vuoto: risposta ottenuta col secondo tentativo", r.status_code == 200 and "Tre modi" in r.json()["risposta"], r.text[:200])
    ok("il secondo tentativo non usa strumenti e chiede la risposta scritta", ricevuti[-1].get("tool_choice") == {"type": "none"} and "risposta finale" in json.dumps(ricevuti[-1]["messages"][-1]["content"]))
    ok("alternanza dei ruoli rispettata nel secondo tentativo", all(a["role"] != b["role"] for a, b in zip(ricevuti[-1]["messages"], ricevuti[-1]["messages"][1:])))
    # 2. anche il secondo tentativo e' vuoto: restano i testi dei passaggi precedenti
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Radar", "domanda": "x"}, "Ho chiesto a Radar e aspetto."), blocco(""), blocco("")]
    r = chiedi()
    ok("secondo tentativo vuoto: si conserva il testo dei passaggi precedenti", "aspetto" in r.json()["risposta"] and azioni_vuote() == 0, r.text[:200])
    # 3. tutto vuoto: messaggio con la causa e traccia nel registro
    copione[:] = [blocco(""), blocco("")]
    r = chiedi()
    ok("tutto vuoto: messaggio esplicito, non una risposta vuota", r.status_code == 200 and "non ha scritto nessuna risposta" in r.json()["risposta"] and "Prova agente" in r.json()["risposta"], r.text[:200])
    ok("registrata l'azione 'risposta_vuota' con modello, token e passi", azioni_vuote() == 1 and "passi" in sql("SELECT dettagli::text FROM registro_azioni WHERE azione='risposta_vuota'")[0][0])
    ok("la risposta segnaposto non entra nella memoria della chat", sql("SELECT count(*) FROM memoria_chat WHERE contenuto LIKE '%non ha scritto nessuna%'")[0][0] == 0 if sql("SELECT to_regclass('memoria_chat') IS NOT NULL")[0][0] else True)
    # 4. troncata per lunghezza, con testo parziale: lo si segnala
    copione[:] = [blocco("Prima parte della rispo", "max_tokens")] + [blocco(" e ancora", "max_tokens") for _ in range(8)]  # le continuazioni (max 8) finiscono e resta il testo ricucito
    r = chiedi()
    ok("risposta troncata: testo parziale + avviso", "Prima parte" in r.json()["risposta"] and "troncata" in r.json()["risposta"])
    # 5. troncata senza testo: causa spiegata
    copione[:] = [blocco("", "max_tokens"), blocco("", "max_tokens")]
    r = chiedi()
    ok("vuota per limite di lunghezza: la causa e' detta", "limite di lunghezza" in r.json()["risposta"], r.text[:200])
    # 6. spazio per rispondere
    sql("UPDATE agenti SET max_token_risposta=500 WHERE id=%s", (ELENA,))
    copione[:] = [blocco("ok")]; ricevuti.clear(); chiedi()
    ok("un agente con strumenti ha almeno 2500 token a disposizione anche se ne ha 500 impostati", ricevuti[0]["max_tokens"] >= 2500, str(ricevuti[0]["max_tokens"]))
    ok("limiti dei dialoghi tra agenti piu' larghi", dialoghi.MAX_TOKEN_DIALOGO >= 1500)
    # 7. Prova agente
    copione[:] = [blocco("Sono Elena, coordino Ricerca e Sviluppo.")]
    p = c.post(f"/gestione/agenti/{ELENA}/prova", headers=H).json()
    ok("Prova agente: risposta, tempi e consumi", p["riuscita"] and "Elena" in p["risposta"] and p["token_output"] > 0 and "secondi" in p, str(p))
    copione[:] = [blocco(""), blocco("")]
    p = c.post(f"/gestione/agenti/{ELENA}/prova", headers=H).json()
    ok("Prova agente su agente muto: non riuscita, con i dettagli", not p["riuscita"] and p["dettagli"] and "stop" in p["dettagli"], str(p))
    ok("Prova agente: solo titolare", c.post(f"/gestione/agenti/{ELENA}/prova", headers=HC).status_code == 403 and c.post("/gestione/agenti/99999/prova", headers=H).status_code == 404)
    def finta_errore(corpo): raise ErroreFornitore("Anthropic: 529 sovraccarico")
    agente_browser._chiama_api = finta_errore
    p = c.post(f"/gestione/agenti/{ELENA}/prova", headers=H).json()
    ok("Prova agente: errore del fornitore mostrato, non un 500", p["riuscita"] is False and "529" in p["errore"], str(p))
    agente_browser._chiama_api = finta_api
    # 8. modelli OpenAI/xAI
    risp = []
    def finta_compat(fornitore, corpo):
        risp.append(corpo); return copione_c.pop(0)
    agente_browser._chiama_compat = finta_compat
    u = lambda: {"prompt_tokens": 10, "completion_tokens": 5}
    def msg(t, tool=None):
        m = {"content": t}
        if tool: m["tool_calls"] = [{"id": "1", "function": {"name": "chiedi_a_agente", "arguments": "{}"}}]
        return {"usage": u(), "choices": [{"message": m}]}
    extra = [{"name": "chiedi_a_agente", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    copione_c = [msg("Chiedo.", True), msg(""), msg("Risposta finale scritta.")]
    rr = agente_browser.esegui_con_strumenti_compatibile("openai", "gpt", "sei", "ciao", 500, extra, lambda n, d: "ok")
    ok("OpenAI/xAI: giro finale vuoto -> secondo tentativo", rr.testo == "Risposta finale scritta." and risp[-1].get("tool_choice") == "none")
    copione_c = [msg("Chiedo.", True), msg(""), msg("")]
    rr = agente_browser.esegui_con_strumenti_compatibile("openai", "gpt", "sei", "ciao", 500, extra, lambda n, d: "ok")
    ok("OpenAI/xAI: anche il secondo tentativo vuoto -> resta il testo precedente", rr.testo == "Chiedo.")
    # 9. dialoghi tra agenti (senza strumenti): vuota -> secondo tentativo con piu' spazio
    from app.fornitori import Risposta
    chiamate_d = []
    def d_vuoto_poi_ok(f, m, sis, cont, mt, web=None):
        chiamate_d.append(mt); return Risposta("" if len(chiamate_d) == 1 else "Eccomi.", 5, 5)
    dialoghi.chiama_modello = d_vuoto_poi_ok
    sql("UPDATE agenti SET dialoghi_attivi=FALSE WHERE nome='Marco'")
    rr = c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID("Marco"), "a_agente_id": ID("Scout"), "argomento": "prova", "messaggi": 2})
    ok("dialogo: risposta vuota -> secondo tentativo con il doppio dei token", rr.status_code in (200, 201) and len(chiamate_d) >= 2 and chiamate_d[1] == 2 * chiamate_d[0], f"{rr.status_code} {chiamate_d} {rr.text[:150]}")
    dialoghi.chiama_modello = lambda *a, **k: Risposta("", 1, 1)
    n0 = azioni_vuote()
    c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID("Marco"), "a_agente_id": ID("Scout"), "argomento": "prova2", "messaggi": 2})
    ok("dialogo sempre vuoto: tracciato e messaggio esplicito", azioni_vuote() > n0 and sql("SELECT count(*) FROM messaggi_agenti WHERE testo LIKE '%Nessuna risposta dal modello%'")[0][0] >= 1 if sql("SELECT to_regclass('messaggi_agenti') IS NOT NULL")[0][0] else azioni_vuote() > n0)
    # 10. diario degli scambi con i colleghi (1.23.2)
    sql("UPDATE agenti SET vede_tutto=FALSE WHERE id=%s", (ELENA,))
    conv = sql("INSERT INTO conversazioni (titolo, fascia_dati) VALUES ('t','pubblico') RETURNING id")[0][0]
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'Domanda su bandi borghi: priorita?')", (conv, ID("Scout"), ELENA))
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'Parti da Renovatio.')", (conv, ELENA, ID("Scout")))
    conv2 = sql("INSERT INTO conversazioni (titolo, fascia_dati) VALUES ('r','riservato') RETURNING id")[0][0]
    sql("INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo) VALUES (%s,%s,%s,'SEGRETO riservato')", (conv2, ID("Scout"), ELENA))
    sql("UPDATE fornitori_ai SET fascia_dati_max='interno'"); sql("UPDATE agenti SET fascia_dati_max='interno' WHERE id=%s", (ELENA,))
    copione[:] = [blocco("ok")]; ricevuti.clear(); chiedi("ciao")
    testo_in = json.dumps(ricevuti[0]["messages"], ensure_ascii=False)
    ok("l'agente rivede i suoi scambi recenti con i colleghi", "ULTIMI SCAMBI CON I COLLEGHI" in testo_in and "Parti da Renovatio" in testo_in and "Scout" in testo_in, testo_in[:300])
    ok("gli scambi di fascia non consentita non entrano", "SEGRETO" not in testo_in)
    sql("UPDATE messaggi_agenti SET creato_il = NOW() - INTERVAL '30 days'")
    copione[:] = [blocco("ok")]; ricevuti.clear(); chiedi("ciao")
    ok("gli scambi vecchi (oltre 14 giorni) non entrano", "ULTIMI SCAMBI" not in json.dumps(ricevuti[0]["messages"], ensure_ascii=False))
    # 11. accesso al web: nei dialoghi e nelle istruzioni (1.23.6)
    sql("UPDATE agenti SET accesso_web=TRUE, max_ricerche=4, siti_consentiti='{}' WHERE nome='Scout'")
    sql("UPDATE agenti SET dialoghi_attivi=FALSE WHERE nome='Scout'")
    visti = []
    def dialogo_spia(f, m, sis, cont, mt, web=None):
        visti.append((sis, web)); return Risposta("Cerco.", 5, 5)
    dialoghi.chiama_modello = dialogo_spia
    sql("UPDATE agenti SET modello_dialogo='claude-haiku-5-5' WHERE nome='Scout'")
    c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": ID("Marco"), "a_agente_id": ID("Scout"), "argomento": "cerca bandi", "messaggi": 2})
    scout_web = [v for v in visti if v[1] and 'Sei Scout' in v[0]]
    ok("nei dialoghi chi ha il web lo usa: strumento passato e istruzione esplicita", scout_web and scout_web[0][1]["max_ricerche"] == 4 and "HAI LA RICERCA WEB" in scout_web[0][0], str(visti)[:200])
    ok("chi non ha il web non riceve la dicitura", all("HAI LA RICERCA WEB" not in v[0] for v in visti if not v[1]))
    sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE nome='Scout'")
    copione[:] = [blocco("ok")]; ricevuti.clear()
    c.post(f"/agenti/{ID('Scout')}/chat", headers=H, json={"messaggio": "cerca", "fascia_dati": "pubblico"})
    ok("nel lavoro ordinario l'agente sa di avere la ricerca web e che deve usarla", ricevuti and "HAI LA RICERCA WEB" in ricevuti[0]["system"] and any(t.get("name") == "web_search" for t in ricevuti[0]["tools"]), str(ricevuti[:1])[:200])
    # 12. web per tutti, bloccabile (1.23.7)
    ok("tutti gli agenti hanno il web e il valore predefinito e' acceso", sql("SELECT count(*) FROM agenti WHERE NOT accesso_web AND (ruolo_speciale IS NULL OR ruolo_speciale NOT IN ('cerimoniere', 'custode')) AND nome <> 'Osservatore dell''uso'")[0][0] == 0 and sql("SELECT column_default FROM information_schema.columns WHERE table_name='agenti' AND column_name='accesso_web'")[0][0] == "true")
    sql("UPDATE agenti SET accesso_web=FALSE WHERE nome='Leo'")
    sql(open("sql/50_web_per_tutti.sql").read())
    ok("la migrazione non riaccende i blocchi decisi dopo", sql("SELECT accesso_web FROM agenti WHERE nome='Leo'")[0][0] is False)
    copione[:] = [blocco("ok")]; ricevuti.clear(); c.post(f"/agenti/{ID('Leo')}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"})
    ok("agente bloccato: nessuno strumento web e istruzione chiara", ricevuti and "NON HAI LA RICERCA WEB" in ricevuti[0]["system"] and not any(t.get("name") == "web_search" for t in ricevuti[0].get("tools", [])), str(ricevuti[:1])[:150])
    n = c.post("/gestione/agenti", headers=H, json={"nome": "Nuovo", "ruolo": "prova", "modello": sql("SELECT nome FROM modelli_ai LIMIT 1")[0][0], "istruzioni": "Sei Nuovo, un agente di prova per verificare i predefiniti.", "divisione_id": sql("SELECT id FROM divisioni LIMIT 1")[0][0], "livello": "operativo"})
    ok("un nuovo agente nasce con il web acceso", n.status_code == 201 and sql("SELECT accesso_web FROM agenti WHERE nome='Nuovo'")[0][0] is True, n.text[:150])
print("TOTALE", sum(ris), "/", len(ris))
