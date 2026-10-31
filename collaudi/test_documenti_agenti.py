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
from app import strumenti_google as sg, google, allineamento, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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





class Risp:
    def __init__(s, d): s.d = d
    def json(s): return s.d
chiamate = []
def finta_ric(metodo, url, tok, **kw):
    chiamate.append((metodo, url, kw.get("params")))
    fid = url.rsplit("/", 1)[-1]
    if metodo == "GET":
        if fid == "f_perso": raise sg.ErroreGoogle("Google ha risposto 404")
        if fid == "f_cestino": return Risp({"id": fid, "trashed": True, "parents": []})
        if fid == "f_ok": return Risp({"id": fid, "trashed": False, "parents": ["cart-Marco"], "webViewLink": "http://l/ok"})
        return Risp({"id": fid, "trashed": False, "parents": ["radice"], "webViewLink": "http://l/" + fid})
    return Risp({"id": fid})
sg._richiesta = finta_ric
sg._contesto = lambda conn: ("tok", "radice")
sg.collegato = lambda conn: True
google.cartella = lambda tok, nome, gen, esistente=None: esistente or "cart-" + nome
sg._crea_con_contenuto = lambda tok, nome, md, ms, cont, gen: {"id": "f_nuovo", "name": nome, "webViewLink": "http://l/nuovo"}
sql("UPDATE agenti SET drive_attivo=TRUE WHERE id=%s", (marco,))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    with connessione() as cn:
        d = sg._cartella_destinazione(cn, "tok", "radice", None, marco)
    proj = sql("SELECT p.drive_cartella_id FROM progetti p JOIN progetti_agenti x ON x.progetto_id = p.id WHERE x.agente_id=%s AND NOT p.archiviato AND p.eliminato_il IS NULL AND p.drive_cartella_id IS NOT NULL", (marco,))
    atteso = proj[0][0] if len(proj) == 1 else "cart-Marco"   # chi lavora a un solo progetto salva nella cartella del progetto
    ok("destinazione predefinita: cartella del progetto se unico, altrimenti dell'agente", d == atteso, d)
    copione[:] = [chiama("google_crea_documento", {"titolo": "Piano", "testo": "ciao"}), fine("Fatto")]
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "crea il documento Piano su drive", "fascia_dati": "interno"}).json()
    ok("la risposta porta il documento creato con link", r.get("file_creati") and r["file_creati"][0]["link"] == "http://l/nuovo", str(r)[:300])
    ok("il file e' registrato nella cartella di destinazione", sql("SELECT cartella_id, link FROM file_google_agenti WHERE file_id='f_nuovo'") == [(atteso, "http://l/nuovo")])
    ok("l'allegato resta nel messaggio di chat", sql("SELECT allegati->0->>'nome' FROM chat_messaggi WHERE ruolo='agente' ORDER BY id DESC LIMIT 1") == [("Piano",)])
    for fid, ag in (("f_ok", marco), ("f_fuori", marco), ("f_perso", marco), ("f_cestino", marco)):
        sql("INSERT INTO file_google_agenti (file_id, agente_id, nome, tipo) VALUES (%s,%s,%s,'documento')", (fid, ag, fid))
    chiamate.clear()
    e = c.post("/documenti/allineamento", headers=H).json()
    ok("allineamento: esito", (e["spostati"], e["assenti"]) == (2, 2) and e["gia_a_posto"] == 1, str({k: v for k, v in e.items() if k != "file"}))
    ok("allineamento: il file fuori posto viene spostato nella cartella dell'agente", any(m == "PATCH" and p.get("addParents") == "cart-Marco" for m, u, p in chiamate if p))
    ok("allineamento: file perso e cestinato marcati", sql("SELECT file_id FROM file_google_agenti WHERE stato='assente' ORDER BY 1") == [("f_cestino",), ("f_perso",)])
    el = c.get("/documenti/allineamento", headers=H).json()
    ok("elenco documenti", el["collegato"] and len(el["file"]) >= 5)
    ok("senza accesso niente", c.get("/documenti/allineamento").status_code in (401, 403))
    ok("pagina demo servita", "avviaDemo" in c.get("/app/demo.js").text and "demo.js" in c.get("/app/").text)
print("TOTALE", sum(ris), "/", len(ris))
