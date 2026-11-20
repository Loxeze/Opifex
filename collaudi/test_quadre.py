import os, sys, json
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
from app import fornitori, cassaforte, scuola, crm, campagne, flusso, redattore, stile
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

PROMPT = []
RISP = []
def finto_modello(fornitore, modello, istr, msg, max_token=1500, **kw):
    PROMPT.append((modello, istr + "\n" + msg))
    return Risposta(RISP.pop(0) if RISP else json.dumps({"note": "Hotel sul lago", "comune": "", "provincia": "", "angolo": "il lago", "motivo": "x",
                                                         "oggetto": "Un video per il lago", "testo": "{saluto}\n\nbozza nuova.\n\nLorenzo Zeppa"}), 800, 200)
fornitori.chiama_modello = finto_modello
redattore._scarica = lambda url: (url, "<html><body><h1>Hotel</h1><p>" + "Albergo storico sul lago di Como, con terrazza panoramica, ristorante e giardino affacciato sull acqua. " * 4 + "</p></body></html>")

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    with K() as k:
        redattore.assicura_agente(k); k.commit()
    gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cf("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    def contatto(nome, ente, email, comune, regione):
        return sql("""INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash, comune, regione) VALUES (%s,'cantina',%s,%s,%s,%s,%s,%s) RETURNING id""",
                   (li, cf(ente), cf(nome) if nome else None, cf(email), crm.hash_email(email), comune, regione))[0][0]
    TESTO = "{saluto}\n\nscrivo a [nome della cantina] perche' a marzo saremo in [zona], nel cuore della [regione]. Mi piacerebbe raccontare il vostro [vino di punta].\n\nLorenzo"
    cid = sql(f"""INSERT INTO campagne_posta (nome, mittente, stato, personalizza, tetto_spesa, categoria, oggetto, testo, invio_automatico)
                 VALUES ('Cantine', 'gmail:{gid}', 'in_corso', FALSE, 50, 'cantina', 'Un video per [nome della cantina]', %s, TRUE) RETURNING id""", (TESTO,))[0][0]
    def dest(kid, email):
        return sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,%s,'in_attesa') RETURNING id", (cid, kid, crm.hash_email(email)))[0][0]
    def prepara(did):
        with K() as k:
            c_ = dict(k.execute("SELECT c.*, NULL AS impresa FROM campagne_posta c WHERE id=%s", (cid,)).fetchone())
            return flusso.prepara_uno(k, c_, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (did,)).fetchone()))
    def email(did):
        return sql("SELECT e.id, e.oggetto, e.testo, e.stato, d.zona FROM campagne_posta_dest d JOIN email_in_uscita e ON e.id=d.email_id WHERE d.id=%s", (did,))[0]

    def mod(o, t):
        return json.dumps({"oggetto": o, "testo": t})
    # 1. testo standard con [ ]: il Redattore lo riscrive per il contatto
    k1 = contatto("Paolo Neri", "Cantina Colle Alto", "paolo@collealto.it", "Montalcino", "Toscana")
    d1 = dest(k1, "paolo@collealto.it")
    RISP[:] = [mod("Colle Alto e le vigne di Montalcino", "{saluto}\n\nscrivo a Cantina Colle Alto perche' a marzo saremo a Montalcino, nel cuore della Toscana. Mi piacerebbe raccontare i vostri vini.\n\nLorenzo")]
    PROMPT.clear()
    st = prepara(d1)
    e = email(d1)
    ok("testo standard con [ ]: riscritto per il contatto, parentesi riempite", "[" not in e[1] + e[2] and "Montalcino" in e[2] and "riscritto per questo contatto" in e[4], e)
    p = PROMPT[-1][1]
    ok("al Redattore: testo base, ente e localita', mai nome della persona ne' email", "[nome della cantina]" in p and "Montalcino" in p and "Paolo" not in p and "paolo@" not in p
       and "SPAZI DA PERSONALIZZARE" in p and "email identiche finiscono nello spam" in p, p[:400])
    ok("riscritta e diversa: con invio automatico parte da sola", st == "approvata" and e[3] == "approvata", (st, e[3]))

    # 2. il secondo contatto: il Redattore vede la prima email e non deve ripeterla
    k2 = contatto("Giulia Verdi", "Fattoria Due Querce", "giulia@duequerce.it", "Greve in Chianti", "Toscana")
    d2 = dest(k2, "giulia@duequerce.it")
    uguale = "{saluto}\n\nscrivo a Fattoria Due Querce perche' a marzo saremo a Montalcino, nel cuore della Toscana. Mi piacerebbe raccontare i vostri vini.\n\nLorenzo"
    diversa = "{saluto}\n\nil Chianti a marzo lo attraverseremo con la telecamera: passando da Greve, mi farebbe piacere fermarmi da Fattoria Due Querce e girare qualche immagine delle vostre botti.\n\nLorenzo"
    RISP[:] = [mod("Un video per Fattoria Due Querce", uguale), mod("Greve, marzo e le vostre botti", diversa)]
    PROMPT.clear()
    st = prepara(d2)
    e = email(d2)
    ok("troppo simile alla prima: il Redattore la riscrive una seconda volta", len(PROMPT) == 2 and "troppo simile" in PROMPT[1][1] and "Greve" in e[2] and st == "approvata", (len(PROMPT), st, e[2][:120]))
    ok("vede le email gia' scritte (senza saluto, quindi senza il nome della persona)", "EMAIL GIA' SCRITTE" in PROMPT[0][1] and "Colle Alto" in PROMPT[0][1] and "Paolo" not in PROMPT[0][1])

    # 3. il Redattore non riesce a cambiarla: testo standard, avviso, non parte da sola
    k3 = contatto("", "Tenuta Sole", "info@tenutasole.it", "Alba", "Piemonte")
    d3 = dest(k3, "info@tenutasole.it")
    RISP[:] = [mod("x", uguale), mod("x", uguale)]
    st = prepara(d3)
    e = email(d3)
    ok("niente da fare: resta il testo di Lorenzo, riempito dal CRM, con l'avviso; non parte da sola", st == "da_approvare" and e[3] == "da_approvare" and "Tenuta Sole" in e[2] and "Alba" in e[2]
       and "non e' riuscito a renderla diversa" in e[4], (st, e[4]))
    ok("la parte ignota resta evidenziata come da completare", "[vino di punta]" in e[2] and "restano da completare [vino di punta]" in e[4], e[4])
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [e[0]]})
    ok("con parti tra [ ] non si approva: lo dice", r.status_code == 422 and "[ ]" in r.json()["detail"] and email(d3)[3] == "da_approvare", r.text)
    c.put(f"/gestione/email-uscita/{e[0]}", headers=H, json={"testo": "Buongiorno,\n\nad Alba a marzo: avete dieci minuti per una telefonata sul vostro Barolo?\n\nLorenzo"})
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [e[0]]})
    ok("completata a mano: si approva", r.status_code == 200 and email(d3)[3] == "approvata", r.text)

    # 4. tetto finito: niente email uguali al posto di quelle scritte, il contatto aspetta e la campagna va in pausa
    sql("UPDATE campagne_posta SET spesa = tetto_spesa WHERE id=%s", (cid,))
    k4 = contatto("", "Cascina Bassa", "info@cascinabassa.it", "Barolo", "Piemonte")
    d4 = dest(k4, "info@cascinabassa.it")
    PROMPT.clear()
    st = prepara(d4)
    ok("tetto raggiunto: nessuna email, il contatto aspetta, campagna in pausa", not PROMPT and st == "in_attesa" and sql("SELECT stato FROM campagne_posta WHERE id=%s", (cid,)) == [("in_pausa",)], st)

    # 4b. far riscrivere le bozze gia' fatte (non partite, non corrette a mano)
    sql("UPDATE campagne_posta SET spesa=0, stato='in_corso' WHERE id=%s", (cid,))
    ok("la campagna conta le bozze da far riscrivere (non quelle corrette a mano)", c.get(f"/gestione/campagne/{cid}", headers=H).json()["da_riscrivere"] == 2)
    vecchia = email(d1)[0]
    r = c.post(f"/gestione/campagne/{cid}/riscrivi", headers=H, json={"tutte": True})
    ok("riscrivi tutte: tornano al Redattore, la corretta a mano resta", r.json()["riscritte"] == 2 and sql("SELECT stato, email_id FROM campagne_posta_dest WHERE id=%s", (d1,)) == [("in_attesa", None)]
       and email(d3)[3] == "approvata" and sql("SELECT stato, errore FROM email_in_uscita WHERE id=%s", (vecchia,)) == [("rifiutata", "riscritta dal Redattore")], r.text)
    RISP[:] = [mod("Montalcino a marzo", "{saluto}\n\ndi passaggio tra le colline di Montalcino, vorrei proporre a Cantina Colle Alto un breve video sulla vendemmia passata.\n\nLorenzo")]
    prepara(d1)
    ok("il giro dopo: bozza nuova e diversa", email(d1)[0] != vecchia and "vendemmia" in email(d1)[2])
    sql("UPDATE email_in_uscita SET stato='inviata' WHERE id=%s", (email(d1)[0],))
    r = c.post(f"/gestione/campagne/{cid}/riscrivi", headers=H, json={"ids": [email(d1)[0]]})
    ok("gia' partita: non si riscrive", r.status_code == 409, r.text)

    # 5. misura della somiglianza
    ok("somiglianza: uguali a parte il saluto = 1; email diverse = poco", redattore.somiglianza("Gentile Anna,\n" + uguale[10:], "Buongiorno,\n" + uguale[10:]) == 1.0
       and redattore.somiglianza(uguale, diversa) < 0.2)
    ok("istruzione generale: parentesi quadre ed email sempre diverse", "SPAZI DA PERSONALIZZARE" in redattore.ISTRUZIONI and "ogni email e' diversa" in redattore.ISTRUZIONI and "parentesi quadre" in redattore.COMPITO_PRIMA)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: parti tra [ ] evidenziate e avviso", "_quadreCp" in js and "parti tra [ ] da completare" in js and "Fai riscrivere" in js)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
