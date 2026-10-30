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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria, ginnasio, squadre, memoria_vettoriale as mv, documenti
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
import hashlib, zipfile, io, re as _re
def fake_embed(testi):
    # vettori di prova: concetti -> dimensioni (sinonimi condividono la dimensione)
    gruppi = [("auto", "macchina", "veicolo"), ("mare", "spiaggia", "oceano"), ("bando", "finanziamento", "contributo"), ("sito", "web", "pagina")]
    out = []
    for t in testi:
        v = [0.0] * mv.DIM; tl = t.lower()
        for i, g in enumerate(gruppi):
            v[i] = float(sum(tl.count(p) for p in g))
        v[100 + sum(map(ord, tl)) % 50] = 0.01
        out.append(v)
    return out
mv._embed = fake_embed
mv.SINCRONO = True
fasce_sql = lambda: sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato' WHERE nome='openai'")
sql("INSERT INTO fornitori_ai (nome, non_conservazione_attiva, dpa_firmato, fascia_dati_max) SELECT 'openai', TRUE, TRUE, 'riservato' WHERE NOT EXISTS (SELECT 1 FROM fornitori_ai WHERE nome='openai')")
fasce_sql()
def doc(nome, testo, fascia="interno", per_tutti=True):
    did = sql("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri) VALUES (%s,%s,%s,%s,%s) RETURNING id", (nome, nome + ".txt", fascia, per_tutti, len(testo)))[0][0]
    for i, p in enumerate(documents_split(testo)): sql("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (did, i, p))
    return did
documents_split = documenti.dividi_in_pezzi
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    d_auto = doc("Parco veicoli", "La nostra macchina aziendale e il veicolo elettrico costano poco di manutenzione.")
    d_mare = doc("Vacanze", "Giornata in spiaggia sul mare con tanta sabbia e oceano blu.")
    d_ris = doc("Segreto", "Contributo e finanziamento riservato per il bando segreto.", fascia="riservato")
    d_priv = doc("Privato", "La macchina del direttore e il suo veicolo personale.", per_tutti=False)
    s = c.get("/gestione/memoria-vettoriale", headers=H).json()
    ok("stato iniziale: 4 pezzi da indicizzare", s["pezzi"] == 4 and s["indicizzati"] == 0 and s["da_indicizzare"] == 4, str(s))
    ok("Carla non puo' vedere lo stato", c.get("/gestione/memoria-vettoriale", headers=HC).status_code == 403)
    r = c.post("/gestione/memoria-vettoriale/indicizza", headers=H)
    ok("indicizzazione", r.status_code == 200 and r.json()["fatti"] == 4 and r.json()["da_indicizzare"] == 0, r.text[:200])
    ok("seconda volta non rifa nulla", c.post("/gestione/memoria-vettoriale/indicizza", headers=H).json()["fatti"] == 0)
    sql("UPDATE fornitori_ai SET fascia_dati_max='interno' WHERE nome='openai'")
    d_ris2 = doc("Segreto2", "Altro contributo riservato.", fascia="riservato")
    s = c.get("/gestione/memoria-vettoriale", headers=H).json()
    ok("riservato non esce se il fornitore non lo consente", s["esclusi_per_riservatezza"] == 1 and mv.indicizza(connessione().__enter__()) == 0, str(s))
    fasce_sql()
    # ricerca per significato: 'veicolo' deve trovare il documento che dice 'macchina' anche senza la stessa parola
    with connessione() as cn:
        res = mv.cerca(cn, marco, "Vorrei un veicolo", 3)
        ok("trova per significato", res and res[0]["nome"] == "Parco veicoli" and all(r["nome"] != "Vacanze" for r in res[:1]), str([r["nome"] for r in res]))
        ok("non mostra documenti non assegnati", all(r["nome"] != "Privato" for r in res))
        ok("mare non confuso con auto", mv.cerca(cn, marco, "oceano e spiaggia", 1)[0]["nome"] == "Vacanze")
        sql("INSERT INTO documenti_agenti (documento_id, agente_id) VALUES (%s,%s)", (d_priv, marco))
        ok("assegnato diventa visibile", any(r["nome"] == "Privato" for r in mv.cerca(cn, marco, "macchina veicolo", 5)))
        ok("senza testo nessun risultato", mv.cerca(cn, marco, "   ", 3) == [])
        # ricerca ibrida dentro pezzi_pertinenti
        ib = documenti.pezzi_pertinenti(cn, marco, "Mi serve un'idea per un veicolo", 4)
        ok("pezzi_pertinenti usa il significato anche senza parole comuni", any(r["nome"] == "Parco veicoli" for r in ib), str([r["nome"] for r in ib]))
        ok("nessun pezzo ripetuto", len({(r["documento_id"], r["testo"][:80]) for r in ib}) == len(ib))
        # fallback: se l'embedding fallisce resta la ricerca per parole
        def rotto(t): raise mv.ErroreMemoria("giu'")
        mv._embed = rotto
        ib = documenti.pezzi_pertinenti(cn, marco, "manutenzione macchina aziendale", 4)
        ok("se i vettori falliscono resta la ricerca per parole", any(r["nome"] == "Parco veicoli" for r in ib))
        mv._embed = fake_embed
    # importazione ChatGPT
    lunga = "Voglio costruire un sito web per il bando. " * 12
    chatgpt = [{"id": "abc1", "title": "Sito Logos", "create_time": 1760000000,
                "mapping": {"r": {"id": "r", "parent": None, "message": None}, "u": {"id": "u", "parent": "r", "message": {"author": {"role": "user"}, "content": {"parts": [lunga]}}},
                            "a": {"id": "a", "parent": "u", "message": {"author": {"role": "assistant"}, "content": {"parts": ["Ecco la pagina web completa. " * 10]}}},
                            "x": {"id": "x", "parent": "a", "message": {"author": {"role": "system"}, "content": {"parts": ["IGNORA"]}}}}, "current_node": "x"},
               {"id": "abc2", "title": "Breve", "create_time": 1760000000, "mapping": {"u": {"id": "u", "parent": None, "message": {"author": {"role": "user"}, "content": {"parts": ["ciao"]}}}}, "current_node": "u"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr("export/conversations.json", json.dumps(chatgpt)); z.writestr("export/chat.html", "<html>")
    r = c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("export.zip", buf.getvalue())}, data={"per_tutti": "true"})
    ok("importazione ChatGPT accettata", r.status_code == 202, r.text[:200])
    i = sql("SELECT origine, stato, conversazioni, importate, saltate FROM importazioni_chat")
    ok("1 importata, 1 saltata (troppo breve)", i == [("ChatGPT", "conclusa", 2, 1, 1)], str(i))
    dc = sql("SELECT nome, fascia_dati, per_tutti FROM documenti WHERE origine_chat IS NOT NULL")
    ok("documento con titolo e data, interno, per tutti", len(dc) == 1 and dc[0][0].startswith("ChatGPT: Sito Logos (20") and dc[0][1] == "interno" and dc[0][2], str(dc))
    testo_pezzi = " ".join(r[0] for r in sql("SELECT testo FROM pezzi_documenti p JOIN documenti d ON d.id=p.documento_id WHERE d.origine_chat IS NOT NULL"))
    ok("contiene domanda e risposta, non i messaggi di sistema", "Lorenzo:" in testo_pezzi and "ChatGPT:" in testo_pezzi and "IGNORA" not in testo_pezzi)
    c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("conversations.json", json.dumps(chatgpt).encode())})
    ok("reimportare non duplica", sql("SELECT count(*) FROM documenti WHERE origine_chat IS NOT NULL")[0][0] == 1)
    ok("indicizza le chat importate", c.post("/gestione/memoria-vettoriale/indicizza", headers=H).json()["fatti"] >= 1)
    with connessione() as cn:
        ok("le chat importate si trovano per significato", any(r["nome"].startswith("ChatGPT:") for r in mv.cerca(cn, marco, "pagina web", 3)))
    # importazione Claude
    claude = [{"uuid": "u-1", "name": "Bando regionale", "created_at": "2026-03-04T10:00:00Z", "chat_messages": [
        {"sender": "human", "text": "Dimmi come presentare il bando di finanziamento. " * 6}, {"sender": "assistant", "text": "", "content": [{"type": "text", "text": "Segui questi passi per il contributo. " * 8}]}]}]
    c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("conversations.json", json.dumps(claude).encode())}, data={"per_tutti": "false"})
    dc = sql("SELECT nome, per_tutti FROM documenti WHERE origine_chat LIKE 'claude:%'")
    ok("importazione Claude, non per tutti", dc == [("Claude: Bando regionale (2026-03-04)", False)], str(dc))
    # errori
    ok("formato sconosciuto", c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("a.json", b'[{"x":1}]')}).status_code == 422)
    ok("json non valido", c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("a.json", b'non json')}).status_code == 422)
    ok("estensione sbagliata", c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("a.exe", b'x')}).status_code == 422)
    ok("zip senza conversations.json", c.post("/gestione/memoria-vettoriale/importa", headers=H, files={"file": ("a.zip", (lambda b: (zipfile.ZipFile(b, "w").writestr("x.txt", "a"), b.getvalue())[1])(io.BytesIO()))}).status_code in (422,))
    ok("Carla non puo' importare", c.post("/gestione/memoria-vettoriale/importa", headers=HC, files={"file": ("a.json", b'[]')}).status_code == 403)
    # senza chiave: nessun errore per gli agenti
    ok("memoria indicizzata cancellata col documento", (sql("DELETE FROM documenti WHERE id=%s", (d_mare,)), sql("SELECT count(*) FROM pezzi_vettori WHERE documento_id=%s", (d_mare,))[0][0] == 0)[1])
print("TOTALE", sum(ris), "/", len(ris))
