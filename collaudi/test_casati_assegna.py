import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import db; db.apri_pool()
from app import casati, ginnasio as g
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute("DELETE FROM documenti_agenti")
    cas = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale='formatore'").fetchone()["id"]
    ag = conn.execute("SELECT id, nome FROM agenti WHERE attivo AND id <> %s ORDER BY id LIMIT 3", (cas,)).fetchall()
    d1 = casati.salva_documento(conn, nome="Color grading con le curve in DaVinci", nome_file="cg.pdf", testo="Il color grading con le curve primarie e secondarie in DaVinci Resolve. " * 20, autori="Rossi", anno=2022)
    d2 = casati.salva_documento(conn, nome="Bando Interreg guida", nome_file="b.pdf", testo="Guida alla rendicontazione dei bandi europei Interreg. " * 20)
    conn.execute("UPDATE documenti SET fascia_dati='riservato' WHERE id=%s", (d2,))
    t = casati.documenti_da_assegnare(conn)
    ok("elenco: documenti senza destinatari e agenti", "Color grading" in t and "Bando Interreg" in t and ag[0]["nome"] in t, t[:300])
    r = casati.assegna_documento(conn, cas, {"documento": "color grading", "agenti": [ag[0]["nome"], ag[1]["nome"], "Inesistente"], "motivo": "serve al montaggio"})
    ok("assegna per titolo parziale, segnala il nome sbagliato", ag[0]["nome"] in r and "Inesistente" in r, r)
    n = conn.execute("SELECT count(*) n FROM documenti_agenti WHERE documento_id=%s", (d1,)).fetchone()["n"]
    ok("righe create", n == 2, str(n))
    ok("il documento assegnato esce dall'elenco", "Color grading" not in casati.documenti_da_assegnare(conn))
    ok("registrato nel registro azioni", conn.execute("SELECT 1 FROM registro_azioni WHERE azione='documento_assegnato'").fetchone() is not None)
    ok("documento inesistente", casati.assegna_documento(conn, cas, {"documento": "zzz", "agenti": ["x"]}).startswith("ERRORE"))
    ok("senza agenti: errore", casati.assegna_documento(conn, cas, {"documento": d1, "agenti": []}).startswith("ERRORE"))
    ok("conteggio da assegnare", g.conta_da_assegnare(conn) == 1, str(g.conta_da_assegnare(conn)))
    # formazione orfana
    comp = conn.execute("INSERT INTO richieste_formazione (competenza_nome, livello, agente_id, stato, avviata_il) VALUES ('Color grading', 2, %s, 'in_corso', NOW() - INTERVAL '4 days') RETURNING id", (ag[0]["id"],)).fetchone()["id"]
    n1 = g.recupera(conn)
    s1 = conn.execute("SELECT stato, riprese FROM richieste_formazione WHERE id=%s", (comp,)).fetchone()
    ok("formazione orfana rimessa in coda", n1 == 1 and s1["stato"] == "in_coda" and s1["riprese"] == 1, str(s1))
    conn.execute("UPDATE richieste_formazione SET stato='in_corso', avviata_il=NOW() - INTERVAL '1 hour', riprese=2 WHERE id=%s", (comp,))
    g.recupera(conn)
    ok("dopo troppe interruzioni: errore visibile", conn.execute("SELECT stato FROM richieste_formazione WHERE id=%s", (comp,)).fetchone()["stato"] == "errore")
    conn.execute("UPDATE richieste_formazione SET stato='in_corso', avviata_il=NOW(), riprese=0 WHERE id=%s", (comp,))
    ok("appena avviata non e' toccata", g.recupera(conn) == 0)
    conn.execute("UPDATE richieste_formazione SET avviata_il=NOW() - INTERVAL '1 hour' WHERE id=%s", (comp,))
    g.RUNNING.add(comp)
    ok("con lavoro attivo non e' toccata", g.recupera(conn) == 0)
    g.RUNNING.discard(comp)
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
