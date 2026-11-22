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
from app import scuola, crm, cassaforte, crm_doppioni, crm_ricerca, esecuzione, flusso, fornitori, respinte
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
crm_ricerca.SINCRONO = True
respinte.dominio_ok = lambda e: True
def nessun_modello(*a, **k):
    raise AssertionError("modello non previsto")
fornitori.chiama_modello = nessun_modello
c_ = cassaforte.cifra

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    def contatto(ente, email="", tel="", comune="", nome=""):
        return sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, nome_cifrato, email_cifrata, email_hash, telefono_cifrato, comune) VALUES (%s,'cantina',%s,%s,%s,%s,%s,%s) RETURNING id",
                   (li, c_(ente), c_(nome) if nome else None, c_(email) if email else None, crm.hash_email(email) if email else None, c_(tel) if tel else None, comune or None))[0][0]

    # ---- doppioni ----
    a1 = contatto("Az. Agr. Tenuta Belvedere S.r.l.", "info@belvedere.it", "", "Montalcino")
    a2 = contatto("Tenuta Belvedere", "", "+39 0577 123456", "Montalcino")
    b1 = contatto("Fattoria Rossi", "", "0577 999 888")
    b2 = contatto("Rossi Vini", "", "0577999888")
    e1 = contatto("Castello di Brolio", "vendite@ricasoli.it")
    e2 = contatto("Castello Brolio Ricasoli", "accoglienza@ricasoli.it")
    x1 = contatto("Tenuta Belvedere", "", "", "Alba")   # stesso nome ma altro comune: non e' un doppione
    sql("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto) VALUES (%s,'telefono','uscita','chiamata')", (a2,))
    sql("INSERT INTO crm_recapiti (contatto_id, tipo, valore_cifrato, valore_hash) VALUES (%s,'sito',%s,'h1')", (a2, c_("https://www.belvedere.it")))
    with K() as k:
        g = crm_doppioni.trova(k)
    gruppi = [sorted(x["id"] for x in gg["contatti"]) for gg in g]
    ok("trova: stesso nome (senza «Az. Agr.», «S.r.l.») nello stesso comune", sorted([a1, a2]) in gruppi, g)
    ok("trova: stesso telefono scritto in modi diversi", sorted([b1, b2]) in gruppi, gruppi)
    ok("trova: stesso dominio di lavoro e nome simile", sorted([e1, e2]) in gruppi, gruppi)
    ok("stesso nome in un altro comune: non e' un doppione", not any(x1 in gg for gg in gruppi), gruppi)
    ok("con il motivo", all(gg["motivo"] for gg in g))
    A = sql("INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Campagna C', 'gmail:1', 'in_corso') RETURNING id")[0][0]
    sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,'hh','inviata')", (A, a2))
    sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato) VALUES (%s,%s,'hh2','inviata')", (A, a1))
    r = c.post("/gestione/crm/doppioni/unisci", headers=H, json={"tieni": a1, "altri": [a2]})
    ok("unione confermata", r.status_code == 200 and r.json()["uniti"] == 1, r.text)
    ok("l'altro sparisce, la sua storia e i recapiti passano a quello tenuto", not sql("SELECT 1 FROM crm_contatti WHERE id=%s", (a2,))
       and sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND oggetto='chiamata'", (a1,))[0][0] == 1
       and sql("SELECT count(*) FROM crm_recapiti WHERE contatto_id=%s AND tipo='sito'", (a1,))[0][0] == 1)
    ok("i campi vuoti si completano (il telefono dell'altro)", cassaforte.decifra(sql("SELECT telefono_cifrato FROM crm_contatti WHERE id=%s", (a1,))[0][0]) == "+39 0577 123456")
    ok("le campagne restano coerenti", sql("SELECT count(*) FROM campagne_posta_dest WHERE campagna_id=%s AND contatto_id=%s", (A, a1))[0][0] == 2)
    ok("unire un contatto con se stesso: rifiutato", c.post("/gestione/crm/doppioni/unisci", headers=H, json={"tieni": b1, "altri": [b1]}).status_code == 422)
    ok("solo il titolare", c.get("/gestione/crm/doppioni").status_code in (401, 403))
    ok("interfaccia CRM: scheda Doppioni", "crmDoppioni" in open("app/static/crm.js").read())

    # ---- responsabile dell'azienda ----
    B = sql("INSERT INTO campagne_posta (nome, mittente, stato, cerca_responsabile, testo, oggetto) VALUES ('Cantine top', 'gmail:1', 'in_corso', TRUE, 't', 'o') RETURNING id")[0][0]
    r1 = contatto("Cantina Alta", "info@cantinalta.it"); dr1 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s) RETURNING id", (B, r1, crm.hash_email("info@cantinalta.it")))[0][0]
    r2 = contatto("Cantina Bassa", "info@cantinabassa.it"); dr2 = sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s) RETURNING id", (B, r2, crm.hash_email("info@cantinabassa.it")))[0][0]
    with K() as k:
        cc = dict(k.execute("SELECT c.*, NULL AS impresa FROM campagne_posta c WHERE id=%s", (B,)).fetchone())
        st = [flusso.prepara_uno(k, cc, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (x,)).fetchone())) for x in (dr1, dr2)]
    ok("email generica e niente nome: prima si cerca il responsabile (nessun modello, nessuna bozza)", st == ["in_attesa", "in_attesa"]
       and sql("SELECT ricerca_resp, nota FROM campagne_posta_dest WHERE id=%s", (dr1,))[0] == ("da_cercare", "cerco il responsabile"))
    VISTO = {}
    def finto_agente(aid, prompt, fascia, *a, **kw):
        VISTO["prompt"] = prompt
        g = crm_ricerca.gestore(lambda: K(), aid)
        VISTO["senza_cognome"] = g("crm_responsabile", {"rif": dr1, "nome": "Marco", "ruolo": "titolare", "fonte_url": "https://cantinalta.it/chi-siamo"})
        VISTO["ok"] = g("crm_responsabile", {"rif": dr1, "nome": "Marco Bianchi", "ruolo": "titolare", "email": "marco.bianchi@cantinalta.it", "fonte_url": "https://cantinalta.it/chi-siamo"})
        return {"risposta": "1 su 2"}
    esecuzione.esegui_agente = finto_agente
    with K() as k:
        n = crm_ricerca.giro_responsabili(k)
    ok("il Ricercatore riceve le aziende (dati pubblici), non gli indirizzi", n == 2 and "Cantina Alta" in VISTO["prompt"] and "info@cantinalta.it" not in VISTO["prompt"], VISTO.get("prompt", "")[:200])
    ok("serve nome e cognome", VISTO["senza_cognome"].startswith("ERRORE"))
    k1 = sql("SELECT nome_cifrato, email_cifrata, genere FROM crm_contatti WHERE id=%s", (r1,))[0]
    ok("trovato: nome nel CRM (l'email comincera' con «Gentile Marco Bianchi») ed email nominativa", VISTO["ok"].startswith("OK") and cassaforte.decifra(k1[0]) == "Marco Bianchi"
       and cassaforte.decifra(k1[1]) == "marco.bianchi@cantinalta.it" and k1[2] == "persona", (VISTO["ok"], k1))
    ok("l'indirizzo generico resta tra i recapiti", sql("SELECT count(*) FROM crm_recapiti WHERE contatto_id=%s AND fonte='indirizzo generico'", (r1,))[0][0] == 1)
    ok("trovato e non trovato: entrambi tornano a essere scritti", sql("SELECT ricerca_resp, nota, email_hash FROM campagne_posta_dest WHERE id=%s", (dr1,))[0] == ("trovato", "", crm.hash_email("marco.bianchi@cantinalta.it"))
       and sql("SELECT ricerca_resp, nota FROM campagne_posta_dest WHERE id=%s", (dr2,))[0] == ("non_trovato", ""))

    # ---- contatti simili a chi ha risposto ----
    S = sql("INSERT INTO campagne_posta (nome, mittente, stato, cerca_simili, categoria) VALUES ('Agriturismi', 'gmail:1', 'in_corso', TRUE, 'agriturismi') RETURNING id")[0][0]
    for i in range(3):
        kk = contatto(f"Agriturismo Buono {i}", f"a{i}@agri{i}.it", "", "Pienza")
        sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, risposta_il) VALUES (%s,%s,%s,'interessato',NOW())", (S, kk, crm.hash_email(f"a{i}@agri{i}.it")))
    def agente_simili(aid, prompt, fascia, *a, **kw):
        VISTO["simili"] = prompt
        g = crm_ricerca.gestore(lambda: K(), aid)
        VISTO["proposta"] = g("crm_proponi_contatto", {"ente": "Agriturismo Nuovo", "email": "direzione@agrinuovo.it", "fonte_url": "https://agrinuovo.it/contatti",
                                                       "motivo": "Agriturismo a Pienza come quelli che hanno risposto, con email di direzione"})
        return {"risposta": "1 proposta"}
    esecuzione.esegui_agente = agente_simili
    with K() as k:
        n = crm_ricerca.giro_simili(k)
        n2 = crm_ricerca.giro_simili(k)
    ok("una volta a settimana: ricerca di enti simili a chi ha risposto", n == 1 and n2 == 0 and "Agriturismo Buono 0" in VISTO["simili"] and "Pienza" in VISTO["simili"], (n, n2))
    pid = sql("SELECT id FROM crm_proposte WHERE stato='proposta' ORDER BY id DESC LIMIT 1")[0][0]
    r = c.post("/gestione/crm-ricerca/decidi", headers=H, json={"ids": [pid], "azione": "approva"})
    nuovo = sql("SELECT id FROM crm_contatti WHERE email_hash=%s", (crm.hash_email("direzione@agrinuovo.it"),))
    ok("approvato da Lorenzo: entra nel CRM e nella campagna", r.status_code == 200 and nuovo and sql("SELECT count(*) FROM campagne_posta_dest WHERE campagna_id=%s AND contatto_id=%s", (S, nuovo[0][0]))[0][0] == 1, r.text)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: opzioni responsabile e contatti simili", "cerca il responsabile" in js and "contatti simili" in js)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
