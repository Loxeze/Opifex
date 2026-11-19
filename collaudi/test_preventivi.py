import os, sys, json
from datetime import date
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
from app import fornitori, cassaforte, scuola, crm, preventivi, redattore
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
def finto_modello(fornitore, modello, istr, msg, max_token=1500, **kw):
    PROMPT.append((modello, msg))
    return Risposta(json.dumps({"oggetto": "Video per la terrazza panoramica", "voci": [
        {"nome": "Video promozionale", "descrizione": "Riprese 4K della terrazza e montaggio di 60 secondi", "quantita": 1, "prezzo": None},
        {"nome": "Pacchetto social", "descrizione": "5 clip verticali per Instagram (facoltativo, upselling)", "quantita": 1, "prezzo": None}],
        "note": "Riprese a marzo, durante la nostra presenza in zona"}), 900, 300)
fornitori.chiama_modello = finto_modello
CHIAMATE = []
FATTURE = []
def finto_fic(conn, metodo, percorso, **kw):
    preventivi._token(conn)
    CHIAMATE.append((metodo, percorso, kw))
    if percorso == "/user/companies":
        return {"data": {"companies": [{"id": 11, "name": "Renovatio ETS"}, {"id": 22, "name": "Logos"}]}}
    if percorso.endswith("/info/vat_types"):
        return {"data": [{"id": 0, "value": 0}, {"id": 5, "value": 22, "is_disabled": False}]}
    if metodo == "POST" and percorso.endswith("/issued_documents"):
        return {"data": {"id": 9001, "number": 17, "url": "https://secure.fattureincloud.it/doc/9001"}}
    if metodo == "GET" and percorso.endswith("/issued_documents"):
        return {"data": FATTURE}
    raise AssertionError(percorso)

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    with K() as k:
        redattore.assicura_agente(k); k.commit()
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Hotel', 'pubblico') RETURNING id")[0][0]
    kid = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash, comune) VALUES (%s,'hotel',%s,%s,%s,%s,'Sharm') RETURNING id",
              (li, cf("Sunrise Resort"), cf("Mario Rossi"), cf("info@sunrise.com"), crm.hash_email("info@sunrise.com")))[0][0]
    cid = sql("""INSERT INTO campagne_posta (nome, mittente, categoria, brief, obiettivo) VALUES ('Hotel Sharm','gmail:1','hotel','{"offerta": "Video a prezzo ridotto"}','Video agli hotel') RETURNING id""")[0][0]
    opp = sql("INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, campagna_id) VALUES (%s,'Sunrise · Hotel Sharm','cliente','call_fatta',%s) RETURNING id", (kid, cid))[0][0]
    sql("""INSERT INTO crm_analisi_call (contatto_id, opportunita_id, categoria, idea, esigenze_dette, esigenze_non_dette, upselling, prossimo_passo)
           VALUES (%s,%s,'hotel','Raccontare la terrazza panoramica','["video per Instagram"]','["sito datato"]','["rifacimento del sito"]','Mandare la proposta')""", (kid, opp))

    r = c.post("/gestione/preventivi", headers=H, json={"opportunita_id": opp})
    p = r.json()
    ok("bozza dall'analisi della call: voci e descrizioni, prezzi vuoti", r.status_code == 200 and len(p["voci"]) == 2 and all(v["prezzo"] is None for v in p["voci"]) and p["cliente"] == "Sunrise Resort", r.text)
    ok("la bozza la scrive un modello capace, senza nomi del cliente", PROMPT and "sonnet" in PROMPT[0][0] and "Sunrise" not in PROMPT[0][1] and "Mario" not in PROMPT[0][1]
       and "terrazza" in PROMPT[0][1] and "rifacimento del sito" in PROMPT[0][1])
    pid = p["id"]
    r = c.post(f"/gestione/preventivi/{pid}/crea", headers=H)
    ok("senza prezzi non si crea", r.status_code == 422 and "prezzo" in r.json()["detail"], r.text)
    voci = [dict(p["voci"][0], prezzo=1800), dict(p["voci"][1], prezzo=450, quantita=2)]
    r = c.put(f"/gestione/preventivi/{pid}", headers=H, json={"voci": voci, "note": "Riprese a marzo"})
    ok("prezzi di Lorenzo: totale calcolato", r.json()["totale_netto"] == 2700.0, r.text)
    r = c.post(f"/gestione/preventivi/{pid}/crea", headers=H)
    ok("Fatture in Cloud non collegato: lo dice", r.status_code == 422 and "non è collegato" in r.json()["detail"], r.text)

    preventivi.fic = finto_fic
    r = c.put("/gestione/preventivi/fatture-in-cloud", headers=H, json={"token": "a/eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.segreto"})
    ok("collegamento: il token vede due aziende, si sceglie", r.json()["serve_scelta"] and len(r.json()["aziende"]) == 2, r.text)
    r = c.put("/gestione/preventivi/fatture-in-cloud", headers=H, json={"token": "a/eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.segreto", "azienda_id": "11"})
    cfg = c.get("/gestione/preventivi", headers=H).json()["config"]
    ok("azienda scelta e IVA ordinaria trovata", cfg["azienda_id"] == "11" and cfg["azienda"] == "Renovatio ETS" and cfg["iva_id"] == "5", cfg)
    ok("il token resta cifrato e non torna all'interfaccia", "segreto" not in json.dumps(cfg) and "segreto" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='fic_token_cifrato'")[0][0])
    CHIAMATE.clear()
    r = c.post(f"/gestione/preventivi/{pid}/crea", headers=H)
    corpo = CHIAMATE[-1][2]["json"]["data"]
    ok("creato in Fatture in Cloud come preventivo, con cliente, voci e IVA", r.status_code == 200 and r.json()["numero"] == 17 and CHIAMATE[-1][1] == "/c/11/issued_documents"
       and corpo["type"] == "quote" and corpo["entity"]["name"] == "Sunrise Resort" and corpo["items_list"][1] == {"name": "Pacchetto social", "description": voci[1]["descrizione"], "qty": 2.0, "net_price": 450.0, "vat": {"id": 5}}, (r.text, corpo))
    ok("l'opportunita' passa a «proposta inviata» con il valore", sql("SELECT stato, valore_euro FROM crm_opportunita WHERE id=%s", (opp,)) == [("proposta", 2700)])
    ok("preventivo segnato con numero e link", sql("SELECT stato, fic_numero, fic_url FROM preventivi WHERE id=%s", (pid,)) == [("in_fatture", "17", "https://secure.fattureincloud.it/doc/9001")])
    ok("non si crea due volte", c.post(f"/gestione/preventivi/{pid}/crea", headers=H).status_code == 422)
    ok("dopo la creazione non si modifica in Opifex", c.put(f"/gestione/preventivi/{pid}", headers=H, json={"note": "x"}).status_code == 422)
    with K() as k:
        ok("nessuna fattura ancora: resta in attesa", preventivi.controlla_fatture(k) == 0 and sql("SELECT stato FROM preventivi WHERE id=%s", (pid,)) == [("in_fatture",)])
    sql("DELETE FROM impostazioni_sistema WHERE chiave='fic_controllo_il'")
    FATTURE[:] = [{"id": 9100, "type": "invoice"}]
    with K() as k:
        n = preventivi.controlla_fatture(k)
    q = [x for x in CHIAMATE if x[0] == "GET" and x[1].endswith("/issued_documents")][-1][2]["params"]
    ok("nata la fattura: affare vinto e notifica", n == 1 and sql("SELECT stato FROM crm_opportunita WHERE id=%s", (opp,)) == [("vinta",)]
       and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Affare vinto%%'") == [(1,)] and q["type"] == "invoice" and "Sunrise Resort" in q["q"], q)
    with K() as k:
        ok("il controllo si fa una volta al giorno", preventivi.controlla_fatture(k) == 0)
    # esito a mano
    opp2 = sql("INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato) VALUES (%s,'Altro affare','cliente','call_fatta') RETURNING id", (kid,))[0][0]
    p2 = c.post("/gestione/preventivi", headers=H, json={"opportunita_id": opp2}).json()["id"]
    c.post(f"/gestione/preventivi/{p2}/esito", headers=H, json={"accettato": False})
    ok("rifiutato a mano: affare perso", sql("SELECT stato FROM crm_opportunita WHERE id=%s", (opp2,)) == [("persa",)])
    def rifiuto(conn, metodo, percorso, **kw):
        raise preventivi.ErrorePreventivo("Fatture in Cloud ha rifiutato il token: rigeneralo e inseriscilo di nuovo")
    preventivi.fic = rifiuto
    p3 = c.post("/gestione/preventivi", headers=H, json={"opportunita_id": opp2}).json()
    c.put(f"/gestione/preventivi/{p3['id']}", headers=H, json={"voci": [dict(v, prezzo=100) for v in p3["voci"]]})
    r = c.post(f"/gestione/preventivi/{p3['id']}/crea", headers=H)
    ok("token scaduto: errore chiaro e il preventivo resta modificabile", r.status_code == 422 and "rigeneralo" in r.json()["detail"]
       and sql("SELECT stato FROM preventivi WHERE id=%s", (p3["id"],)) == [("errore",)], r.text)
    ok("solo il titolare", c.get("/gestione/preventivi").status_code in (401, 403))
    js = open("app/static/campagne.js").read()
    ok("interfaccia: preventivo nella scheda dell'interessato e carta Fatture in Cloud", all(x in js for x in ("Prepara il preventivo", "Crea in Fatture in Cloud", "cartaFattureInCloud", "Applicazioni collegate")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
