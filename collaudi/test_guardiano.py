import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from app.main import app
from app import guardiano, scuola
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
ACCESO = [True]
guardiano.computer_acceso = lambda: ACCESO[0]
def esiti(k):
    return {x["chiave"]: x for x in guardiano.controlla(k)}

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    k = psycopg.connect(DSN, row_factory=dict_row)
    cid = sql("SELECT id FROM competenze LIMIT 1")[0][0]
    tid = sql("SELECT id FROM casati_target ORDER BY id LIMIT 1")[0][0]
    ok("niente in coda: va, e lo dice", esiti(k)["casati"]["stato"] == "va" and "Niente in coda" in esiti(k)["casati"]["messaggio"])

    # il caso di Lorenzo: tanti tentativi non riusciti, nessun risultato, video in coda
    for i in range(6):
        sql("INSERT INTO casati_registro (tipo, testo) VALUES ('carta', %s)", (f"Carta d'identita' di «X{i}»: (non riuscita)",))
    sql("INSERT INTO competenze_fonti (competenza_id, target_id, rif, titolo) SELECT %s, %s, 'V' || g, 'Video ' || g FROM generate_series(1,5) g", (cid, tid))
    e = esiti(k)["casati"]
    ok("lavora ma non produce: FERMO, con la causa e cosa fare", e["stato"] == "fermo" and "non produce" in e["messaggio"] and "6 tentativi" in e["messaggio"] and "diario" in e["fare"], e)
    sql("DELETE FROM casati_registro")
    e = esiti(k)["casati"]
    ok("video in coda e nessuno studiato da 6 ore: FERMO", e["stato"] == "fermo" and "5 video da studiare ma nessuno studiato" in e["messaggio"], e)
    sql("UPDATE casati_target SET errore='DownloadError: HTTP 404' WHERE id=%s", (tid,))
    ok("e se un canale non si elenca, lo dice", "HTTP 404" in esiti(k)["casati"]["messaggio"])
    ACCESO[0] = False
    e = esiti(k)
    ok("computer spento: solo attenzione (non e' colpa sua), e il modello locale e' segnalato", e["casati"]["stato"] == "attenzione" and "nessun computer" in e["casati"]["messaggio"]
       and e["locale"]["stato"] == "attenzione")
    ACCESO[0] = True
    scuola._scrivi(k, "casati3_youtube_bloccato_fino", "2099-01-01T00:00:00+00:00"); k.commit()
    ok("YouTube blocca il server: FERMO, con la soluzione", esiti(k)["casati"]["stato"] == "fermo" and "YouTube blocca" in esiti(k)["casati"]["messaggio"])
    scuola._scrivi(k, "casati3_youtube_bloccato_fino", ""); k.commit()

    # notifica dopo un'ora di fermo, una volta sola
    sql("DELETE FROM notifiche")
    guardiano.giro(k); k.commit()
    ok("primo giro: segna l'inizio del fermo, nessuna notifica ancora", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'GUARDIANO:%%'") == [(0,)]
       and sql("SELECT 1 FROM impostazioni_sistema WHERE chiave='guardiano_dal_casati'") == [(1,)])
    sql("UPDATE impostazioni_sistema SET valore=(NOW() - INTERVAL '2 hours')::text WHERE chiave='guardiano_dal_casati'")
    sql("UPDATE impostazioni_sistema SET valore=to_char(NOW() - INTERVAL '2 hours', 'YYYY-MM-DD\"T\"HH24:MI:SS.US+00:00') WHERE chiave='guardiano_dal_casati'")
    avvisi = guardiano.giro(k); k.commit()
    n = sql("SELECT testo, urgente, critica FROM notifiche WHERE testo LIKE 'GUARDIANO:%%'")
    ok("fermo da piu' di un'ora: notifica urgente con causa e cosa fare", len(n) == 1 and "Padre Casati e' fermo" in n[0][0] and "Cosa" not in n[0][0] and n[0][1] and n[0][2] and avvisi, n)
    guardiano.giro(k); k.commit()
    ok("non ripete la notifica", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'GUARDIANO:%%'") == [(1,)])
    sql("UPDATE casati_target SET errore='' WHERE id=%s", (tid,))
    sql("UPDATE competenze_fonti SET stato='integrata', studiata_il=NOW() WHERE rif='V1'")
    guardiano.giro(k); k.commit()
    ok("ripartito: va, e il fermo si dimentica", esiti(k)["casati"]["stato"] == "va" and not sql("SELECT 1 FROM impostazioni_sistema WHERE chiave LIKE 'guardiano_%%casati'"))

    # posta
    sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, oggetto, creata_il) SELECT 'gmail', 1, 'm' || g, 'Email ' || g, NOW() - INTERVAL '3 hours' FROM generate_series(1,6) g""")
    e = esiti(k)["posta"]
    ok("posta: 6 email aspettano e nessuna letta: FERMO", e["stato"] == "fermo" and "6 email aspettano" in e["messaggio"] and "Controlla adesso" in e["fare"], e)
    sql("UPDATE posta_vaglio SET categoria='normale', vagliata_il=NOW()")
    ok("posta che legge: va", esiti(k)["posta"]["stato"] == "va")

    # un agente che sbaglia
    aid = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]
    for t in ("inizio", "errore", "inizio", "errore", "inizio", "errore", "inizio", "fine"):
        sql("INSERT INTO eventi_lavoro (agente_id, tipo) VALUES (%s,%s)", (aid, t))
    e = esiti(k).get(f"agente_{aid}")
    ok("agente con meta' delle richieste in errore: FERMO, porta alla Scatola nera", e and e["stato"] == "fermo" and "3 errori" in e["messaggio"] and e["vista"] == "sez:scatolanera", e)
    # domanda bloccante senza risposta
    pid = sql("SELECT id FROM agenti WHERE nome='Padre Casati'")[0][0]
    sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante, creata_il) VALUES (%s,'chiave YouTube?',TRUE, NOW() - INTERVAL '20 hours')", (pid,))
    e = esiti(k).get("bloccato_Padre Casati")
    ok("domanda bloccante senza risposta da ore: attenzione, rispondi in Plancia", e and e["stato"] == "attenzione" and "bloccante" in e["messaggio"], e)
    # compito fermo
    sql("INSERT INTO task (titolo, stato, assegnato_agente_id, aggiornata_il) VALUES ('Piano editoriale Renovatio','in_corso',%s, NOW() - INTERVAL '9 hours')", (aid,))
    ok("compito «in corso» da ore senza novita': attenzione", any(x["chiave"].startswith("task_") and "Piano editoriale" in x["messaggio"] for x in guardiano.controlla(k)))

    # campagne: il tetto giornaliero non e' un fermo
    from app import campagne
    cp = sql("INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine', 'gmail:1', 'in_corso') RETURNING id")[0][0]
    sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, campagna_id, tipo_campagna, stato, decisa_il)
           SELECT 'gmail', 1, 'l@p.it', 'x'||g||'@c.it', 'o', 't', %s, 'primo', 'approvata', NOW() - INTERVAL '3 hours' FROM generate_series(1,5) g""", (cp,))
    ok("campagne: approvate ferme da ore, niente partito oggi: fermo", esiti(k)["campagne"]["stato"] == "fermo")
    campagne.MAX_GIORNO, vecchio = 3, campagne.MAX_GIORNO
    sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, campagna_id, tipo_campagna, stato, decisa_il)
           SELECT 'gmail', 1, 'l@p.it', 'y'||g||'@c.it', 'o', 't', %s, 'primo', 'inviata', date_trunc('day', NOW()) + INTERVAL '1 minute' FROM generate_series(1,3) g""", (cp,))
    e = esiti(k)["campagne"]
    ok("campagne: tetto del giorno raggiunto: attenzione (niente notifica), dice che ripartono domani", e["stato"] == "attenzione" and "Tetto di oggi" in e["messaggio"] and "domani" in e["messaggio"], e)
    campagne.MAX_GIORNO = vecchio
    sql("UPDATE campagne_posta SET stato='bozza' WHERE id=%s", (cp,))

    # la schermata
    d = c.get("/gestione/guardiano", headers=H).json()
    ok("API: prima i fermi, con i conteggi e l'ultimo giro", d["esiti"][0]["stato"] == "fermo" and d["fermi"] >= 1 and d["attenzione"] >= 2 and d["ultimo_giro"])
    ok("solo il titolare", c.get("/gestione/guardiano").status_code in (401, 403))
    js = open("app/static/plancia.js").read()
    ok("Plancia: il guardiano e' il primo riquadro e si aggiorna", "guardiano.el, lavoro.el" in js and 'giro("g", guardiano.ricarica)' in js and "Il guardiano non gira" in js)
    ok("il guardiano gira con gli altri lavori di fondo", "guardiano del lavoro" in open("app/main.py").read())
    k.close()

print(f"TOTALE: {sum(ris)}/{len(ris)}")
