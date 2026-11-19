import os, sys, json
from datetime import datetime, timezone, timedelta, date
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
from app import fornitori, cassaforte, scuola, crm, campagne, flusso, redattore, invio_posta, posta_vaglio, imbuto, plaud
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
cf = cassaforte.cifra

# --- 1. le date dette a parole
o = date(2026, 11, 19)
casi = {"ci sentiamo tra 2 giorni": date(2026, 11, 21), "risentiamoci tra una settimana": date(2026, 11, 26), "fra un mese": date(2026, 12, 19),
        "ci sentiamo a marzo": date(2027, 3, 1), "ne riparliamo a giugno 2027": date(2027, 6, 1), "ci sentiamo a dicembre": date(2026, 12, 1),
        "mi richiami dopo l'estate": date(2027, 9, 1), "l'anno prossimo": date(2027, 1, 10), "a fine gennaio": date(2027, 1, 20), "grazie, non ora": None}
sbagli = {k: imbuto.data_richiamo(k, o) for k, v in casi.items() if imbuto.data_richiamo(k, o) != v}
ok("date a parole: tra 2 giorni, tra una settimana, fra un mese, a marzo, a giugno 2027, dopo l'estate, l'anno prossimo, a fine gennaio", not sbagli, sbagli)
ok("date del modello: solo future e entro 2 anni", imbuto.valida_richiamo("2027-03-01", o) == date(2027, 3, 1) and imbuto.valida_richiamo("2025-01-01", o) is None
   and imbuto.valida_richiamo("boh", o) is None and imbuto.valida_richiamo("2030-01-01", o) is None)

LOCALE = []
posta_vaglio._chiedi = lambda conn, istr, msg, max_token=1500: LOCALE.pop(0)
TESTI = {}
posta_vaglio._anteprima = lambda conn, r: TESTI.get(r["msg_id"], "")
PROMPT = []
def finto_modello(fornitore, modello, istr, msg, max_token=1500, **kw):
    PROMPT.append((modello, istr + "\n" + msg))
    if "QUADRO DI SETTORE" in istr:
        return Risposta("Gli hotel chiedono soprattutto video per i social; 2 su 2 hanno siti datati.", 1000, 200)
    return Risposta(json.dumps({"oggetto": "Ci risentiamo", "testo": "{saluto}\n\ncome d'accordo torno a scriverle per la call...\n\nLorenzo Zeppa"}), 800, 200)
