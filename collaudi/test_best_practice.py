import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import db
db.apri_pool()
from app import best_practice as bp, scheda_progetto, fornitori, rotte_best_practice as rb, rotte_progetti as rp
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/110_best_practice.sql').read())
    conn.execute("DELETE FROM best_practice")
    conn.execute('UPDATE fornitori_ai SET non_conservazione_attiva = TRUE, dpa_firmato = TRUE')
    conn.execute("INSERT INTO aziende (nome) VALUES ('Impresa BP') ON CONFLICT DO NOTHING")
    az = conn.execute("SELECT id FROM aziende LIMIT 1").fetchone()["id"]
    a = conn.execute("SELECT id FROM agenti WHERE attivo AND NOT COALESCE(sentinella, FALSE) AND ruolo_speciale IS NULL ORDER BY id LIMIT 1").fetchone()["id"]
    p1 = conn.execute("INSERT INTO progetti (nome, azienda_id, descrizione, obiettivo) VALUES ('Reel Pilota', %s, 'Montaggio reel verticale', 'Un reel verticale di 30 secondi dalle riprese grezze') RETURNING id", (az,)).fetchone()["id"]
    vuoto = conn.execute("INSERT INTO progetti (nome, azienda_id) VALUES ('Vuoto', %s) RETURNING id", (az,)).fetchone()["id"]
    scheda_progetto.aggiungi_decisione(conn, p1, "Formato verticale 9:16 con sottotitoli bruciati", agente_id=a)
    d2 = scheda_progetto.aggiungi_decisione(conn, p1, "Consegna in 4K nativo", agente_id=a)
    scheda_progetto.supera_decisione(conn, p1, d2)
    conn.execute("INSERT INTO task (titolo, stato, progetto_id) VALUES ('Selezione riprese', 'completata', %s)", (p1,))
    # senza modello: scheda composta dal codice
    i = bp.genera(conn, p1, usa_modello=False)
    r = conn.execute("SELECT * FROM best_practice WHERE id=%s", (i,)).fetchone()
    ok("genera dal codice con decisioni e task", i and "9:16" in r["cosa_funziona"] and "4K" in r["da_evitare"] and "Selezione riprese" in r["checklist"], str(r))
    ok("progetto senza materiale: nessuna scheda", bp.genera(conn, vuoto, usa_modello=False) is None)
    ok("rigenerare aggiorna la stessa scheda", bp.genera(conn, p1, usa_modello=False) == i and conn.execute("SELECT count(*) n FROM best_practice").fetchone()["n"] == 1)
    # modello finto
    class R:  # noqa
        testo = '{"titolo":"Reel verticale da riprese grezze","tipo":"video","contesto":"Montaggio di reel","cosa_funziona":["Sottotitoli bruciati","Selezione prima del montaggio"],"da_evitare":"- Promettere 4K da 1080p","checklist":["Elenca le riprese","Monta"]}'
    fornitori.chiama_modello = lambda *a_, **k: R()
    from app import catalogo_modelli
    catalogo_modelli.scegli_per_dialogo = lambda c, ag: conn.execute("SELECT nome FROM modelli_ai LIMIT 1").fetchone()["nome"]
    conn.execute("UPDATE fornitori_ai SET fascia_dati_max = 'riservato'")
    bp.genera(conn, p1)
    r = conn.execute("SELECT * FROM best_practice WHERE id=%s", (i,)).fetchone()
    ok("modello: scheda strutturata e tipo valido", r["tipo"] == "video" and "Sottotitoli" in r["cosa_funziona"] and r["titolo"].startswith("Reel verticale"), str(r))
    R.testo = "non e' json"
    bp.genera(conn, p1)
    ok("risposta non valida: ripiego sul codice", conn.execute("SELECT titolo FROM best_practice WHERE id=%s", (i,)).fetchone()["titolo"].startswith("Come abbiamo"))
    # ricerca
    t = bp.cerca(conn, "montaggio reel verticale per Instagram")
    ok("cerca trova la scheda per parole chiave", t and t[0]["id"] == i)
    ok("cerca: nulla di pertinente", bp.cerca(conn, "bilancio fiscale trimestrale") == [])
    ok("cerca esclude il progetto stesso se richiesto", bp.cerca(conn, "montaggio reel verticale", escludi_progetto=p1) == [])
    out = bp.esegui(conn, {"argomento": "reel verticale"})
    ok("strumento: restituisce la scheda e conta l'uso", "BUONA PRATICA" in out and conn.execute("SELECT usata_n FROM best_practice WHERE id=%s", (i,)).fetchone()["usata_n"] == 1)
    ok("strumento: nessun risultato è un messaggio, non un errore", "Nessuna buona pratica" in bp.esegui(conn, {"argomento": "xyzzy"}))
    # contesto per un agente di un altro progetto simile
    p2 = conn.execute("INSERT INTO progetti (nome, azienda_id, descrizione, obiettivo) VALUES ('Nuovo reel', %s, 'Reel verticale per il lancio', 'Montaggio di un reel verticale') RETURNING id", (az,)).fetchone()["id"]
    conn.execute("DELETE FROM progetti_agenti WHERE agente_id=%s", (a,))
    conn.execute("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s)", (p2, a))
    ag = {"id": a, "fascia_dati_max": "interno", "fascia_fornitore": "interno", "non_conservazione_attiva": True, "dpa_firmato": True}
    c = bp.contesto(conn, ag)
    ok("contesto: l'agente del nuovo progetto riceve la buona pratica", "BUONE PRATICHE" in c and "Reel Pilota" in c, c[:200])
    ok("contesto: vuoto se i dati interni non possono uscire", bp.contesto(conn, {**ag, "fascia_dati_max": "pubblico"}) == "")
    conn.execute("UPDATE best_practice SET stato='scartata'")
    ok("contesto: le schede scartate non vengono usate", bp.contesto(conn, ag) == "" and bp.cerca(conn, "reel verticale") == [])
    conn.execute("UPDATE best_practice SET stato='attiva'")
    # gestione
    rb.modifica(i, rb.Modifica(titolo="Titolo rivisto"), None)
    r = conn.execute("SELECT titolo, origine FROM best_practice WHERE id=%s", (i,)).fetchone()
    ok("modifica a mano: resta manuale", r["titolo"] == "Titolo rivisto" and r["origine"] == "manuale")
    bp.genera(conn, p1, usa_modello=False)
    ok("una scheda rivista a mano non viene riscritta", conn.execute("SELECT titolo FROM best_practice WHERE id=%s", (i,)).fetchone()["titolo"] == "Titolo rivisto")
    el = rb.elenco(None)
    ok("elenco con tipi", el["schede"] and "video" in el["tipi"])
    rb.genera(p1, None)
    rp._buona_pratica(p1)
    ok("archiviazione: la scheda si ricava senza errori", conn.execute("SELECT count(*) n FROM best_practice WHERE progetto_id=%s", (p1,)).fetchone()["n"] == 1)
    from app import scheda_progetto as sp
    ok("lo strumento e' tra quelli della scheda progetto", any(s["name"] == "best_practice_cerca" for s in sp.STRUMENTI))
    g = sp.gestore(lambda: __import__("app.db", fromlist=["x"]).connessione(), a)
    ok("gestore instrada best_practice_cerca", "BUONA PRATICA" in g("best_practice_cerca", {"argomento": "reel verticale"}) or "Titolo rivisto" in g("best_practice_cerca", {"argomento": "reel verticale"}))
print(f"\n{sum(ris)}/{len(ris)} ok")
sys.exit(0 if all(ris) else 1)
