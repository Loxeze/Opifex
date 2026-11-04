import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import archivio_nas as an, richieste
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
cn = sql("INSERT INTO archivio_connettori (nome, token_hash) VALUES ('NAS','h') RETURNING id")[0][0]
k1 = sql("INSERT INTO archivio_cartelle (connettore_id, nome, percorso) VALUES (%s,'Bandi','/b') RETURNING id", (cn,))[0][0]
k2 = sql("INSERT INTO archivio_cartelle (connettore_id, nome, percorso) VALUES (%s,'Famiglia','/f') RETURNING id", (cn,))[0][0]
for i in range(25):
    sql("INSERT INTO archivio_file (cartella_id, rel, nome, tipo, visto_scan, descrizione) VALUES (%s,%s,%s,'foto',5,'bando %s')", (k1, f"b{i}.jpg", f"b{i}.jpg", i))
for i in range(3):
    sql("INSERT INTO archivio_file (cartella_id, rel, nome, tipo, visto_scan, descrizione) VALUES (%s,%s,%s,'foto',5,'bando famiglia %s')", (k2, f"f{i}.jpg", f"f{i}.jpg", i))
ag = sql("INSERT INTO agenti (nome, ruolo, livello, istruzioni) VALUES ('Scrittore','r','operativo','i') RETURNING id")[0][0]
ag2 = sql("INSERT INTO agenti (nome, ruolo, livello, istruzioni) VALUES ('Libero','r','operativo','i') RETURNING id")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    with connessione() as conn:
        an._avvisa_novita(conn, k1, 5, None, "Bandi"); an._avvisa_novita(conn, k2, 5, None, "Famiglia")
    ok("avviso solo per il gruppo grosso", sql("SELECT count(*) FROM archivio_novita")[0][0] == 1 and sql("SELECT nuovi FROM archivio_novita")[0][0] == 25)
    ok("notifica creata", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Archivio NAS: aggiunti 25%'")[0][0] == 1)
    r = c.get("/gestione/archivio/novita", headers=H).json()
    ok("chi e' collegato vede l'avviso con esempi", len(r) == 1 and r[0]["nuovi"] == 25 and r[0]["cartella"] == "Bandi" and len(r[0]["esempi"]) == 6, r)
    nid = r[0]["id"]
    f = c.get(f"/gestione/archivio/cerca?novita_id={nid}", headers=H).json()
    ok("elenco dei soli file nuovi", len(f) == 25 and all(x["nome"].startswith("b") for x in f), len(f))
    c.post(f"/gestione/archivio/novita/{nid}/vista", headers=H)
    ok("dopo 'Ok' l'avviso sparisce", c.get("/gestione/archivio/novita", headers=H).json() == [])
    ok("imposta cartelle dell'agente", c.put(f"/gestione/archivio/cartelle-agente/{ag}", headers=H, json={"cartelle": [k1]}).status_code == 200 and c.get(f"/gestione/archivio/cartelle-agente/{ag}", headers=H).json()["scelte"] == [k1])
    g = an.gestore(connessione, ag); g2 = an.gestore(connessione, ag2)
    r1 = g("archivio_cerca", {"testo": "bando", "limite": 15})
    ok("agente con cartelle vede solo le sue", "b0.jpg" in r1 and "f0.jpg" not in r1, r1[:200])
    ok("agente senza restrizioni vede tutto", "f0.jpg" in g2("archivio_cerca", {"testo": "famiglia"}))
    fid = sql("SELECT id FROM archivio_file WHERE rel='f0.jpg'")[0][0]
    ok("non puo' leggere file fuori dalle sue cartelle", "non ti e' stata associata" in g("archivio_leggi", {"id": fid}))
    ok("ne' chiederne la foto", "non ti e' stata associata" in g("archivio_richiedi", {"id": fid, "tipo": "foto"}))
    # domande legate al progetto
    p1 = sql("INSERT INTO progetti (nome) VALUES ('Bando Alfa') RETURNING id")[0][0]
    p2 = sql("INSERT INTO progetti (nome) VALUES ('Bando Beta') RETURNING id")[0][0]
    sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id) VALUES ('t','in_corso',%s,%s)", (p1, ag))
    sql("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s)", (p2, ag2))
    with connessione() as conn:
        richieste.estrai_e_salva(conn, ag, "[MANCA] Qual e' il budget del bando Alfa?")
        richieste.estrai_e_salva(conn, ag2, "[MANCA] Chi e' il referente del bando Beta?")
    cont = c.get("/gestione/richieste/conteggio", headers=H).json()
    ok("conteggio per progetto", cont["per_progetto"] == {str(p1): 1, str(p2): 1}, cont)
    el = c.get(f"/gestione/richieste?stato=aperta&progetto_id={p1}", headers=H).json()
    ok("elenco filtrato per progetto con nome", len(el) == 1 and el[0]["progetto"] == "Bando Alfa" and el[0]["agente"] == "Scrittore", el)
    sql("INSERT INTO squadre_proposte (progetto_id, motivazione) VALUES (%s,'m')", (p1,))
    ok("le squadre da approvare contano nel progetto", c.get("/gestione/richieste/conteggio", headers=H).json()["per_progetto"][str(p1)] == 2)
print(f"TOTALE {sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
