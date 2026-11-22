import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
from datetime import datetime, timedelta
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, crm, cassaforte, campagne, flusso, telegram, campagne_telegram as ct, voce_elevenlabs as ve, fornitori, invio_posta, regole_invio
from app.fornitori import Risposta
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
def K():
    return psycopg.connect(DSN, row_factory=dict_row)
scuola.giro = lambda *a, **k: None
INVIATI, AUDIO, LETTI, PROMPT = [], [], [], []
telegram.invia = lambda token, chat, testo: INVIATI.append(testo)
telegram.invia_audio = lambda token, chat, mp3, titolo="": AUDIO.append(titolo)
telegram._chiama = lambda *a, **k: {}
ve.configurazione = lambda conn: {"chiave": "x", "voce_id": "v", "garanzie": False, "telegram_voce": False}
def finta_voce(testo, fascia="interno", uid=None, **k):
    LETTI.append((testo, fascia)); return b"mp3"
ve.sintetizza = finta_voce
def finto_modello(forn, mod, istr, msg, mt=1500, **k):
    PROMPT.append((istr, msg))
    return Risposta(json.dumps({"oggetto": "x", "testo": "{saluto}\n\nperfetto, ci sentiamo giovedì alle 10 come mi ha proposto.\n\nLorenzo Zeppa"}), 300, 100)
