import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
from datetime import date, timedelta
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, crm, cassaforte, imbuto, posta_vaglio, fornitori, dopo_call, flusso
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
LOCALE = []
def finto_locale(conn, istr, msg, max_token=1500):
    LOCALE.append((istr, msg))
    if "resoconto di una call" in istr:
        return json.dumps({"idea": "video per l'enoturismo", "esigenze_dette": ["un video"], "esigenze_non_dette": ["sito vecchio"], "upselling": ["foto"],
                           "prossimo_passo": "mandare il preventivo", "riassunto": "La cantina vuole un video per accogliere i turisti. Si e' deciso di mandare un preventivo.",
                           "passi": [{"cosa": "Mandare il preventivo", "entro_giorni": 3}, {"cosa": "Sopralluogo in cantina", "entro_giorni": 20}]})
    return json.dumps({"testo": "{saluto}\n\ngrazie! Per un video come il vostro si parte da 1.500 euro. Sentiamoci: https://cal.x/abc\n\nLorenzo"})
posta_vaglio._chiedi = finto_locale
MODELLO = []
def finto_modello(forn, mod, istr, msg, mt=1500, **k):
    MODELLO.append((istr, msg))
    if "BOZZA di un preventivo" in istr:
        return Risposta(json.dumps({"oggetto": "Video per l'enoturismo", "voci": [{"nome": "Video di presentazione cantina", "descrizione": "3 minuti", "quantita": 1, "prezzo": None},
                                                                               {"nome": "Servizio fotografico", "descrizione": "30 foto", "quantita": 1, "prezzo": None}], "note": ""}), 500, 300)
    return Risposta(json.dumps({"oggetto": "Il preventivo per il video", "testo": "{saluto}\n\nha avuto modo di guardare il preventivo? Se serve lo adattiamo.\n\nLorenzo Zeppa"}), 300, 100)
