import os, sys, time
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import db; db.apri_pool()
from app import chat_coda as cc
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/60_z_chat_coda_ripresa.sql').read())
    a = conn.execute("SELECT id FROM agenti LIMIT 1").fetchone()["id"]
    u = conn.execute("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','rip@p.it','x','titolare') RETURNING id").fetchone()["id"]
    chiamate = []
    cc._lavora = lambda *x: chiamate.append(x)
    def riga(**k):
        v = dict(stato="in_lavoro", con_allegati=False, riprese=0, canale="web", fascia="interno", ore="0 hours")
        v.update(k)
        return conn.execute("INSERT INTO chat_coda (agente_id, utente_id, messaggio, canale, stato, fascia, con_allegati, riprese, creato_il) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW() - %s::interval) RETURNING id",
                            (a, u, "msg " + str(len(chiamate)), v["canale"], v["stato"], v["fascia"], v["con_allegati"], v["riprese"], v["ore"])).fetchone()["id"]
    r1, r2, r3, r4, r5 = riga(), riga(con_allegati=True), riga(ore="5 hours"), riga(riprese=1), riga(canale="ronda")
    n = cc.riavvio(conn); time.sleep(0.3)
    st = {i: conn.execute("SELECT stato, riprese FROM chat_coda WHERE id=%s", (i,)).fetchone() for i in (r1, r2, r3, r4, r5)}
    ok("il messaggio recente senza allegati riparte", n == 1 and st[r1]["stato"] == "in_coda" and st[r1]["riprese"] == 1 and chiamate and chiamate[0][0] == r1 and chiamate[0][4] == "interno", str(st))
    ok("con allegati: segnato come interrotto", st[r2]["stato"] == "errore")
    ok("troppo vecchio: interrotto", st[r3]["stato"] == "errore")
    ok("gia' ripreso una volta: interrotto (niente cicli)", st[r4]["stato"] == "errore")
    ok("canali di servizio non ripartono", st[r5]["stato"] == "errore")
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
