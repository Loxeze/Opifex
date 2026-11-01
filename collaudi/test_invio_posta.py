import os, sys, json, tempfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app.sicurezza import cifra_password
from app import invio_posta as ip, strumenti_gmail, strumenti_posta, cassaforte
from app.db import connessione
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@s.it',%s,'collaboratore')", (cifra_password(PW),))
# finto Gmail e finto SMTP
CH = []
def rich(metodo, url, tok, **kw):
    CH.append((metodo, url, kw))
    if url.endswith("/messages/send"): return {"id": "S1"}
    return {"threadId": "T9", "payload": {"headers": [{"name": "Message-ID", "value": "<orig@x>"}]}}
strumenti_gmail._richiesta = rich
strumenti_gmail.token_accesso = lambda conn, a: "tok"; ip.strumenti_gmail.token_accesso = lambda conn, a: "tok"
SMTP = []
class FakeSMTP:
    def __init__(self, host, porta, timeout=0, context=None): SMTP.append(("connect", host, porta))
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def login(self, u, p): SMTP.append(("login", u, p))
    def send_message(self, m): SMTP.append(("send", m["From"], m["To"], m["Subject"]))
ip.smtplib.SMTP_SSL = FakeSMTP
strumenti_posta.host_ammesso = lambda h: None
gm = sql("INSERT INTO account_google (etichetta,email,refresh_token_cifrato,servizi) VALUES ('Casella','l@gmail.test','x',ARRAY['gmail']) RETURNING id")[0][0]
ag = sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni, gmail_account_id) VALUES ('Posta','Posta','operativo','sistema',(SELECT nome FROM modelli_ai LIMIT 1),'riservato','x',%s) RETURNING id", (gm,))[0][0]
cas = sql("INSERT INTO caselle_posta (etichetta,email,host,utente,password_cifrata,stato) VALUES ('Aruba','info@dom.it','imaps.aruba.it','info@dom.it',%s,'attiva') RETURNING id", (cassaforte.cifra("segreta"),))[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@s.it", PW)}
    ok("predefinito: solo bozze", sql("SELECT invio_posta FROM agenti WHERE id=%s", (ag,))[0][0] == "bozze")
    ok("modo non valido rifiutato", c.put(f"/gestione/agenti/{ag}", headers=H, json={"invio_posta": "libero"}).status_code == 422)
    ok("modo impostabile e riportato nell'elenco", c.put(f"/gestione/agenti/{ag}", headers=H, json={"invio_posta": "approvazione"}).status_code == 200 and {a["id"]: a["invio_posta"] for a in c.get("/gestione/agenti", headers=H).json()}[ag] == "approvazione")
    with connessione() as conn:
        # --- bozze: nessun invio
        g = ip.gestore(conn, ag, "bozze", gm, [])
        ok("modo bozze: invio negato", g("posta_invia", {"a": "x@y.it", "oggetto": "o", "testo": "t"}).startswith("ERRORE") and not sql("SELECT 1 FROM email_in_uscita"))
        # --- approvazione
        g = ip.gestore(conn, ag, "approvazione", gm, [])
        r = g("posta_invia", {"a": "bandi@ente.it", "oggetto": "Richiesta", "testo": "Buongiorno", "rispondi_a": "m1"})
        ok("approvazione: va in coda e NON parte", "NON e' ancora partita" in r and sql("SELECT stato, canale FROM email_in_uscita") == [("da_approvare", "gmail")] and not any(u.endswith("/messages/send") for _, u, _ in CH), r)
        ok("approvazione: notifica creata", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Email da approvare%'")[0][0] == 1)
        for cattivo in ("niente", "a@b", "a@b.it, c@d", "a@b.it\nBcc: spia@x.it", ",".join(f"u{i}@x.it" for i in range(6))):
            ok("indirizzo/e non valido rifiutato: " + cattivo[:20].replace("\n", " "), g("posta_invia", {"a": cattivo, "oggetto": "o", "testo": "t"}).startswith("ERRORE"))
        ok("nulla in piu' in coda dopo i rifiuti", sql("SELECT count(*) FROM email_in_uscita")[0][0] == 1)
    eid = sql("SELECT id FROM email_in_uscita")[0][0]
    ok("collaboratore: 403", c.get("/gestione/email-uscita", headers=HA).status_code == 403 and c.post(f"/gestione/email-uscita/{eid}/decisione", headers=HA, json={"azione": "approva"}).status_code == 403)
    el = c.get("/gestione/email-uscita", headers=H).json()
    ok("elenco: la coda con agente e testo", len(el) == 1 and el[0]["agente"] == "Posta" and el[0]["testo"] == "Buongiorno")
    ok("modifica prima dell'invio, indirizzo non valido rifiutato", c.put(f"/gestione/email-uscita/{eid}", headers=H, json={"destinatari": "male"}).status_code == 422 and c.put(f"/gestione/email-uscita/{eid}", headers=H, json={"testo": "Buongiorno, rivisto"}).status_code == 200)
    d = c.post(f"/gestione/email-uscita/{eid}/decisione", headers=H, json={"azione": "approva"})
    inv = [k for m, u, k in CH if u.endswith("/messages/send")]
    import base64
    raw = base64.urlsafe_b64decode(inv[0]["json"]["raw"] + "==").decode() if inv else ""
    ok("approvata: inviata via Gmail sul thread, con il testo rivisto", d.status_code == 200 and len(inv) == 1 and inv[0]["json"]["threadId"] == "T9" and "rivisto" in raw and "bandi@ente.it" in raw and "In-Reply-To: <orig@x>" in raw, d.text + raw[:200])
    ok("stato inviata e registrata", sql("SELECT stato FROM email_in_uscita WHERE id=%s", (eid,))[0][0] == "inviata" and sql("SELECT count(*) FROM registro_azioni WHERE azione='email_inviata'")[0][0] == 1)
    ok("non parte due volte", c.post(f"/gestione/email-uscita/{eid}/decisione", headers=H, json={"azione": "approva"}).status_code == 409 and len([1 for m, u, k in CH if u.endswith("/messages/send")]) == 1)
    # --- scarto
    with connessione() as conn:
        ip.gestore(conn, ag, "approvazione", gm, [])("posta_invia", {"a": "z@z.it", "oggetto": "Scartami", "testo": "x"})
    e2 = sql("SELECT id FROM email_in_uscita WHERE oggetto='Scartami'")[0][0]
    ok("scartata: non parte", c.post(f"/gestione/email-uscita/{e2}/decisione", headers=H, json={"azione": "rifiuta"}).json()["stato"] == "rifiutata" and len([1 for m, u, k in CH if u.endswith("/messages/send")]) == 1)
    # --- diretto + IMAP/SMTP
    with connessione() as conn:
        caselle = strumenti_posta.caselle_agente(conn, ag) or conn.execute("SELECT * FROM caselle_posta").fetchall()
        g = ip.gestore(conn, ag, "diretto", None, caselle)
        r = g("posta_invia", {"a": "cliente@azienda.it, altro@azienda.it", "oggetto": "Preventivo", "testo": "In allegato no"})
        ok("diretto da casella IMAP: parte subito via SMTP (imaps -> smtps, porta 465)", "Email inviata" in r and ("connect", "smtps.aruba.it", 465) in SMTP and ("login", "info@dom.it", "segreta") in SMTP and ("send", "info@dom.it", "cliente@azienda.it, altro@azienda.it", "Preventivo") in SMTP, r + str(SMTP))
        ok("diretto: registrata come diretta e inviata", sql("SELECT stato, diretta, canale FROM email_in_uscita WHERE oggetto='Preventivo'") == [("inviata", True, "imap")])
        for i in range(ip.MAX_DIRETTE_ESECUZIONE):
            r = g("posta_invia", {"a": "x@y.it", "oggetto": f"n{i}", "testo": "t"})
        ok("diretto: tetto di invii per richiesta", "limite" in r.lower() and sql("SELECT count(*) FROM email_in_uscita WHERE stato='inviata' AND diretta")[0][0] == ip.MAX_DIRETTE_ESECUZIONE)
        # errore di invio: resta in errore e si puo' riprovare
        def rotto(*a, **k): raise strumenti_posta.ErrorePosta("Invio non riuscito (prova)")
        orig = ip._spedisci_smtp; ip._spedisci_smtp = rotto
        g2 = ip.gestore(conn, ag, "diretto", None, caselle)
        r = g2("posta_invia", {"a": "x@y.it", "oggetto": "Guasto", "testo": "t"})
        ip._spedisci_smtp = orig
        ok("invio fallito: errore all'agente e riga in errore", r.startswith("ERRORE") and sql("SELECT stato FROM email_in_uscita WHERE oggetto='Guasto'")[0][0] == "errore", r)
    e3 = sql("SELECT id FROM email_in_uscita WHERE oggetto='Guasto'")[0][0]
    ok("dall'errore si puo' riprovare", c.post(f"/gestione/email-uscita/{e3}/decisione", headers=H, json={"azione": "approva"}).status_code == 200 and sql("SELECT stato FROM email_in_uscita WHERE id=%s", (e3,))[0][0] == "inviata")
    # --- schermate
    js = c.get("/app/app.js").text
    ok("schermata: scelta dell'invio, coda email e dipartimenti richiudibili", "Invio con la mia approvazione" in js and "codaEmailUscita" in js and "gruppo-testa" in js and "Chiudi tutti" in js)
    ok("stile dei titoli dei dipartimenti", ".gruppo-nome{font-size:21px" in c.get("/app/stile.css").text)
print(f"TOTALE: {sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
