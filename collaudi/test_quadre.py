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

    # 1. il Redattore riempie le parti tra [ ]
    k1 = contatto("Paolo Neri", "Cantina Colle Alto", "paolo@collealto.it", "Montalcino", "Toscana")
    d1 = dest(k1, "paolo@collealto.it")
    RISP[:] = [json.dumps({"oggetto": "Un video per Cantina Colle Alto", "testo": "{saluto}\n\nscrivo a Cantina Colle Alto perche' a marzo saremo a Montalcino, nel cuore della Toscana. Mi piacerebbe raccontare i vostri vini.\n\nLorenzo"})]
    PROMPT.clear()
    st = prepara(d1)
    e = email(d1)
    ok("testo standard con [ ]: il Redattore le riempie con i dati del contatto", "[" not in e[1] + e[2] and "Montalcino" in e[2] and "Colle Alto" in e[1] and "controllale" in e[4], e)
    p = PROMPT[-1][1]
    ok("al Redattore: testo base, ente e localita', mai nome della persona ne' email", "[nome della cantina]" in p and "Montalcino" in p and "Paolo" not in p and "paolo@" not in p
       and "SPAZI DA PERSONALIZZARE" in p, p[:400])
    ok("riempite: con invio automatico parte da sola", st == "approvata" and e[3] == "approvata", (st, e[3]))

    # 2. il modello sbaglia (lascia le quadre): riempimento dal CRM, l'ignoto resta e blocca
    k2 = contatto("", "Fattoria Due Querce", "info@duequerce.it", "Greve in Chianti", "Toscana")
    d2 = dest(k2, "info@duequerce.it")
    RISP[:] = [json.dumps({"oggetto": "Un video per [nome della cantina]", "testo": "uguale [zona]"})]
    st = prepara(d2)
    e = email(d2)
    ok("riempite dal CRM le ovvie: nome, zona, regione", "Fattoria Due Querce" in e[1] and "saremo in Greve in Chianti" in e[2] and "della Toscana" in e[2], e)
    ok("la parte ignota resta, segnalata, e non parte da sola", "[vino di punta]" in e[2] and "Attenzione: restano da completare [vino di punta]" in e[4] and st == "da_approvare" and e[3] == "da_approvare", (st, e[4]))
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [e[0]]})
    ok("con parti tra [ ] non si approva: lo dice", r.status_code == 422 and "[ ]" in r.json()["detail"] and email(d2)[3] == "da_approvare", r.text)
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"tutte": True})
    ok("«approva tutte» salta quella e lo conta", r.status_code == 422 or r.json().get("da_completare") == 1, r.text)
    c.put(f"/gestione/email-uscita/{e[0]}", headers=H, json={"testo": e[2].replace("[vino di punta]", "Chianti Classico")})
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [e[0]]})
    ok("completata a mano: si approva", r.status_code == 200 and email(d2)[3] == "approvata", r.text)

    # 3. tetto finito: niente modello, solo il CRM
    sql("UPDATE campagne_posta SET spesa = tetto_spesa WHERE id=%s", (cid,))
    k3 = contatto("", "Tenuta Sole", "info@tenutasole.it", "Alba", "Piemonte")
    d3 = dest(k3, "info@tenutasole.it")
    PROMPT.clear()
    prepara(d3)
    e = email(d3)
    ok("tetto raggiunto: nessuna chiamata, riempite dal CRM", not PROMPT and "Tenuta Sole" in e[2] and "Alba" in e[2] and "[vino di punta]" in e[2], e)
    # 4. istruzione anche per le email personalizzate
    ok("istruzione generale del Redattore sulle parentesi quadre", "SPAZI DA PERSONALIZZARE" in redattore.ISTRUZIONI and "parentesi quadre" in redattore.COMPITO_PRIMA)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: parti tra [ ] evidenziate e avviso", "_quadreCp" in js and "parti tra [ ] da completare" in js)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
