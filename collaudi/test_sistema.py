import os, sys, tempfile, shutil, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app import backup, allarmi, spesa, esecuzione, google
from app.fornitori import Risposta
from app.main import app
from app.db import connessione
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
sql("UPDATE fornitori_ai SET non_conservazione_attiva = TRUE, dpa_firmato = TRUE, fascia_dati_max = 'riservato'")
esecuzione.chiama_modello = lambda *a, **k: Risposta("ok", 10, 5)
scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
tmp = Path(tempfile.mkdtemp())
backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"
backup.FILE_ENV.write_text("CHIAVE_CASSAFORTE=SEGRETO-CASSAFORTE-123\nDATABASE_URL=x\n")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    # ---- tetto di spesa
    ok("senza tetti non blocca", spesa.controlla(connessione().__enter__()) is None)
    r = c.put("/gestione/sistema/spesa", headers=H, json={"giorno": 10, "mese": 100})
    ok("tetti salvati", r.status_code == 200 and c.get("/gestione/sistema", headers=H).json()["spesa"]["limiti"] == {"giorno": 10.0, "mese": 100.0})
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) VALUES (%s,'m',1,1,8.5,'lavoro')", (scout,))
    ch = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"})
    ok("all'85% l'agente lavora ancora", ch.status_code == 200, ch.text[:200])
    av = sql("SELECT testo, urgente FROM notifiche WHERE testo LIKE 'Spesa giornaliera%'")
    ok("avviso all'80% (una volta, urgente)", len(av) == 1 and av[0][1] is True, str(av))
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao ancora", "fascia_dati": "pubblico"})
    ok("l'avviso non si ripete", len(sql("SELECT 1 FROM notifiche WHERE testo LIKE 'Spesa giornaliera%'")) == 1)
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) VALUES (%s,'m',1,1,2,'lavoro')", (scout,))
    ch = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"})
    ok("al 100% gli agenti si fermano con messaggio chiaro", ch.status_code in (409, 423, 403, 400) and "Tetto di spesa" in ch.text, f"{ch.status_code} {ch.text[:200]}")
    ok("notifica di blocco", len(sql("SELECT 1 FROM notifiche WHERE testo LIKE 'Tetto di spesa giornaliero raggiunto%'")) == 1)
    c.put("/gestione/sistema/spesa", headers=H, json={"giorno": 0, "mese": 0})
    ok("togliendo i tetti riparte", c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"}).status_code == 200)
    ok("modelli senza prezzo segnalati", isinstance(c.get("/gestione/sistema", headers=H).json()["spesa"]["modelli_senza_prezzo"], list))
    ok("valori negativi rifiutati", c.put("/gestione/sistema/spesa", headers=H, json={"giorno": -5}).status_code == 422)
    # ---- backup
    ok("senza chiave il backup non e' da fare", not backup.da_fare(connessione().__enter__()))
    r = c.post("/gestione/sistema/backup/chiave", headers=H)
    k = r.json().get("chiave")
    ok("chiave creata e mostrata", r.status_code == 201 and len(k) == 44)
    ok("la chiave e' cifrata nel database", k not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='backup_chiave_cifrata'")[0][0])
    ok("seconda richiesta rifiutata (non si riscrive per sbaglio)", c.post("/gestione/sistema/backup/chiave", headers=H).status_code == 409)
    backup._dump = lambda: b"CREATE TABLE prova (x int);\n-- dati riservati: Mario Rossi\n"
    e = c.post("/gestione/sistema/backup/ora", headers=H).json()
    ok("backup eseguito", e["ok"] and e["dimensione"] > 0 and "Drive non collegato" in e["drive"], str(e))
    f = next((tmp / "bk").glob("*.enc"))
    grezzo = f.read_bytes()
    ok("il file non contiene nulla in chiaro (ne' dati ne' .env)", b"Mario Rossi" not in grezzo and b"SEGRETO-CASSAFORTE" not in grezzo and b"CREATE TABLE" not in grezzo)
    cont = backup.apri(str(f), k)
    ok("con la chiave si riapre: database e .env", b"Mario Rossi" in cont["database.sql"] and b"SEGRETO-CASSAFORTE-123" in cont["env.txt"])
    try: backup.apri(str(f), Fernet.generate_key().decode()); errore = False
    except backup.ErroreBackup: errore = True
    ok("con una chiave sbagliata non si apre", errore)
    ok("permessi del file ristretti", oct(f.stat().st_mode)[-3:] == "600")
    ok("dopo un backup riuscito non e' da rifare", not backup.da_fare(connessione().__enter__()))
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='backup_ultimo_ok'", ((datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),))
    ok("dopo 25 ore e' da rifare", backup.da_fare(connessione().__enter__()))
    for i in range(20):
        (tmp / "bk" / f"opifex-backup-2020010{i % 10}-0000{i:02d}.enc").write_bytes(b"x")
    backup._potatura()
    ok("restano solo gli ultimi 14", len(list((tmp / "bk").glob("opifex-backup-*.enc"))) == 14)
    # pg_dump assente / errore
    def rotto(): raise backup.ErroreBackup("pg_dump non e' installato sul server")
    backup._dump = rotto
    e = c.post("/gestione/sistema/backup/ora", headers=H).json()
    ok("errore del dump: esito negativo chiaro, nessun file nuovo", e["ok"] is False and "pg_dump" in e["dettaglio"])
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='backup_ultimo_ok'", ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),))
    ok("dopo un tentativo fallito non riprova subito (max ogni 2 ore)", not backup.da_fare(connessione().__enter__()))
    # upload su Drive simulato
    backup._dump = lambda: b"SELECT 1;"
    google._leggi = lambda conn, k: "1" if k == "drive_account_id" else ""
    google.token_accesso = lambda conn, a: "tok"; google.radice_valida = lambda conn, t: "RADICE"
    google.cartella = lambda tok, nome, gen, es=None: "CARTELLA-" + nome
    caricati = []
    google._http = lambda m, u, **kw: caricati.append((m, u, kw)) or {"id": "f1"}
    e = backup.esegui(connessione().__enter__())
    ok("caricamento su Drive nella cartella Backup, file cifrato", "caricato su Drive" in e["drive"] and caricati and b"CARTELLA-Backup" in caricati[0][2]["content"] and b"SELECT 1" not in caricati[0][2]["content"], str(e))
    ok("stato del backup leggibile", c.get("/gestione/sistema", headers=H).json()["backup"]["ultimo"]["ok"] is True)
    ok("riservato al titolare", c.get("/gestione/sistema").status_code in (401, 403) and c.post("/gestione/sistema/backup/ora").status_code in (401, 403))
    ok("le azioni sul backup entrano nel registro decisioni", sql("SELECT count(*) FROM registro_decisioni WHERE tipo IN ('backup','tetto_spesa')")[0][0] >= 3)
    # ---- allarmi
    import app.allarmi as al
    sql("DELETE FROM notifiche"); sql("DELETE FROM impostazioni_sistema WHERE chiave LIKE 'allarme_%'")
    class U: used = 90; total = 100
    al.shutil.disk_usage = lambda p: U
    with connessione() as conn:
        out = al.controlla(conn)
    ok("allarme disco pieno", any("disco" in x for x in out), str(out))
    with connessione() as conn:
        out2 = al.controlla(conn)
    ok("lo stesso allarme non si ripete entro 6 ore", not any("disco" in x for x in out2))
    al.shutil.disk_usage = lambda p: type("V", (), {"used": 10, "total": 100})
    for i in range(3):
        sql("INSERT INTO registro_azioni (azione, dettagli) VALUES ('errore_modello', %s::jsonb)", (json.dumps({"errore": "Anthropic: 401 invalid x-api-key"}),))
    with connessione() as conn:
        out3 = al.controlla(conn)
    ok("allarme errori ripetuti del fornitore", any("Anthropic" in x for x in out3), str(out3))
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='backup_ultimo_ok'", ((datetime.now(timezone.utc) - timedelta(hours=40)).isoformat(),))
    with connessione() as conn:
        out4 = al.controlla(conn)
    ok("allarme backup vecchio", any("backup" in x.lower() for x in out4), str(out4))
    ok("gli allarmi sono notifiche urgenti (vanno su Telegram)", sql("SELECT count(*) FROM notifiche WHERE urgente AND testo LIKE 'ALLARME:%'")[0][0] >= 3)
    ok("controllo manuale", c.post("/gestione/sistema/allarmi/prova", headers=H).status_code == 200)
shutil.rmtree(tmp, ignore_errors=True)
print(f"TOTALE {sum(ris)}/{len(ris)}")
