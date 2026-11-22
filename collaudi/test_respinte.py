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
from app import scuola, crm, cassaforte, campagne, respinte, posta_vaglio, invio_posta, crm_ricerca, esecuzione, guardiano
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
SPEDITE = []
ERRORE = {}
def finto_spedisci(conn, r):
    if r["destinatari"] in ERRORE:
        raise ValueError(ERRORE[r["destinatari"]])
    SPEDITE.append((r["account_id"], r["destinatari"]))
invio_posta._spedisci = finto_spedisci
respinte.dominio_ok = lambda e: not e.endswith("@nessuno.invalid")
crm_ricerca.SINCRONO = True

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    g1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    g2 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('R','info@renovatio.it',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    A = sql(f"INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine', 'gmail:{g1}', 'in_corso') RETURNING id")[0][0]
    B = sql(f"INSERT INTO campagne_posta (nome, mittente, stato, cerca_email_nuova) VALUES ('Musei', 'gmail:{g2}', 'in_corso', TRUE) RETURNING id")[0][0]

    def contatto(ente, email):
        return sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, email_cifrata, email_hash) VALUES (%s,'cantina',%s,%s,%s) RETURNING id",
                   (li, cassaforte.cifra(ente), cassaforte.cifra(email), crm.hash_email(email)))[0][0]
    def dest(cid, k, email, stato="inviata"):
        return sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, inviata_il, prossimo_il) VALUES (%s,%s,%s,%s,NOW(),NOW()+INTERVAL '5 days') RETURNING id",
                   (cid, k, crm.hash_email(email), stato))[0][0]
    def email(cid, d, a, stato="approvata", tipo="primo", acc=None):
        return sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, destinatario_id, decisa_il)
                      VALUES ('gmail',%s,'m',%s,'o','t',%s,%s,%s,%s,NOW()) RETURNING id""", (acc or g1, a, stato, cid, tipo, d))[0][0]

    # ---- avviso di mancata consegna letto dalla Posta ----
    k1 = contatto("Cantina Uno", "uno@cantinauno.it")
    d1 = dest(A, k1, "uno@cantinauno.it")
    d1b = dest(B, k1, "uno@cantinauno.it", "in_attesa")      # lo stesso indirizzo in un'altra campagna
    sol = email(A, d1, "uno@cantinauno.it", "da_approvare", "sollecito")
    k2 = contatto("Cantina Due", "due@cantinadue.it")
    d2 = dest(A, k2, "due@cantinadue.it")
    v1 = sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, categoria) VALUES ('gmail',%s,'b1','Mail Delivery Subsystem <mailer-daemon@googlemail.com>',
                'Delivery Status Notification (Failure)','scartabile') RETURNING id""", (g1,))[0][0]
    posta_vaglio._ANTEPRIME[v1] = "Address not found. Your message wasn't delivered to uno@cantinauno.it because the address couldn't be found. 550 5.1.1 The email account does not exist."
    v2 = sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, categoria) VALUES ('gmail',%s,'b2','postmaster@x.it','Undeliverable: proposta video','scartabile') RETURNING id""", (g1,))[0][0]
    posta_vaglio._ANTEPRIME[v2] = "Delivery to due@cantinadue.it delayed: mailbox full. The server will retry for 48 hours."
    with K() as k:
        n = respinte.giro(k)
    ok("avviso di mancata consegna: indirizzo respinto e bloccato", n == 1 and sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d1,))[0][0] == "respinto"
       and sql("SELECT count(*) FROM email_bloccate WHERE email_hash=%s", (crm.hash_email("uno@cantinauno.it"),))[0][0] == 1, n)
    ok("rifiuto temporaneo (casella piena, riproveremo): NON si blocca", sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d2,))[0][0] == "inviata")
    ok("il sollecito gia' pronto viene annullato", sql("SELECT stato, errore FROM email_in_uscita WHERE id=%s", (sol,))[0] == ("rifiutata", "indirizzo respinto"))
    ok("lo stesso indirizzo in un'altra campagna: fermo anche li'", sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d1b,))[0][0] == "respinto")
    ok("nella storia del contatto nel CRM", sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND oggetto LIKE 'Email respinta%%'", (k1,))[0][0] == 1)
    ok("campagna senza ricerca: niente email da cercare", sql("SELECT ricerca_email FROM campagne_posta_dest WHERE id=%s", (d1,))[0][0] == "")
    with K() as k:
        ok("non rientra in nessuna campagna nuova", crm.hash_email("uno@cantinauno.it") in campagne._esclusi(k))
        ok("il giro successivo non rilegge lo stesso avviso", respinte.giro(k) == 0)
    # un'email gia' approvata verso un indirizzo bloccato non parte
    e_b = email(A, d1, "uno@cantinauno.it")
    with K() as k:
        try:
            invio_posta.invia_riga(k, e_b, None); ok("a un indirizzo bloccato non parte nulla", False)
        except ValueError:
            ok("a un indirizzo bloccato non parte nulla", ("uno@cantinauno.it" not in [x[1] for x in SPEDITE]) and sql("SELECT stato FROM email_in_uscita WHERE id=%s", (e_b,))[0][0] == "rifiutata")

    # ---- rifiuto immediato del server ----
    k3 = contatto("Cantina Tre", "tre@cantinatre.it")
    d3 = dest(A, k3, "tre@cantinatre.it", "approvata")
    e3 = email(A, d3, "tre@cantinatre.it")
    ERRORE["tre@cantinatre.it"] = "550 5.1.1 <tre@cantinatre.it>: Recipient address rejected: User unknown"
    k4 = contatto("Cantina Quattro", "quattro@c4.it")
    d4 = dest(A, k4, "quattro@c4.it", "approvata")
    e4 = email(A, d4, "quattro@c4.it")
    ERRORE["quattro@c4.it"] = "535 5.7.8 Username and Password not accepted"
    with K() as k:
        for e_ in (e3, e4):
            try:
                invio_posta.invia_riga(k, e_, None)
            except Exception:
                pass
    ok("rifiuto definitivo all'invio (user unknown): respinto", sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d3,))[0][0] == "respinto")
    ok("errore della NOSTRA casella (password): non blocca l'indirizzo", sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d4,))[0][0] == "errore"
       and not sql("SELECT 1 FROM email_bloccate WHERE email_hash=%s", (crm.hash_email("quattro@c4.it"),)))

    # ---- ricerca di un'email nuova (campagna con l'opzione accesa) ----
    k5 = contatto("Museo Cinque", "vecchia@museo5.it")
    d5 = dest(B, k5, "vecchia@museo5.it")
    k6 = contatto("Museo Sei", "vecchia@museo6.it")
    d6 = dest(B, k6, "vecchia@museo6.it")
    with K() as k:
        respinte.segna(k, d5, "550 user unknown"); respinte.segna(k, d6, "550 user unknown"); k.commit()
    ok("opzione accesa: il respinto va cercato", sql("SELECT ricerca_email FROM campagne_posta_dest WHERE id=%s", (d5,))[0][0] == "da_cercare")
    VISTO = {}
    def finto_agente(aid, prompt, fascia, *a, **kw):
        VISTO["prompt"] = prompt
        g = crm_ricerca.gestore(lambda: K(), aid)
        VISTO["vecchia"] = g("crm_email_nuova", {"rif": d5, "email": "vecchia@museo5.it", "fonte_url": "https://museo5.it/contatti"})
        VISTO["dominio"] = g("crm_email_nuova", {"rif": d5, "email": "dir@nessuno.invalid", "fonte_url": "https://museo5.it/contatti"})
        VISTO["fuori"] = g("crm_email_nuova", {"rif": 999999, "email": "x@museo5.it", "fonte_url": "https://museo5.it/contatti"})
        VISTO["ok"] = g("crm_email_nuova", {"rif": d5, "email": "direzione@museo5.it", "fonte_url": "https://museo5.it/contatti"})
        return {"risposta": "Trovata 1 email su 2."}
    esecuzione.esegui_agente = finto_agente
    with K() as k:
        n = crm_ricerca.giro_email_nuove(k)
    ok("il Ricercatore riceve enti (dati pubblici), mai le email respinte", n == 2 and "Museo Cinque" in VISTO["prompt"] and f"[{d5}]" in VISTO["prompt"] and "vecchia@museo5.it" not in VISTO["prompt"], VISTO.get("prompt", "")[:300])
    ok("scarta l'indirizzo gia' respinto, il dominio che non riceve posta e il rif estraneo",
       VISTO["vecchia"].startswith("SCARTATO") and VISTO["dominio"].startswith("SCARTATO") and VISTO["fuori"].startswith("ERRORE"), VISTO)
    r5 = sql("SELECT stato, ricerca_email, email_hash FROM campagne_posta_dest WHERE id=%s", (d5,))[0]
    ok("email trovata: CRM aggiornato e contatto di nuovo in coda", VISTO["ok"].startswith("OK") and r5 == ("in_attesa", "trovata", crm.hash_email("direzione@museo5.it"))
       and cassaforte.decifra(sql("SELECT email_cifrata FROM crm_contatti WHERE id=%s", (k5,))[0][0]) == "direzione@museo5.it", (VISTO["ok"], r5))
    ok("con la fonte nei recapiti del CRM", sql("SELECT fonte FROM crm_recapiti WHERE contatto_id=%s AND tipo='email'", (k5,))[0][0] == "https://museo5.it/contatti")
    ok("non trovata: resta respinto, e non si cerca di nuovo", sql("SELECT stato, ricerca_email FROM campagne_posta_dest WHERE id=%s", (d6,))[0] == ("respinto", "non_trovata"))
    with K() as k:
        ok("niente altro da cercare", crm_ricerca.giro_email_nuove(k) == 0)
    det = c.get(f"/gestione/campagne/{B}", headers=H).json()
    ok("la campagna mostra respinti ed email ritrovate", det["numeri"]["respinto"] == 2 and det["respinte"]["trovate"] == 1 and det["cerca_email_nuova"] is True, (det["numeri"], det["respinte"]))
    r = c.put(f"/gestione/campagne/{A}", headers=H, json={"cerca_email_nuova": True})
    ok("l'opzione si accende dalla campagna", r.status_code == 200 and sql("SELECT cerca_email_nuova FROM campagne_posta WHERE id=%s", (A,))[0][0] is True)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: blocco Respinte con l'opzione", "Cerca un'email nuova online" in js and "cerca_email_nuova" in js)

    # ---- tetto per casella ----
    SPEDITE.clear()
    sql("UPDATE email_in_uscita SET stato='rifiutata' WHERE stato IN ('approvata','errore','da_approvare')")
    campagne.MAX_GIORNO = 2
    for i in range(2):   # la casella 1 ha gia' mandato 2 email oggi
        email(A, None, f"oggi{i}@x.it", "inviata")
    for i in range(3):
        ka = contatto(f"A{i}", f"a{i}@a.it"); email(A, dest(A, ka, f"a{i}@a.it", "approvata"), f"a{i}@a.it")
        kb = contatto(f"B{i}", f"b{i}@b.it"); email(B, dest(B, kb, f"b{i}@b.it", "approvata"), f"b{i}@b.it", acc=g2)
    sql("UPDATE campagne_posta SET per_ora=120")
    sql("UPDATE campagne_posta_dest SET inviata_il = NOW() - INTERVAL '1 hour' WHERE inviata_il IS NOT NULL")
    with K() as k:
        campagne.invia_in_coda(k)
    ok("casella piena: si ferma solo la sua campagna, l'altra casella continua", [x[0] for x in SPEDITE] == [g2], (SPEDITE, sql("SELECT id, stato, mittente FROM campagne_posta"), sql("SELECT campagna_id, stato, count(*) FROM email_in_uscita GROUP BY 1,2")))
    sql("UPDATE email_in_uscita SET decisa_il = NOW() - INTERVAL '3 hours' WHERE stato='approvata'")
    sql("UPDATE campagne_posta_dest SET inviata_il = NOW() - INTERVAL '3 hours' WHERE inviata_il IS NOT NULL")
    sql("UPDATE campagne_posta SET stato='in_pausa' WHERE id=%s", (B,))
    with K() as k:
        e = {x["chiave"]: x for x in guardiano.controlla(k)}["campagne"]
    ok("guardiano: casella piena = attenzione, con il nome della casella", e["stato"] == "attenzione" and "l.zeppa@gmail.com" in e["messaggio"], e)
    campagne.MAX_GIORNO = 300

    # ---- Posta: inviti del calendario ----
    ok("inviti, risposte e spostamenti del calendario riconosciuti", all(posta_vaglio.e_calendario(o) for o in (
        "Invito: Call @ lun 24 nov 2026 10:00 - 10:30 (CET)", "Accettato: Riunione @ mar 25 nov 2026 15:00", "Declined: Sync @ Tue Nov 25, 2026 3pm",
        "Updated invitation: Call @ Wed Nov 26, 2026 11am", "Evento annullato: Call @ 3 dic 2026 10:00")) and posta_vaglio.e_calendario("ciao", "invite.ics"))
    ok("le email normali no", not any(posta_vaglio.e_calendario(o) for o in ("Invito a cena per la mostra", "Re: proposta video", "Promemoria fattura")))
    posta_vaglio.recenti = lambda conn, o, cid, *a, **kw: [
        {"id": "c1", "da": "Anna <anna@x.it>", "oggetto": "Invito: Call @ lun 24 nov 2026 10:00 (CET)", "data": None, "anteprima": "", "allegati": "invite.ics"},
        {"id": "c2", "da": "Anna <anna@x.it>", "oggetto": "Proposta per il video", "data": None, "anteprima": "", "allegati": ""}]
    posta_vaglio.caselle = lambda conn: [{"origine": "gmail", "id": g1, "email": "l.zeppa@gmail.com"}]
    with K() as k:
        posta_vaglio.raccogli(k)
    cat = dict(sql("SELECT msg_id, categoria FROM posta_vaglio WHERE msg_id IN ('c1','c2')"))
    ok("Posta: l'invito finisce tra quelle da non vedere, la proposta no", cat == {"c1": "scartabile", "c2": "da_vagliare"}, cat)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
