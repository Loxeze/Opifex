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
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Hotel', 'pubblico') RETURNING id")[0][0]
    def contatto(nome, ente, email, sito):
        kid = sql("""INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash, comune) VALUES (%s,'hotel',%s,%s,%s,%s,'Como') RETURNING id""",
                  (li, cf(ente), cf(nome) if nome else None, cf(email), crm.hash_email(email)))[0][0]
        with K() as k:
            flusso._imposta_sito(k, kid, sito); k.commit()
        return kid
    k1 = contatto("Anna Bianchi", "Hotel Luna", "anna@hotelluna.it", "https://www.hotelluna.it")
    k2 = contatto("", "Hotel Sole", "info@hotelsole.it", "https://www.hotelsole.it")
    cid = sql(f"INSERT INTO campagne_posta (nome, mittente, stato, personalizza, tetto_spesa) VALUES ('Hotel Como', 'gmail:{gid}', 'in_corso', TRUE, 50) RETURNING id")[0][0]
    d1 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,%s,'in_attesa') RETURNING id", (cid, k1, crm.hash_email("anna@hotelluna.it")))[0][0]
    with K() as k:
        c_ = dict(k.execute("SELECT c.*, NULL AS impresa FROM campagne_posta c WHERE id=%s", (cid,)).fetchone())
        flusso.prepara_uno(k, c_, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (d1,)).fetchone()))
    eid = sql("SELECT email_id FROM campagne_posta_dest WHERE id=%s", (d1,))[0][0]
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    x = [d for d in det["destinatari"] if d["id"] == d1][0]
    ok("bozza da approvare con la prima versione del Redattore", x["stato"] == "da_approvare" and x["testo"] == x["testo_proposto"] and x["testo"].startswith("Gentile Anna Bianchi,"), x)

    # Lorenzo modifica e salva, senza approvare
    nuovo = "Gentile Anna Bianchi,\n\nsono Lorenzo. A marzo saro' sul lago di Como con la mia squadra: le andrebbe una telefonata di 10 minuti?\n\nUn saluto,\nLorenzo" + campagne.PIEDE
    r = c.put(f"/gestione/email-uscita/{eid}", headers=H, json={"oggetto": "Hotel Luna e il lago, a marzo", "testo": nuovo})
    e = sql("SELECT stato, testo = testo_proposto, corretta_il IS NOT NULL, testo_proposto LIKE '%%bozza nuova%%' FROM email_in_uscita WHERE id=%s", (eid,))[0]
    ok("salvata la modifica: resta da approvare, la prima versione e' conservata", r.status_code == 200 and e == ("da_approvare", False, True, True), e)
    x = [d for d in c.get(f"/gestione/campagne/{cid}", headers=H).json()["destinatari"] if d["id"] == d1][0]
    ok("la scheda mostra le due versioni per il confronto", x["testo"] == nuovo and "bozza nuova" in x["testo_proposto"] and x["oggetto_proposto"] == "Un video per il lago")
    with K() as k:
        es = stile.corrette(k, cid)
    ok("esempio di correzione anonimo: niente nome ne' email, ente come {ente}, senza riga RIMUOVI", es and es[0]["t2"].startswith("{saluto}") and "Anna" not in json.dumps(es)
       and "anna@" not in json.dumps(es) and es[0]["o2"] == "{ente} e il lago, a marzo" and "RIMUOVI" not in es[0]["t2"], es)
    with K() as k:
        ok("finche' non parte, le regole non si aggiornano", stile.studia(k) == 0)

    # approvata: le regole si aggiornano
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [eid]})
    ok("dopo una correzione l'invio automatico resta lontano", flusso.autonomia(K(), cid)["di_fila"] == 0)
    PROMPT.clear()
    RISP[:] = [json.dumps({"regole": ["Presentati per nome nella prima riga", "Chiedi una telefonata di 10 minuti, non un incontro", "Chiudi con «Un saluto,»"]})]
    with K() as k:
        n = stile.studia(k)
    ok("approvata: un modello capace confronta le versioni e scrive le regole", n == 1 and "sonnet" in PROMPT[-1][0] and "bozza nuova" in PROMPT[-1][1] and "telefonata di 10 minuti" in PROMPT[-1][1]
       and "Anna" not in PROMPT[-1][1], PROMPT[-1][0] if PROMPT else None)
    r = c.get("/gestione/campagne/stile", headers=H).json()
    ok("«Come scrivo io»: regole e conteggio", r["correzioni"] == 1 and r["regole"].startswith("- Presentati per nome"), r)
    with K() as k:
        ok("la stessa correzione non si studia due volte", stile.studia(k) == 0)

    # la bozza dopo riceve regole ed esempio
    d2 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,%s,'in_attesa') RETURNING id", (cid, k2, crm.hash_email("info@hotelsole.it")))[0][0]
    PROMPT.clear()
    with K() as k:
        flusso.prepara_uno(k, c_, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (d2,)).fetchone()))
    p = PROMPT[-1][1]
    ok("la bozza nuova segue le regole e vede l'esempio prima/dopo", "COME SCRIVE LORENZO" in p and "Presentati per nome" in p and "VERSIONE DI LORENZO" in p
       and "telefonata di 10 minuti" in p and "bozza nuova" in p, p[-1500:])
    ok("all'esempio non arrivano il nome della persona ne' l'email", "Anna" not in p and "anna@hotelluna.it" not in p)

    # Lorenzo cambia le regole a mano
    r = c.put("/gestione/campagne/stile", headers=H, json={"regole": "1. Niente punti esclamativi\n\n• Massimo 120 parole"})
    ok("regole modificate a mano, ripulite", r.json()["regole"] == "- Niente punti esclamativi\n- Massimo 120 parole", r.text)
    ok("solo il titolare", c.get("/gestione/campagne/stile").status_code in (401, 403))
    # salvare senza cambiare nulla non conta come correzione
    eid2 = sql("SELECT email_id FROM campagne_posta_dest WHERE id=%s", (d2,))[0][0]
    t2 = sql("SELECT testo FROM email_in_uscita WHERE id=%s", (eid2,))[0][0]
    c.put(f"/gestione/email-uscita/{eid2}", headers=H, json={"testo": t2.replace("\n", "\r\n")})
    ok("salvare il testo identico non e' una correzione", sql("SELECT corretta_il FROM email_in_uscita WHERE id=%s", (eid2,)) == [(None,)])
    js = open("app/static/campagne.js").read()
    ok("interfaccia: Modifica, Salva, confronto e carta «Come scrivo io»", all(x in js for x in ('"Modifica"', '"Salva"', "Confronta con la prima versione del Redattore", "cartaStileCp", "_diffCp")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
