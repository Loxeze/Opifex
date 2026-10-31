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
from app import costi, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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




aur = ID("Aurora")
sent = sql("SELECT id FROM agenti WHERE sentinella ORDER BY id LIMIT 1")
sent = sent[0][0] if sent else None
ok("esiste almeno una sentinella", sent is not None)
for g, tipo, tin, tout, cst, ag in ((0, "lavoro", 1000, 500, 1.50, marco), (0, "dialogo", 400000, 100000, 0.50, marco), (1, "dialogo", 800000, 200000, 1.00, marco), (2, "lavoro", 2000, 1000, 3.00, scout)):
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo, creato_il) VALUES (%s,'claude-sonnet-5-5',%s,%s,%s,%s, NOW() - make_interval(days => %s))", (ag, tin, tout, cst, tipo, g))
ok("migrazione: dialoghi a 30 milioni", int(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='dialoghi_budget_token_giornaliero'")[0][0]) >= 30000000)
chiamate = []
def finto_get(url, **kw):
    chiamate.append((url, kw))
    class R:
        status_code = 200; text = ""
        def json(self):
            if "anthropic" in url:
                return {"data": [{"starting_at": "2026-10-25T00:00:00Z", "results": [{"amount": "250.0"}, {"amount": "50.0"}]}], "has_more": False}
            return {"data": [{"start_time": 1792800000, "results": [{"amount": {"value": 1.25, "currency": "usd"}}]}]}
    return R()
costi.httpx.get = finto_get
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("solo titolare", c.get("/gestione/costi", headers=HC).status_code == 403)
    q = c.get("/gestione/costi", headers=H).json()
    ok("senza chiavi: stima, nessun dato reale", q["fornitori"] == {} and not any(q["chiavi"].values()) and "non disponibile" in q["testo"])
    ok("stima per giorno e per agente", len(q["stima"]["per_giorno"]) == 3 and abs(sum(d["costo"] for d in q["stima"]["per_giorno"].values()) - 6.0) < 0.01
       and {x["nome"] for x in q["stima"]["per_agente"]} == {"Marco", "Scout"}, str(q["stima"]["per_agente"]))
    pr = q["pieno_regime"]
    ok("pieno regime: dialoghi al budget + lavoro dei giorni piu' intensi", pr["dialoghi"] > 0 and pr["lavoro"] > 0 and abs(pr["totale"] - (pr["dialoghi"] + pr["lavoro"])) < 0.02 and pr["mensile"] > pr["totale"], str(pr))
    ok("limiti: dialoghi non esauriti", q["limiti"]["dialoghi_esauriti"] is False and q["limiti"]["dialoghi_budget_giorno"] >= 30000000)
    ok("salva chiavi (cifrate, mai restituite)", c.put("/gestione/costi/chiavi", headers=H, json={"fornitore": "anthropic", "chiave": "sk-ant-admin-segretissima"}).json()["anthropic"] is True
       and c.put("/gestione/costi/chiavi", headers=H, json={"fornitore": "openai", "chiave": "sk-admin-openai-seg"}).status_code == 200
       and "segretissima" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='anthropic_admin_chiave_cifrata'")[0][0]
       and c.put("/gestione/costi/chiavi", headers=H, json={"fornitore": "x", "chiave": "k"}).status_code == 422)
    q = c.get("/gestione/costi", headers=H).json()
    ok("dato reale Anthropic in dollari (centesimi/100) e OpenAI", abs(q["fornitori"]["anthropic"]["usd_per_giorno"]["2026-10-25"] - 3.0) < 0.001 and abs(list(q["fornitori"]["openai"]["usd_per_giorno"].values())[0] - 1.25) < 0.001, str(q["fornitori"]))
    a = [x for x in chiamate if "anthropic" in x[0]][0][1]
    ok("chiamata Anthropic con chiave admin in x-api-key", a["headers"]["x-api-key"] == "sk-ant-admin-segretissima" and a["params"]["bucket_width"] == "1d")
    # strumento per agente
    sql("UPDATE impostazioni_sistema SET valore='1000' WHERE chiave='dialoghi_budget_token_giornaliero'")
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) VALUES (%s,'claude-sonnet-5-5',900000,200000,1,'dialogo')", (marco,))
    copione[:] = [chiama("costi_consulta", {"giorni": 7}, "a"), fine("Fatto")]; strumenti_visti.clear(); ultimi_msg.clear()
    r = c.post(f"/agenti/{aur}/chat", headers=H, json={"messaggio": "quanto spendiamo?", "fascia_dati": "interno"})
    ok("Aurora vede lo strumento e riceve i numeri", r.status_code == 200 and "costi_consulta" in strumenti_visti[0] and "PIENO REGIME" in ultimi_msg[-1] and "ESAURITO" in ultimi_msg[-1] and "Dato reale anthropic" in ultimi_msg[-1], r.text[:200])
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{sent}/chat", headers=H, json={"messaggio": "controlla i costi di oggi", "fascia_dati": "interno"})
    ok("una sentinella vede lo strumento", strumenti_visti and "costi_consulta" in strumenti_visti[0])
    sql("DELETE FROM chat_messaggi")
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{aur}/chat", headers=H, json={"messaggio": "Ciao Aurora, come va?", "fascia_dati": "interno"})
    ok("senza parlare di costi lo strumento non c'e' (richieste normali leggere)", not any("costi_consulta" in x for x in strumenti_visti))
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{ID('Giulia')}/chat", headers=H, json={"messaggio": "quanto costiamo?", "fascia_dati": "interno"})
    ok("un agente comune no", not any("costi_consulta" in x for x in strumenti_visti))
    costi.httpx.get = lambda url, **kw: type("R", (), {"status_code": 401, "text": "non autorizzato", "json": lambda s: {}})()
    ok("errore del fornitore riportato, senza crash", "ERRORE" in costi.testo(costi.quadro(__import__("app.db", fromlist=["x"]).connessione().__enter__(), 7)))
print("TOTALE", sum(ris), "/", len(ris))