fornitori.chiama_modello = finto_modello
SPEDITE = []
invio_posta._spedisci = lambda conn, riga: SPEDITE.append((riga["destinatari"], riga.get("tipo_campagna")))

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    with K() as k:
        redattore.assicura_agente(k); k.commit()
    gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Personale','l.zeppa@gmail.com',%s,ARRAY['gmail','calendar']) RETURNING id", (cf("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Hotel', 'pubblico') RETURNING id")[0][0]
    def contatto(ente, email, nome=""):
        return sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash) VALUES (%s,'hotel',%s,%s,%s,%s) RETURNING id",
                   (li, cf(ente), cf(nome) if nome else None, cf(email), crm.hash_email(email)))[0][0]
    k1, k2, k3 = contatto("Coral Bay", "dir@coral.com", "Mario Rossi"), contatto("Sunrise", "info@sunrise.com"), contatto("Palm", "info@palm.com")
    cid = sql("""INSERT INTO campagne_posta (nome, mittente, oggetto, testo, stato, categoria, link_prenotazione, brief)
                 VALUES ('Hotel Sharm', %s, 'Video', '{saluto}\nciao', 'in_corso', 'hotel', 'https://calendar.app.google/abc', '{"occasione": "A marzo siamo a Sharm"}') RETURNING id""", (f"gmail:{gid}",))[0][0]
    ds = {}
    for kid, em in ((k1, "dir@coral.com"), (k2, "info@sunrise.com"), (k3, "info@palm.com")):
        ds[kid] = sql("""INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, inviata_il, prossimo_il) VALUES (%s,%s,%s,'inviata', NOW() - INTERVAL '3 days', NOW() + INTERVAL '10 days')
                         RETURNING id""", (cid, kid, crm.hash_email(em)))[0][0]
    # risposte: «ci sentiamo a marzo» (dubbio) e «interessato» e «tra 2 giorni» detto solo nel testo
    sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, data) VALUES
           ('gmail', %s, 'r1', 'Mario Rossi <dir@coral.com>', 'Re: Video', NOW()), ('gmail', %s, 'r2', 'info@sunrise.com', 'Re: Video', NOW()),
           ('gmail', %s, 'r3', 'info@palm.com', 'Re: Video', NOW())""", (gid, gid, gid))
    TESTI.update(r1="Buongiorno, ora siamo in alta stagione, ci sentiamo a marzo.", r2="Interessante! Possiamo sentirci?", r3="Ok, ci sentiamo tra 2 giorni che torno in ufficio.")
    with K() as k:
        campagne.risposte(k)
    LOCALE[:] = [json.dumps({"esito": "dubbio", "sintesi": "In alta stagione, ci si sente a marzo", "richiamo": "2027-03-01", "quando": "a marzo"}),
                 json.dumps({"esito": "interessato", "sintesi": "Vuole sentirsi", "richiamo": None, "quando": ""}),
                 json.dumps({"testo": "{saluto}\n\ngrazie! Ecco il link: https://calendar.app.google/abc\n\nLorenzo"}),
                 json.dumps({"esito": "dubbio", "sintesi": "Torna in ufficio fra poco", "richiamo": "boh", "quando": ""})]
    with K() as k:
        flusso.classifica_risposte(k)
    d1 = sql("SELECT stato, richiamo_il, richiamo_nota, opportunita_id FROM campagne_posta_dest WHERE id=%s", (ds[k1],))[0]
    ok("«ci sentiamo a marzo»: interessato, promemoria sul destinatario", d1[0] == "interessato" and d1[1] == date(2027, 3, 1) and d1[2] == "a marzo", d1)
    ok("...e nel CRM: prossimo passo del contatto e scadenza dell'opportunita'", sql("SELECT prossimo_passo_il, prossimo_passo LIKE 'Ricontattare%%' FROM crm_contatti WHERE id=%s", (k1,)) == [(date(2027, 3, 1), True)]
       and sql("SELECT scadenza, stato FROM crm_opportunita WHERE id=%s", (d1[3],)) == [(date(2027, 3, 1), "interessato")])
    rsp = sql("SELECT testo FROM email_in_uscita WHERE destinatari='dir@coral.com' AND tipo_campagna='risposta'")
    ok("...la risposta da approvare conferma che lo ricontatterai, senza il link", rsp and "la ricontatto a marzo" in rsp[0][0] and "calendar" not in rsp[0][0], rsp)
    ok("...e la notifica dice la data", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%risentirsi a marzo (01/03/2027)%%'") == [(1,)])
    d3 = sql("SELECT stato, richiamo_il FROM campagne_posta_dest WHERE id=%s", (ds[k3],))[0]
    ok("data sbagliata dal modello ma «tra 2 giorni» nel testo: la trova lo stesso", d3 == ("interessato", date.today() + timedelta(days=2)), d3)
    ok("chi vuole la call: risposta con il link, nessun promemoria", sql("SELECT richiamo_il FROM campagne_posta_dest WHERE id=%s", (ds[k2],)) == [(None,)]
       and "calendar.app.google/abc" in sql("SELECT testo FROM email_in_uscita WHERE destinatari='info@sunrise.com' AND tipo_campagna='risposta'")[0][0])

    # --- il giorno del promemoria
    sql("UPDATE campagne_posta_dest SET richiamo_il = CURRENT_DATE WHERE id=%s", (ds[k1],))
    PROMPT.clear()
    with K() as k:
        n = imbuto.richiami(k)
    rip = sql("SELECT tipo_campagna, stato, testo FROM email_in_uscita WHERE destinatari='dir@coral.com' AND tipo_campagna='ripresa'")
    ok("arrivata la data: email per riprendere il discorso, da approvare", n == 1 and rip and rip[0][1] == "da_approvare" and rip[0][2].startswith("Gentile Mario Rossi,"), rip)
    ok("...il Redattore sa cosa aveva detto, ma non riceve email ne' nome", PROMPT and "a marzo" in PROMPT[0][1] and "dir@coral.com" not in PROMPT[0][1] and "Mario" not in PROMPT[0][1])
    ok("...notifica e una volta sola", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Oggi è il giorno per ricontattare Coral Bay%%'") == [(1,)] and imbuto.richiami(K()) == 0)
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"tutte": True})
    ok("«approva tutte» non tocca risposte e riprese", sql("SELECT count(*) FROM email_in_uscita WHERE tipo_campagna IN ('risposta','ripresa') AND stato='da_approvare'")[0][0] == 4)
    rid = sql("SELECT id FROM email_in_uscita WHERE tipo_campagna='ripresa'")[0][0]
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [rid]})
    with K() as k:
        campagne.invia_in_coda(k)
    ok("ripresa inviata: il destinatario resta interessato", ("dir@coral.com", "ripresa") in SPEDITE and sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (ds[k1],)) == [("interessato",)])

    # --- call fissata dal calendario
    quando = datetime.now(timezone.utc) + timedelta(days=2)
    imbuto._eventi = lambda conn, aid, email: [{"id": "ev1", "quando": quando, "titolo": "Call"}] if email == "info@sunrise.com" else []
    with K() as k:
        n = imbuto.call_fissate(k)
    o2 = sql("SELECT o.stato, o.call_evento FROM crm_opportunita o WHERE contatto_id=%s", (k2,))
    ok("evento con l'interessato nel calendario: «call fissata» e notifica", n == 1 and o2 == [("call_fissata", "ev1")]
       and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Call fissata con Sunrise%%'") == [(1,)], o2)
    with K() as k:
        ok("nessun doppione al giro dopo", imbuto.call_fissate(k) == 0)

    # --- call fatta dal resoconto PLAUD
    giorno = quando.astimezone(timezone(timedelta(hours=1))).date()
    r1 = sql("""INSERT INTO riunioni_importate (casella_id, uid, titolo, testo, stato, data_riunione) VALUES (NULL, 'u1', 'Call Sunrise', 'Il cliente vuole video per Instagram... il sito è vecchio', 'elaborata', %s)
                RETURNING id""", (giorno,))[0][0]
    r2 = sql("""INSERT INTO riunioni_importate (casella_id, uid, titolo, testo, stato, data_riunione) VALUES (NULL, 'u2', 'Riunione interna', 'Parliamo di ferie', 'elaborata', %s) RETURNING id""",
             (date.today() - timedelta(days=10),))[0][0]
    LOCALE[:] = [json.dumps({"idea": "Raccontare la nuova terrazza", "esigenze_dette": ["video per Instagram"], "esigenze_non_dette": ["sito datato"],
                             "upselling": ["rifacimento del sito"], "prossimo_passo": "Mandare la proposta entro venerdi'"})]
    with K() as k:
        n = imbuto.call_fatte(k)
    ok("resoconto del giorno della call: abbinato da solo, «call fatta», analisi in locale", n == 1 and sql("SELECT stato, prossima_azione FROM crm_opportunita WHERE contatto_id=%s", (k2,))
       == [("call_fatta", "Mandare la proposta entro venerdi'")] and sql("SELECT categoria, upselling FROM crm_analisi_call WHERE riunione_id=%s", (r1,)) == [("hotel", ["rifacimento del sito"])])
    ok("la riunione interna resta fuori, da abbinare a mano", [x["id"] for x in imbuto.da_abbinare(K())] == [r2])
    LOCALE[:] = [json.dumps({"idea": "Video per il ristorante", "esigenze_dette": ["video ristorante"], "esigenze_non_dette": ["poche recensioni"], "upselling": ["gestione social"], "prossimo_passo": "Preventivo"})]
    r = c.post(f"/gestione/campagne/riunioni/{r2}/abbina", headers=H, json={"contatto_id": k3})
    ok("abbinata a mano: call fatta e analisi", r.json() == {"analisi": True} and sql("SELECT stato FROM crm_opportunita WHERE contatto_id=%s", (k3,)) == [("call_fatta",)], r.text)
    with K() as k:
        imbuto.call_fissate(k)
    ok("l'opportunita' non torna mai indietro da sola", sql("SELECT stato FROM crm_opportunita WHERE contatto_id=%s", (k2,)) == [("call_fatta",)])

    # --- quadro di settore
    PROMPT.clear()
    with K() as k:
        n = imbuto.aggiorna_quadri(k)
    ok("quadro di settore «hotel» da 2 call, con un modello capace e senza nomi", n == 1 and sql("SELECT n_call FROM quadri_settore WHERE categoria='hotel'") == [(2,)]
       and "Sunrise" not in PROMPT[0][1] and "Coral" not in PROMPT[0][1] and "sito datato" in PROMPT[0][1] and "sonnet" in PROMPT[0][0], PROMPT[:1])
    with K() as k:
        ok("non si rifà due volte nello stesso giorno", imbuto.aggiorna_quadri(k) == 0)
        cc = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone())
        ok("il Redattore riceve il quadro di settore nel brief", "QUADRO DI SETTORE (hotel)" in redattore.testo_brief(cc, k) and "siti datati" in redattore.testo_brief(cc, k))

    # --- l'imbuto
    with K() as k:
        g = {x["gradino"]: x for x in imbuto.numeri(k, cid)}
    ok("imbuto della campagna: contatti, inviate, risposte, interessati, call fissate, call fatte", [g[x]["n"] for x in ("Contatti", "Email inviate", "Risposte", "Interessati", "Call fissate", "Call fatte", "Vinte")]
       == [3, 3, 3, 3, 2, 2, 0] and g["Call fatte"]["passaggio"] == 100, {k_: v["n"] for k_, v in g.items()})
    d = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    ok("la campagna porta imbuto, quadro e promemoria", d["imbuto"][0]["n"] == 3 and d["quadro"]["n_call"] == 2 and any(x["richiamo_il"] for x in d["destinatari"]))
    ok("l'elenco porta l'imbuto di tutte le campagne e i quadri", c.get("/gestione/campagne", headers=H).json()["quadri"][0]["categoria"] == "hotel")

    # --- PLAUD: senza elaboratore scelto lavora la Posta (in locale)
    vista = {}
    plaud.importa = lambda conn, casella, mittente, ora=None: 0
    plaud.elabora = lambda conn, rid, aid: vista.setdefault("agente", aid)
    cas = sql("INSERT INTO caselle_posta (etichetta, email, host, utente, password_cifrata, stato) VALUES ('Aquilia','trascrizioni@aquilia.agency','imap.x.it','t',%s,'attiva') RETURNING id", (cf("pw"),))[0][0]
    sql("INSERT INTO riunioni_importate (casella_id, uid, titolo, testo, stato) VALUES (%s, 'u9', 'Nuova', 'testo', 'nuova')", (cas,))
    with K() as k:
        plaud.salva_configurazione(k, True, cas, "plaud", None); k.commit()
        plaud.controlla(k)
    ok("canale PLAUD: senza elaboratore scelto, i resoconti li elabora la Posta", vista.get("agente") == sql("SELECT id FROM agenti WHERE nome='Posta'")[0][0], vista)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: grafico dell'imbuto, quadri, call da abbinare, promemoria, ripresa", all(x in js for x in ("graficoImbutoCp", "Quadri di settore", "Resoconti delle call da abbinare", "Da ricontattare il", "riprendere il discorso")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
