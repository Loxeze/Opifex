import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from app import competenze_base as cb, squadre
from app.db import connessione
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
from app.main import app
from fastapi.testclient import TestClient
with TestClient(app):
    with connessione() as cn:
        cb.applica(cn)
        cn.commit()
    ok("ogni agente specifico ha il verticale", all(cb.MARC_VERT in cb.con_blocchi(n, "operativo", t) for n, t in cb.COMPETENZE.items()))
    ok("i manager hanno il metodo di spezzettamento", cb.MARC_METODO in cb.con_blocchi("Legal Master", "manager", cb.COMPETENZE["Legal Master"]))
    ok("gli operativi non hanno il metodo manager", cb.MARC_METODO not in cb.con_blocchi("Tester", "operativo", cb.COMPETENZE["Tester"]))
    ok("agente sconosciuto operativo: verticale generico", cb.MARC_VERT in cb.con_blocchi("Pippo", "operativo", "x"))
    t = sql("SELECT istruzioni FROM agenti WHERE nome='Marco'")
    ok("Marco in database: verticale e metodo", t and cb.MARC_VERT in t[0][0] and cb.MARC_METODO in t[0][0])
    # idempotenza: personalizzato + riapplico
    sql("UPDATE agenti SET istruzioni='Testo mio' WHERE nome='Scout'")
    with connessione() as cn:
        n = cb._aggiunte(cn); cn.commit(); n2 = cb._aggiunte(cn)
    r = sql("SELECT istruzioni FROM agenti WHERE nome='Scout'")[0][0]
    ok("aggiunta in coda al testo personalizzato, una sola volta", n >= 1 and n2 == 0 and r.startswith("Testo mio") and r.count(cb.MARC_VERT) == 1)
    # organico
    sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES ('Capo prova','Capo','manager','divisione','claude-sonnet-5-5','riservato','x')")
    cid = sql("SELECT id FROM agenti WHERE nome='Capo prova'")[0][0]
    sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni, superiore_id) VALUES ('Sub uno','Analista','operativo','divisione','claude-sonnet-5-5','riservato','x',%s)", (cid,))
    sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni, superiore_id) VALUES ('Sub due','Revisore','operativo','divisione','claude-sonnet-5-5','riservato','x',%s)", (cid,))
    with connessione() as cn:
        o = squadre.organico(cn, cid)
        vuoto = squadre.organico(cn, sql("SELECT id FROM agenti WHERE nome='Sub uno'")[0][0])
    ok("organico elenca tutti i sottoposti", "Sub uno" in o and "Sub due" in o and "Analista" in o and "2 sottoposti" in o, o)
    ok("senza sottoposti: indicazione", "Non hai sottoposti" in vuoto)
    g = squadre.gestore(connessione, cid)
    ok("lo strumento squadra_organico risponde", "Sub due" in g("squadra_organico", {}))
    ok("strumento e metodo esposti", squadre.STRUMENTO_ORGANICO["name"] == "squadra_organico" and "SPEZZETTARE" in squadre.AVVISO_SPEZZETTA)
    ok("documentazione include il verticale", cb.MARC_VERT in cb.documentazione())
print("TOTALE", sum(ris), "/", len(ris))