fornitori.chiama_modello = finto_modello
SPEDITE = []
invio_posta._spedisci = lambda conn, r: SPEDITE.append((r["destinatari"], r["tipo_campagna"]))
ORA = [datetime(2026, 11, 24, 19, 5, tzinfo=regole_invio.ROMA)]
ct.adesso = lambda: ORA[0]
regole_invio.adesso = lambda: ORA[0]

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    sql("INSERT INTO canale_telegram (id, token_cifrato, chat_id) VALUES (1, %s, 777) ON CONFLICT (id) DO UPDATE SET token_cifrato=EXCLUDED.token_cifrato, chat_id=777", (cassaforte.cifra("tok"),))
    g1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    A = sql(f"INSERT INTO campagne_posta (nome, mittente, stato, oggetto, ore_dal, ore_al) VALUES ('Cantine Toscana', 'gmail:{g1}', 'in_corso', 'Un video per la vostra cantina', 8, 11) RETURNING id")[0][0]
    k1 = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash, telefono_cifrato) VALUES (%s,'cantina',%s,%s,%s,%s,%s) RETURNING id",
             (li, cassaforte.cifra("Tenuta Belvedere"), cassaforte.cifra("Paola Rossi"), cassaforte.cifra("paola@belvedere.it"), crm.hash_email("paola@belvedere.it"), cassaforte.cifra("0577 111222")))[0][0]
    oggi = datetime(2026, 11, 24, 10, 0, tzinfo=regole_invio.ROMA)
    d1 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, inviata_il, risposta_il, risposta_oggetto) VALUES (%s,%s,%s,'risposto',%s,%s,'Re: Un video') RETURNING id",
             (A, k1, crm.hash_email("paola@belvedere.it"), oggi, oggi))[0][0]
    for i in range(4):
        sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, decisa_il)
               VALUES ('gmail',%s,'m',%s,'o','t','inviata',%s,'primo',%s)""", (g1, f"x{i}@c.it", A, oggi))
    sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna) VALUES ('gmail',%s,'m','y@c.it','o','t','da_approvare',%s,'primo')""", (g1, A))

    # avviso «caldo»
    with K() as k:
        flusso.segna_interessato(k, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (d1,)).fetchone()), "vuole un preventivo per la vendemmia 2027")
    n = sql("SELECT testo, urgente FROM notifiche WHERE testo LIKE '%%interessato%%' ORDER BY id DESC LIMIT 1")[0]
    ok("avviso caldo: urgente, con ente, telefono e riferimento per rispondere da Telegram", n[1] and "🔥 Tenuta Belvedere" in n[0] and "0577 111222" in n[0] and f"[#C{d1}]" in n[0], n[0])

    # riepilogo serale
    INVIATI.clear()
    with K() as k:
        f1 = ct.giro(k); f2 = ct.giro(k)
    t = sql("SELECT testo FROM notifiche WHERE testo LIKE '📬%%' ORDER BY id")
    ok("alle 19: riepilogo serale, una volta sola", f1.get("sera") and not f2.get("sera") and len(t) == 1, (f1, f2, t))
    ok("riepilogo: partite, risposte, interessati, bozze che aspettano", "4 email partite" in t[0][0] and "1 interessato" in t[0][0] and "2 bozze" in t[0][0] and "Cantine Toscana" in t[0][0], t[0][0])

    # riepilogo vocale del mattino
    ORA[0] = datetime(2026, 11, 25, 7, 35, tzinfo=regole_invio.ROMA)
    with K() as k:
        f = ct.giro(k); f2 = ct.giro(k)
    ok("alle 7:30: testo e audio su Telegram, una volta sola", f.get("mattina") and f.get("audio") and not f2.get("mattina") and AUDIO == ["Riepilogo del mattino"], (f, f2, AUDIO))
    ok("al sintetizzatore solo numeri e campagne (pubblico), mai nomi o email dei contatti", LETTI and LETTI[0][1] == "pubblico" and "Belvedere" not in LETTI[0][0]
       and "Paola" not in LETTI[0][0] and "@" not in LETTI[0][0] and "Buongiorno Lorenzo" in LETTI[0][0], LETTI)

    # rispondere a voce (qui: testo trascritto) all'avviso
    INVIATI.clear()
    avviso = sql("SELECT testo FROM notifiche WHERE testo LIKE '🔥%%'")[0][0]
    upd = {"message": {"chat": {"id": 777, "type": "private"}, "text": "eh si allora le dico che giovedi alle dieci va benissimo, ci sentiamo",
                       "reply_to_message": {"text": avviso}}}
    with K() as k:
        telegram.gestisci_messaggio(k, "tok", upd)
    e = sql("SELECT id, stato, tipo_campagna, destinatari, testo FROM email_in_uscita WHERE tipo_campagna='risposta' AND destinatario_id=%s ORDER BY id DESC", (d1,))
    nuova = [x for x in e if "giovedì alle 10" in x[4]]
    ok("risposta dettata: email curata DA APPROVARE, al contatto giusto", nuova and nuova[0][1] == "da_approvare" and nuova[0][3] == "paola@belvedere.it" and nuova[0][4].startswith("Gentile Paola Rossi"), e)
    ok("il Redattore riceve il dettato, Telegram mostra la bozza e come mandarla", PROMPT and "giovedi alle dieci" in PROMPT[-1][1] and INVIATI and f"/ok {nuova[0][0]}" in INVIATI[-1], INVIATI)
    with K() as k:
        r = telegram._comando(k, f"/ok {nuova[0][0]}", telegram._riga(k)); k.commit()
    ok("/ok: approvata", "Approvata" in r and sql("SELECT stato FROM email_in_uscita WHERE id=%s", (nuova[0][0],))[0][0] == "approvata", r)
    with K() as k:
        ok("/ok su una prima email di campagna: non si approva da Telegram", "non trovata" in telegram._comando(k, f"/ok {sql('SELECT id FROM email_in_uscita WHERE tipo_campagna=%s AND stato=%s', ('primo', 'da_approvare'))[0][0]}", telegram._riga(k)))
    sql("UPDATE campagne_posta_dest SET inviata_il = NOW() - INTERVAL '2 hours'")
    ORA[0] = datetime(2026, 11, 25, 16, 0, tzinfo=regole_invio.ROMA)   # fuori fascia: le risposte agli interessati partono lo stesso
    with K() as k:
        campagne.invia_in_coda(k)
    ok("fuori fascia la risposta all'interessato parte lo stesso", ("paola@belvedere.it", "risposta") in SPEDITE, SPEDITE)
    with K() as k:
        r = telegram._comando(k, f"/r {d1} confermo anche il preventivo entro venerdi", telegram._riga(k))
    ok("/r NUMERO testo: stessa cosa senza vocale", "/ok" in r and "Bozza per Tenuta Belvedere" in r, r)
    with K() as k:
        ok("/campagne: il punto di oggi", "Campagne email di oggi" in telegram._comando(k, "/campagne", telegram._riga(k)) or "niente" in telegram._comando(k, "/campagne", telegram._riga(k)))
    ok("aiuto aggiornato", "/campagne" in telegram.AIUTO and "/r NUMERO" in telegram.AIUTO)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
