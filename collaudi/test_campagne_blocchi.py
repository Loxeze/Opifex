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
from app import scuola, flusso, crm, cassaforte, imbuto, stile
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
flusso.classifica_risposte = lambda conn: 0
for n in ("richiami", "call_fissate", "call_fatte", "aggiorna_quadri"):
    setattr(imbuto, n, lambda conn: 0)
stile.studia = lambda conn: 0
def finto_prepara(conn, c, d):
    e = conn.execute("""INSERT INTO email_in_uscita (canale, account_id, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, destinatario_id, oggetto_proposto, testo_proposto)
                        VALUES ('gmail',1,'x@y.it','o','t','da_approvare',%s,'primo',%s,'o','t') RETURNING id""", (c["id"], d["id"])).fetchone()["id"]
    conn.execute("UPDATE campagne_posta_dest SET stato='da_approvare', email_id=%s WHERE id=%s", (e, d["id"])); conn.commit()
    return "da_approvare"
flusso.prepara_uno = finto_prepara

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail','drive']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    cid = sql(f"INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine', 'gmail:{gid}', 'in_corso') RETURNING id")[0][0]
    for i in range(120):
        k = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato) VALUES (%s,'cantina',%s) RETURNING id", (li, cassaforte.cifra(f"Cantina {i}")))[0][0]
        sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,%s,'in_attesa')", (cid, k, crm.hash_email(f"c{i}@x.it")))
    def giri(n):
        with K() as k:
            for _ in range(n):
                flusso.giro(k)
    def bozze():
        return sql("SELECT count(*) FROM email_in_uscita WHERE campagna_id=%s AND tipo_campagna='primo'", (cid,))[0][0]
    giri(15)
    ok("invio automatico spento: il Redattore si ferma a 50 bozze", bozze() == 50, bozze())
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    ok("la campagna mostra il blocco completo in attesa di Lorenzo", det["blocco"]["in_attesa"] and det["blocco"]["da_approvare"] == 50, det["blocco"])
    ids = [r[0] for r in sql("SELECT id FROM email_in_uscita WHERE campagna_id=%s ORDER BY id", (cid,))]
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": ids[:30]})
    giri(3)
    ok("approvate solo alcune: niente bozze nuove", bozze() == 50, bozze())
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": ids[30:45]})
    c.post(f"/gestione/campagne/{cid}/scarta", headers=H, json={"ids": ids[45:]})
    giri(15)
    ok("tutte decise (approvate o scartate): parte il blocco dopo, sempre da 50", bozze() == 100, bozze())
    sql("UPDATE campagne_posta SET invio_automatico=TRUE WHERE id=%s", (cid,))
    giri(6)
    ok("invio automatico acceso: nessun limite di blocco", bozze() == 120, bozze())
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    ok("con l'invio automatico il blocco non compare", det["blocco"] is None)

    # piu' documenti nella stessa campagna
    FOGLI = {"https://docs.google.com/spreadsheets/d/AAAAAAAAAAAAAAAAAAAAAAAAAAAAA1/edit": [("Toscana", [["Nome", "Email"], ["Cantina Uno", "uno@c.it"]])],
             "https://docs.google.com/spreadsheets/d/BBBBBBBBBBBBBBBBBBBBBBBBBBBBB2/edit": [("Elenco", [["Codice", "Cantina", "Zona", "Email", "Telefono", "Ettari"],
                                                                                               ["VIN0012", "Tenuta Due", "Montalcino", "due@c.it", "0577 123456", "12"],
                                                                                               ["VIN0013", "Fattoria Tre", "Greve", "tre@c.it", "", "8"]])]}
    flusso.scarica_fogli = lambda conn, cc: FOGLI[cc["foglio"]]
    c2 = sql(f"INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Vini', 'gmail:{gid}', 'bozza') RETURNING id")[0][0]
    u1, u2 = list(FOGLI)
    r = c.post(f"/gestione/campagne/{c2}/fogli", headers=H, json={"url": u1}).json()
    ok("primo documento: diventa quello principale e si legge subito", r["destinatari"] == 1 and sql("SELECT foglio FROM campagne_posta WHERE id=%s", (c2,)) == [(u1,)], r)
    r = c.post(f"/gestione/campagne/{c2}/fogli", headers=H, json={"url": u2}).json()
    ok("altro documento nella stessa campagna: legge entrambi", r["righe"] == 3 and r["destinatari"] == 2 and sql("SELECT count(*) FROM campagne_posta_dest WHERE campagna_id=%s", (c2,)) == [(3,)], r)
    ok("lo stesso documento due volte: no", c.post(f"/gestione/campagne/{c2}/fogli", headers=H, json={"url": u2}).status_code == 409)
    det = c.get(f"/gestione/campagne/{c2}", headers=H).json()
    ok("la campagna elenca il documento aggiunto con le sue righe", det["fogli_extra"][0]["url"] == u2 and det["fogli_extra"][0]["righe"] == 2, det["fogli_extra"])

    # le colonne: «Codice» non e' il nome; gli altri dati non si perdono
    col = [f for f in det["foglio_resoconto"] if f["foglio"] == "Elenco"][0]
    ruoli = {x["nome"]: x["ruolo"] for x in col["colonne"]}
    ok("capisce le colonne: Codice no, Cantina = nome, Zona = localita', Telefono", ruoli == {"Codice": "", "Cantina": "ente", "Zona": "comune", "Email": "email", "Telefono": "telefono", "Ettari": ""}, ruoli)
    k2 = sql("SELECT id, note_cifrate, comune FROM crm_contatti WHERE email_hash=%s", (crm.hash_email("due@c.it"),))[0]
    ok("il codice e gli ettari finiscono nelle note del contatto", "Codice: VIN0012" in cassaforte.decifra(k2[1]) and "Ettari: 12" in cassaforte.decifra(k2[1]) and k2[2] == "Montalcino")
    ok("il telefono diventa un recapito", sql("SELECT count(*) FROM crm_recapiti WHERE contatto_id=%s AND tipo='telefono'", (k2[0],)) == [(1,)])
    m, rr, t = flusso.analizza_foglio([["VIN0012", "Tenuta Due", "due@c.it"], ["VIN0013", "Fattoria Tre", "tre@c.it"]])
    ok("senza intestazione il nome e' la colonna dei nomi, non quella dei codici", m.get("ente") == 1 and rr[0]["ente"] == "Tenuta Due", m)
    m, rr, t = flusso.analizza_foglio([["Codice cantina", "Ragione sociale", "Mail"], ["A1", "Cantina Quattro", "q@c.it"]])
    ok("«Codice cantina» non e' il nome; «Ragione sociale» si'", m.get("ente") == 1, m)
    # Lorenzo corregge: il nome e' la colonna della zona (per prova)
    r = c.put(f"/gestione/campagne/{c2}/colonne", headers=H, json={"documento": u2, "foglio": "Elenco", "testa": 0, "mappa": {"ente": 2, "email": 3}})
    ok("correzione delle colonne: si rilegge e aggiorna il contatto, senza doppioni", r.status_code == 200 and cassaforte.decifra(sql("SELECT ente_cifrato FROM crm_contatti WHERE id=%s", (k2[0],))[0][0]) == "Montalcino"
       and sql("SELECT count(*) FROM crm_contatti WHERE email_hash=%s", (crm.hash_email("due@c.it"),)) == [(1,)], r.text)
    det = c.get(f"/gestione/campagne/{c2}", headers=H).json()
    ok("la correzione resta e si vede", [f for f in det["foglio_resoconto"] if f["foglio"] == "Elenco"][0]["corretta"])
    ok("due significati per la stessa colonna: no", c.put(f"/gestione/campagne/{c2}/colonne", headers=H, json={"documento": u2, "foglio": "Elenco", "testa": 0, "mappa": {"ente": 2, "email": 2}}).status_code == 422)
    fid = det["fogli_extra"][0]["id"]
    c.delete(f"/gestione/campagne/{c2}/fogli/{fid}", headers=H)
    ok("documento tolto: i contatti restano", sql("SELECT count(*) FROM campagne_fogli WHERE campagna_id=%s", (c2,)) == [(0,)] and sql("SELECT count(*) FROM campagne_posta_dest WHERE campagna_id=%s", (c2,)) == [(3,)])
    js = open("app/static/campagne.js").read()
    ok("interfaccia: altri documenti, colonne, blocchi", all(x in js for x in ("Aggiungi un altro documento", "Cosa ho capito delle colonne", "Blocco completo")))
print(f"TOTALE: {sum(ris)}/{len(ris)}")
