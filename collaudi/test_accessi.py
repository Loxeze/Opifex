import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import accessi_agenti as aa, strumenti_google, richieste
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
base = {"fornitore": "anthropic", "modello_nome": "claude-haiku-5-5", "fascia_dati_max": "interno", "fascia_fornitore": "riservato",
        "non_conservazione_attiva": True, "dpa_firmato": True, "drive_attivo": True}
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    strumenti_google.collegato = lambda c: True
    ok("agente a posto: nessun motivo", aa.motivo_senza_drive(conn, base) is None)
    ok("Drive spento: motivo chiaro", "spento" in aa.motivo_senza_drive(conn, {**base, "drive_attivo": False}))
    ok("fascia dati troppo bassa: motivo chiaro", "fascia" in aa.motivo_senza_drive(conn, {**base, "fascia_dati_max": "pubblico"}))
    ok("fornitore senza DPA: motivo chiaro", aa.motivo_senza_drive(conn, {**base, "dpa_firmato": False}) is not None)
    ok("modello senza strumenti: motivo chiaro", "strumenti" in aa.motivo_senza_drive(conn, {**base, "fornitore": "gemini"}))
    strumenti_google.collegato = lambda c: False
    ok("Drive non collegato: motivo chiaro", "collegato" in aa.motivo_senza_drive(conn, base))
    ok("istruzione: vieta di rimandare a Lorenzo e indica il motivo", "Non chiedere a Lorenzo" in aa.istruzione_senza_drive("Drive spento") and "Drive spento" in aa.istruzione_senza_drive("Drive spento"))
    ok("regola comune: provare prima gli strumenti e non aprire task per accessi", "ACCESSO AI FILE E LAVORO CONTINUO" in richieste.REGOLA)
    n = len(conn.execute("SELECT id FROM agenti WHERE attivo AND NOT drive_attivo AND NOT COALESCE(sentinella, FALSE)").fetchall())
    conn.execute("UPDATE agenti SET drive_attivo = FALSE WHERE id = (SELECT id FROM agenti WHERE attivo AND NOT COALESCE(sentinella, FALSE) LIMIT 1)")
    from fastapi.testclient import TestClient
print("TOTALE", sum(ris), "/", len(ris))