fornitori.chiama_modello = finto_modello

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    g1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    A = sql(f"INSERT INTO campagne_posta (nome, mittente, stato, oggetto, link_prenotazione) VALUES ('Cantine', 'gmail:{g1}', 'in_corso', 'Un video', 'https://cal.x/abc') RETURNING id")[0][0]
    k1 = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash) VALUES (%s,'cantina',%s,%s,%s,%s) RETURNING id",
             (li, cassaforte.cifra("Tenuta Belvedere"), cassaforte.cifra("Paola Rossi"), cassaforte.cifra("paola@belvedere.it"), crm.hash_email("paola@belvedere.it")))[0][0]
    opp = sql("INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, campagna_id) VALUES (%s,'Tenuta Belvedere · Cantine','cliente','call_fissata',%s) RETURNING id", (k1, A))[0][0]
    d1 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, opportunita_id) VALUES (%s,%s,%s,'interessato',%s) RETURNING id",
             (A, k1, crm.hash_email("paola@belvedere.it"), opp))[0][0]
    # un preventivo gia' mandato in passato: i prezzi di sempre
    k0 = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato) VALUES (%s,'cantina',%s) RETURNING id", (li, cassaforte.cifra("Vecchio cliente")))[0][0]
    for prezzo in (1500, 1500, 1800):
        sql("INSERT INTO preventivi (contatto_id, oggetto, voci, stato, inviato_il) VALUES (%s,'Video',%s,'in_fatture',NOW() - INTERVAL '90 days')",
            (k0, json.dumps([{"nome": "Video di presentazione della cantina", "descrizione": "", "quantita": 1, "prezzo": prezzo}])))
    with K() as k:
        u = dopo_call.prezzi_usuali(k)
    ok("prezzi di sempre: il valore piu' usato per quel servizio", u and u[0]["prezzo"] == 1500 and u[0]["volte"] == 3, u)

    # la call: analisi, riassunto e passi, preventivo veloce
    r1 = sql("""INSERT INTO riunioni_importate (casella_id, uid, titolo, testo, stato) VALUES (NULL, 'u1', 'Call Belvedere', 'resoconto della call...', 'elaborata') RETURNING id""")[0][0]
    with K() as k:
        imbuto.analizza(k, r1, k1)
    nota = sql("SELECT note_cifrate FROM crm_interazioni WHERE contatto_id=%s AND oggetto='Riassunto della call e passi successivi'", (k1,))
    testo = cassaforte.decifra(nota[0][0]) if nota else ""
    ok("dopo la call: riassunto e passi nella storia del contatto", "accogliere i turisti" in testo and "Sopralluogo" in testo, testo)
    ok("il primo passo diventa la data da ricontattare e la prossima azione dell'opportunita'",
       sql("SELECT prossimo_passo_il FROM crm_contatti WHERE id=%s", (k1,))[0][0] == date.today() + timedelta(days=3)
       and sql("SELECT prossima_azione, scadenza FROM crm_opportunita WHERE id=%s", (opp,))[0] == ("Mandare il preventivo", date.today() + timedelta(days=3)))
    p = sql("SELECT id, voci FROM preventivi WHERE opportunita_id=%s", (opp,))
    ok("bozza di preventivo pronta subito dopo la call", len(p) == 1, p)
    voci = {v["nome"]: v["prezzo"] for v in p[0][1]} if p else {}
    ok("con il prezzo di sempre dove il servizio e' lo stesso, vuoto dove non c'e' storia", voci.get("Video di presentazione cantina") == 1500 and voci.get("Servizio fotografico") is None, voci)
    ok("il modello vede i servizi gia' proposti (non i clienti)", any("SERVIZI GIA' PROPOSTI" in m for _, m in MODELLO) and not any("Vecchio cliente" in m for _, m in MODELLO))
    ok("notifica: bozza di preventivo pronta", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Call fatta con%%bozza di preventivo pronta%%'")[0][0] == 1)
    with K() as k:
        ok("una sola bozza per opportunita'", dopo_call.preventivo_veloce(k, opp) is None)

    # promemoria sulla proposta
    sql("UPDATE crm_interazioni SET quando = NOW() - INTERVAL '10 days' WHERE contatto_id=%s", (k1,))   # la call e' venuta prima del preventivo
    sql("UPDATE preventivi SET stato='in_fatture', inviato_il = NOW() - INTERVAL '6 days', oggetto='Video per l''enoturismo' WHERE opportunita_id=%s", (opp,))
    with K() as k:
        n = dopo_call.promemoria_proposte(k)
    e = sql("SELECT stato, tipo_campagna, destinatari, testo FROM email_in_uscita WHERE destinatario_id=%s AND tipo_campagna='ripresa'", (d1,))
    ok("proposta senza risposta da 6 giorni: email gentile da approvare al cliente", n == 1 and e and e[0][0] == "da_approvare" and e[0][2] == "paola@belvedere.it" and e[0][3].startswith("Gentile Paola"), e)
    ok("e l'avviso a Lorenzo, una volta sola", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%non si e'' ancora fatto sentire%%'")[0][0] == 1)
    with K() as k:
        ok("non si ripete", dopo_call.promemoria_proposte(k) == 0)
    # se il cliente si e' fatto sentire, niente sollecito
    k2 = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato) VALUES (%s,'cantina',%s) RETURNING id", (li, cassaforte.cifra("Fattoria")))[0][0]
    o2 = sql("INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato) VALUES (%s,'Fattoria','cliente','proposta') RETURNING id", (k2,))[0][0]
    sql("INSERT INTO preventivi (opportunita_id, contatto_id, oggetto, stato, inviato_il) VALUES (%s,%s,'Foto','in_fatture',NOW() - INTERVAL '7 days')", (o2, k2))
    sql("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, quando) VALUES (%s,'telefono','entrata','ha chiamato', NOW() - INTERVAL '1 day')", (k2,))
    with K() as k:
        ok("il cliente si e' fatto sentire dopo il preventivo: nessun sollecito", dopo_call.promemoria_proposte(k) == 0)

    # risposte pronte
    r = c.post("/gestione/campagne/risposte-pronte", headers=H, json={"domanda": "Quanto costa un video?", "risposta": "Si parte da 1.500 euro, dipende da durata e riprese."})
    ok("risposta pronta salvata", r.status_code == 200 and len(c.get("/gestione/campagne/risposte-pronte", headers=H).json()) == 1)
    with K() as k:
        ok("riconosce la domanda nella loro email", "1.500 euro" in dopo_call.per_la_bozza(k, "Buongiorno, interessante. Quanto costa un video come quello?")
           and dopo_call.per_la_bozza(k, "Grazie, sentiamoci la prossima settimana") == "")
    v = sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, categoria) VALUES ('gmail',%s,'r9','paola@belvedere.it','Re: Un video','normale') RETURNING id""", (g1,))[0][0]
    posta_vaglio._ANTEPRIME[v] = "Interessante! Ma quanto costa un video?"
    sql("UPDATE campagne_posta_dest SET risposta_vaglio_id=%s WHERE id=%s", (v, d1))
    LOCALE.clear()
    with K() as k:
        t = flusso._bozza_risposta(k, dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (A,)).fetchone()), dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (d1,)).fetchone()))
    ok("la bozza di risposta usa la risposta pronta di Lorenzo", LOCALE and "RISPOSTE PRONTE DI LORENZO" in LOCALE[-1][0] and "1.500 euro" in t, (LOCALE[-1][0][-300:] if LOCALE else None, t))
    rid = c.get("/gestione/campagne/risposte-pronte", headers=H).json()[0]["id"]
    c.delete(f"/gestione/campagne/risposte-pronte/{rid}", headers=H)
    ok("si toglie", c.get("/gestione/campagne/risposte-pronte", headers=H).json() == [])
    ok("interfaccia: risposte pronte", "Risposte pronte" in open("app/static/campagne.js").read())

print(f"TOTALE: {sum(ris)}/{len(ris)}")
