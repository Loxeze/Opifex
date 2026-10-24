import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import ripresa
from app.main import app
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('=Cmd','c@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
ripresa.riprendi = lambda *a, **k: None
scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
with TestClient(app) as c:
    tok = lambda e: {"Authorization": "Bearer " + c.post("/login", json={"email": e, "password": "PasswordLunga!2026"}).json()["token"]}
    H, H2 = tok("l@p.it"), tok("c@p.it")
    n0 = sql("SELECT count(*) FROM registro_decisioni")[0][0]
    # richiesta
    r1 = sql("INSERT INTO richieste_informazioni (agente_id, domanda) VALUES (%s,'Quale CUP?') RETURNING id", (scout,))[0][0]
    r2 = sql("INSERT INTO richieste_informazioni (agente_id, domanda) VALUES (%s,'Altra domanda?') RETURNING id", (scout,))[0][0]
    c.post(f"/gestione/richieste/{r1}/risposta", headers=H, json={"risposta": "CUP B53C22003780006"})
    c.post(f"/gestione/richieste/{r2}/annulla", headers=H2)
    rg = sql("SELECT utente_nome, esito, oggetto, nota FROM registro_decisioni WHERE tipo='richiesta_info' ORDER BY id")
    ok("risposta a una richiesta: registrata con persona, domanda e risposta", rg[0][0] == "Lorenzo" and rg[0][1] == "risposta data" and "CUP" in rg[0][2] and "B53C" in rg[0][3], str(rg))
    ok("annullamento: registrato con la persona che l'ha fatto", rg[1][0] == "=Cmd" and rg[1][1] == "annullata")
    # garanzie e chiavi
    c.put("/gestione/fornitori/openai", headers=H, json={"non_conservazione_attiva": True, "dpa_firmato": False})
    c.put("/gestione/fornitori/openai/chiave", headers=H, json={"chiave": "sk-test-1234567890abcdefghij"})
    t = {x[0]: x for x in sql("SELECT tipo, esito, oggetto, dettagli::text FROM registro_decisioni WHERE tipo IN ('garanzie_fornitore','chiave_fornitore')")}
    ok("garanzie del fornitore registrate", "garanzie_fornitore" in t and "true" in t["garanzie_fornitore"][3])
    ok("chiave registrata ma MAI il valore", "chiave_fornitore" in t and "sk-test" not in str(sql("SELECT * FROM registro_decisioni")))
    # task
    tid = c.post("/task", headers=H, json={"titolo": "Preparare il budget", "assegnato_utente_id": sql("SELECT id FROM utenti WHERE nome='Lorenzo'")[0][0]}).json().get("id")
    c.put(f"/task/{tid}", headers=H2, json={"stato": "completata"})
    c.put(f"/task/{tid}", headers=H, json={"assegnato_agente_id": scout})
    tk = sql("SELECT utente_nome, esito FROM registro_decisioni WHERE tipo='task' ORDER BY id")
    ok("task: cambio di stato e riassegnazione registrati con chi li ha fatti", ("=Cmd", "stato: da_fare → completata") in tk or any(x[0] == "=Cmd" and "completata" in x[1] for x in tk), str(tk))
    ok("task: riassegnazione", any(x[0] == "Lorenzo" and x[1] == "riassegnata" for x in tk), str(tk))
    # proposta
    pid = sql("INSERT INTO proposte_sviluppo (agente_id, titolo, descrizione, stato) VALUES (%s,'Nuovo agente grafica','x','proposta') RETURNING id", (scout,))[0][0] if "descrizione" in str(sql("SELECT column_name FROM information_schema.columns WHERE table_name='proposte_sviluppo'")) else None
    if pid:
        c.post(f"/agenti/proposte/{pid}/decisione", headers=H, json={"decisione": "approvata", "note": "ok per il collaudo"})
        ok("proposta di sviluppo approvata: registrata", sql("SELECT count(*) FROM registro_decisioni WHERE tipo='proposta_sviluppo' AND utente_nome='Lorenzo'")[0][0] == 1)
    # immutabilita'
    def prova(q):
        try: sql(q); return False
        except Exception as e: return "non si modifica" in str(e)
    ok("il registro non si modifica", prova("UPDATE registro_decisioni SET esito='x' WHERE id=(SELECT min(id) FROM registro_decisioni)"))
    ok("il registro non si cancella", prova("DELETE FROM registro_decisioni"))
    ok("neppure con TRUNCATE-like sulla singola riga (nome utente)", prova("UPDATE registro_decisioni SET utente_nome='Altro' WHERE id=(SELECT min(id) FROM registro_decisioni)"))
    # lettura e filtri
    d = c.get("/gestione/registro", headers=H).json()
    ok("elenco con tipi e persone", len(d["righe"]) >= 5 and "richiesta_info" in d["tipi"] and len(d["persone"]) == 2, str(len(d["righe"])))
    uid2 = sql("SELECT id FROM utenti WHERE nome='=Cmd'")[0][0]
    f = c.get(f"/gestione/registro?utente_id={uid2}", headers=H).json()["righe"]
    ok("filtro per persona", f and all(x["utente_nome"] == "=Cmd" for x in f))
    ok("filtro per tipo", all(x["tipo"] == "task" for x in c.get("/gestione/registro?tipo=task", headers=H).json()["righe"]))
    ok("ricerca testuale", len(c.get("/gestione/registro?q=budget", headers=H).json()["righe"]) >= 1)
    ok("filtro date nel futuro: vuoto", c.get("/gestione/registro?dal=2999-01-01", headers=H).json()["righe"] == [])
    csv = c.get("/gestione/registro?formato=csv", headers=H)
    ok("esportazione CSV", csv.status_code == 200 and "text/csv" in csv.headers["content-type"] and "Preparare il budget" in csv.content.decode("utf-8-sig"))
    ok("CSV: i nomi che iniziano con = non diventano formule", "'=Cmd" in csv.content.decode("utf-8-sig") and ";=Cmd" not in csv.content.decode("utf-8-sig"))
    ok("senza accesso: 401/403", c.get("/gestione/registro").status_code in (401, 403))
    # eliminazione utente: il nome resta
    sql("UPDATE registro_decisioni SET utente_id=NULL WHERE utente_id=%s", (uid2,))   # cio' che fa ON DELETE SET NULL
    ok("se l'utente sparisce il riferimento si azzera ma il nome resta scritto (unica modifica ammessa)", sql("SELECT count(*) FROM registro_decisioni WHERE utente_nome='=Cmd' AND utente_id IS NULL")[0][0] >= 1)
print(f"TOTALE {sum(ris)}/{len(ris)}")
