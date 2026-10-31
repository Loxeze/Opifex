import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import squadra_progetto as sq, scheda_progetto, strumenti_google as sg, google
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    sg.collegato = lambda c: True
    conn.execute(open('sql/109_squadra_allineata.sql').read())   # il banco di prova applica i file in ordine alfabetico: qui lo si applica dopo la creazione delle tabelle
    conn.execute('UPDATE fornitori_ai SET non_conservazione_attiva = TRUE, dpa_firmato = TRUE')
    ag = [r["id"] for r in conn.execute("SELECT id FROM agenti WHERE attivo AND NOT COALESCE(sentinella, FALSE) AND ruolo_speciale IS NULL ORDER BY id LIMIT 3").fetchall()]
    a, b, c3 = ag
    conn.execute("UPDATE agenti SET drive_attivo = FALSE, fascia_dati_max = 'pubblico' WHERE id = %s", (b,))
    conn.execute("UPDATE agenti SET drive_attivo = TRUE, fascia_dati_max = 'interno' WHERE id IN (%s,%s)", (a, c3))
    conn.execute("DELETE FROM progetti_agenti")
    p = conn.execute("INSERT INTO progetti (nome, azienda_id, drive_cartella_id) VALUES ('Squadra prova', (SELECT id FROM aziende LIMIT 1), 'CART1') RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s),(%s,%s),(%s,%s)", (p, a, p, b, p, c3))
    ok("entrando nel progetto Drive si accende da solo", conn.execute("SELECT drive_attivo FROM agenti WHERE id=%s", (b,)).fetchone()["drive_attivo"])
    conn.execute("UPDATE agenti SET drive_attivo = FALSE, fascia_dati_max = 'interno' WHERE id = %s", (b,))
    c = sq.controllo(conn, p)
    mb = [m for m in c["membri"] if m["id"] == b][0]
    ok("controllo: segnala chi e' senza Drive, con motivo", not c["allineata"] and mb["motivo"] and mb["correggibile_drive"])
    r = sq.allinea.__wrapped__(p, sq.Allinea(fascia_interna=False), None) if hasattr(sq.allinea, "__wrapped__") else None
    from app.db import connessione
    conn.execute("UPDATE agenti SET drive_attivo = TRUE, fascia_dati_max = 'pubblico' WHERE id = %s", (b,))
    c = sq.controllo(conn, p)
    mb = [m for m in c["membri"] if m["id"] == b][0]
    ok("fascia pubblico: segnalata come correggibile solo con consenso", mb["motivo"] and "fascia" in mb["motivo"] and mb["correggibile_fascia"])
    conn.execute("UPDATE agenti SET fascia_dati_max = 'interno' WHERE id = %s", (b,))
    ok("squadra allineata con cartella e Drive per tutti", sq.controllo(conn, p)["allineata"])
    # decisioni: avviso a tutti gli altri
    conn.execute("DELETE FROM avvisi_agente")
    scheda_progetto.aggiungi_decisione(conn, p, "Pietro e' il cliente: nessuna liberatoria", agente_id=a)
    avv = {r["agente_id"] for r in conn.execute("SELECT agente_id FROM avvisi_agente WHERE testo LIKE 'NUOVA DECISIONE%'").fetchall()}
    ok("decisione: avvisati tutti gli altri membri, non l'autore", avv == {b, c3}, str(avv))
    ok("scheda nel prompt: cartella Drive del progetto", "CART1" in scheda_progetto._testo_progetto(conn, p, "Squadra prova"))
    # cartella di default = progetto per chi ha un solo progetto
    ok("destinazione predefinita: cartella del progetto", sg._cartella_destinazione(conn, "tok", "RAD", None, a) == "CART1")
    # creazione cartella
    creati = []
    google.cartella = lambda tok, nome, gen, esistente=None: (creati.append((nome, gen)) or "NUOVA")
    sg._contesto = lambda conn: ("tok", ("RAD",))
    sg._nell_albero = lambda tok, fid, radici: fid in ("CART1",)
    o = sg._esegui(conn, a, "google_crea_cartella", {"nome": "reels"})
    ok("crea cartella 'reels' dentro il progetto", "pronta" in o and creati == [("reels", "CART1")], o)
    o = sg._esegui(conn, a, "google_crea_cartella", {"nome": "x", "dentro": "ESTERNA"})
    ok("cartella fuori dall'albero rifiutata", o.startswith("ERRORE") or creati[-1][1] == "CART1", o)
    ok("strumento nel catalogo", "google_crea_cartella" in [t["name"] for t in sg.STRUMENTI])
print("TOTALE", sum(ris), "/", len(ris))
