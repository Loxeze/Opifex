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
from app import profilo_alto as pa, agente_browser as ab
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    a = conn.execute("SELECT id, modello, istruzioni, max_token_risposta, sforzo FROM agenti WHERE fascia_dati_max IN ('pubblico','interno') ORDER BY id LIMIT 1").fetchone()
    r = pa.applica(conn, a["id"])
    n = conn.execute("SELECT * FROM agenti WHERE id=%s", (a["id"],)).fetchone()
    ok("profilo attivo: passi, sforzo, metodo", n["profilo_alto"] and n["passi_max"] == 40 and n["sforzo"] == "high" and pa.MARCA in n["istruzioni"], str(r))
    ok("modello avanzato scelto se disponibile", (not r["modello_cambiato"]) or "opus" in r["modello"] or "fable" in r["modello"] or "mythos" in r["modello"], r["modello"])
    ok("token di risposta almeno 32000 e strumenti attivi", n["max_token_risposta"] >= 32000 and n["usa_biblioteca"] and n["sandbox_attivo"] and n["drive_attivo"])
    from app import modello_economico as me
    ok("risparmio: il cambio di massa non tocca l'agente in profilo alto", a["id"] not in [x["id"] for x in me.piano(conn)])
    ok("stile asciutto nel metodo", "Vietati ringraziamenti" in n["istruzioni"] and "RISPARMIO" in n["istruzioni"] and n["modello_dialogo"] is None)
    pa.applica(conn, a["id"])
    n2 = conn.execute("SELECT istruzioni, profilo_prima FROM agenti WHERE id=%s", (a["id"],)).fetchone()
    ok("secondo clic: metodo non duplicato e stato di prima conservato", n2["istruzioni"].count(pa.MARCA) == 1 and n2["profilo_prima"]["istruzioni"] == a["istruzioni"])
    ok("passi dell'agente letti dal contesto", ab._passi() == ab.MAX_PASSI and (ab.PASSI_AGENTE.set(40) and ab._passi() == 40))
    ok("ripristino", pa.ripristina(conn, a["id"]))
    n3 = conn.execute("SELECT * FROM agenti WHERE id=%s", (a["id"],)).fetchone()
    ok("ripristino: tutto com'era", not n3["profilo_alto"] and n3["passi_max"] is None and n3["istruzioni"] == a["istruzioni"] and n3["modello"] == a["modello"] and n3["max_token_risposta"] == a["max_token_risposta"] and n3["sforzo"] == a["sforzo"])
    ok("ripristino senza profilo: falso", not pa.ripristina(conn, a["id"]))
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
