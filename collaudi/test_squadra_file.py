import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import dialoghi, strumenti_google, accessi_agenti
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    az = conn.execute("INSERT INTO aziende (nome, attiva) VALUES ('T', TRUE) RETURNING id").fetchone()["id"] if False else None
    ids = [r["id"] for r in conn.execute("SELECT id FROM agenti WHERE attivo AND NOT COALESCE(sentinella, FALSE) AND ruolo_speciale IS NULL AND livello IS NOT NULL ORDER BY id LIMIT 3").fetchall()]
    a, b, c_ = ids[0], ids[1], ids[2]
    conn.execute("UPDATE agenti SET superiore_id = NULL, livello = 'operativo' WHERE id IN (%s,%s)", (b, c_)) if False else None
    for x in (a, b):
        conn.execute("UPDATE agenti SET livello = 'operativo', superiore_id = NULL WHERE id = %s", (x,))
    prima = {r["id"] for r in dialoghi.colleghi(conn, a)}
    conn.execute("DELETE FROM progetti_agenti")
    p = conn.execute("INSERT INTO progetti (nome, azienda_id) VALUES ('Prova squadra', (SELECT id FROM aziende LIMIT 1)) RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s),(%s,%s)", (p, a, p, b))
    dopo = {r["id"] for r in dialoghi.colleghi(conn, a)}
    ok("con un progetto in comune si possono contattare", b in dopo)
    ok("la domanda su file riconosciuta", bool(dialoghi._RE_FILE.search("Vedi la cartella RIPRESE GREZZE?")) and bool(dialoghi._RE_FILE.search("durata e fps dei video")))
    ok("domande generiche non cambiano modalita'", not dialoghi._RE_FILE.search("Come impostereste il tono del reel?"))
    strumenti_google.collegato = lambda c: True
    conn.execute("UPDATE agenti SET drive_attivo = TRUE, fascia_dati_max = 'interno' WHERE id = %s", (b,))
    dest = {"id": b, "nome": "x"}
    ris_ = dialoghi._serve_esecuzione(conn, dest, "Elenca i file della cartella")
    m = accessi_agenti.motivo_senza_drive(conn, conn.execute("""SELECT a.id, a.fascia_dati_max, a.drive_attivo, m.nome AS modello_nome, f.nome AS fornitore, f.fascia_dati_max AS fascia_fornitore,
        f.non_conservazione_attiva, f.dpa_firmato FROM agenti a LEFT JOIN modelli_ai m ON m.nome = a.modello LEFT JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE a.id = %s""", (b,)).fetchone())
    ok("domanda su file: esecuzione completa se l'agente ha Drive, altrimenti risposta normale", ris_ == (m is None), str(m))
    ok("domande massime per compito allargate", conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='dialoghi_max_domande'").fetchone()["valore"] == "12")
print("TOTALE", sum(ris), "/", len(ris))
