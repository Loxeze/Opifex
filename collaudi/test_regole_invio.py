import os, sys
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
from app import scuola, crm, cassaforte, campagne, respinte, regole_invio, invio_posta, flusso, fornitori
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
invio_posta._spedisci = lambda conn, r: SPEDITE.append(r["destinatari"])
respinte.dominio_ok = lambda e: not e.endswith("@nonesiste.invalid")
def nessun_modello(*a, **k):
    raise AssertionError("il modello non doveva essere chiamato")
fornitori.chiama_modello = nessun_modello
ORA = [datetime(2026, 11, 24, 9, 30, tzinfo=regole_invio.ROMA)]   # martedi' mattina
regole_invio.adesso = lambda: ORA[0]

ok("cantine: la mattina presto e mai in vendemmia", regole_invio.di_serie("Cantine storiche") == {"ore_dal": 8, "ore_al": 11, "evita_dal": "08-20", "evita_al": "10-31"})
ok("musei: in orario d'ufficio; altre categorie: 9-17", regole_invio.di_serie("musei")["ore_al"] == 13 and regole_invio.di_serie("")["ore_dal"] == 9)
c0 = {"evita_dal": "08-20", "evita_al": "10-31", "ore_dal": 8, "ore_al": 11, "solo_feriali": True}
ok("vendemmia: fermo", regole_invio.in_stagione_da_evitare(c0, datetime(2026, 9, 15, 9, tzinfo=regole_invio.ROMA)))
ok("periodo a cavallo d'anno (dic-gen)", regole_invio.in_stagione_da_evitare({"evita_dal": "12-20", "evita_al": "01-06"}, datetime(2027, 1, 3, tzinfo=regole_invio.ROMA)))
ok("fuori fascia, e il sabato", regole_invio.fuori_orario(c0, datetime(2026, 11, 24, 14, tzinfo=regole_invio.ROMA)) and regole_invio.fuori_orario(c0, datetime(2026, 11, 28, 9, tzinfo=regole_invio.ROMA)))
ok("dentro la fascia, martedi': si parte", regole_invio.perche_non_parte(c0) == "")

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    g1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine', 'pubblico') RETURNING id")[0][0]
    r = c.post("/gestione/campagne", headers=H, json={"nome": "Cantine Toscana", "mittente": f"gmail:{g1}", "categoria": "cantine", "obiettivo": "video"})
    A = r.json()["id"]
    a = sql("SELECT ore_dal, ore_al, solo_feriali, evita_dal, evita_al FROM campagne_posta WHERE id=%s", (A,))[0]
    ok("campagna nuova di cantine: fascia e vendemmia di serie", a == (8, 11, True, "08-20", "10-31"), a)
    B = sql(f"INSERT INTO campagne_posta (nome, mittente, stato, categoria) VALUES ('Vecchia', 'gmail:{g1}', 'in_corso', 'cantine') RETURNING id")[0][0]

    def contatto(ente, email):
        return sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, email_cifrata, email_hash) VALUES (%s,'cantina',%s,%s,%s) RETURNING id",
                   (li, cassaforte.cifra(ente), cassaforte.cifra(email), crm.hash_email(email)))[0][0]
    def dest(cid, k, email, stato="in_attesa", inviata=None, risposta=None):
        return sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash, stato, inviata_il, risposta_il) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                   (cid, k, crm.hash_email(email), stato, inviata, risposta))[0][0]
    adesso = datetime.now(regole_invio.ROMA)

    # controllo dell'indirizzo prima di scrivere
    k1 = contatto("Cantina Fantasma", "info@nonesiste.invalid"); d1 = dest(A, k1, "info@nonesiste.invalid")
    with K() as k:
        cc = dict(k.execute("SELECT c.*, NULL AS impresa FROM campagne_posta c WHERE id=%s", (A,)).fetchone())
        st = flusso.prepara_uno(k, cc, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (d1,)).fetchone()))
    ok("dominio che non riceve posta: respinto subito, senza chiamare il modello", st == "respinto" and sql("SELECT stato FROM campagne_posta_dest WHERE id=%s", (d1,))[0][0] == "respinto"
       and sql("SELECT count(*) FROM email_bloccate")[0][0] == 1, st)

    # non contattare due volte
    k2 = contatto("Cantina Due", "anna@cantinadue.it"); dest(B, k2, "anna@cantinadue.it", "inviata", adesso - timedelta(days=10)); d2 = dest(A, k2, "anna@cantinadue.it")
    k3 = contatto("Cantina Due (vendite)", "vendite@cantinadue.it"); d3 = dest(A, k3, "vendite@cantinadue.it")
    k4 = contatto("Mario", "mario@gmail.com"); k5 = contatto("Luigi", "luigi@gmail.com"); dest(B, k4, "mario@gmail.com", "inviata", adesso - timedelta(days=5)); d5 = dest(A, k5, "luigi@gmail.com")
    k6 = contatto("Cantina Sei", "sei@c6.it"); dest(B, k6, "sei@c6.it", "non_interessato", adesso - timedelta(days=300), adesso - timedelta(days=290)); d6 = dest(A, k6, "sei@c6.it")
    k7 = contatto("Cantina Sette", "sette@c7.it"); dest(B, k7, "sette@c7.it", "interessato", adesso - timedelta(days=30), adesso - timedelta(days=20)); d7 = dest(A, k7, "sette@c7.it")
    with K() as k:
        cc = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (A,)).fetchone())
        esiti = {x: regole_invio.prima_di_scrivere(k, cc, dict(k.execute("SELECT * FROM campagne_posta_dest WHERE id=%s", (x,)).fetchone()),
                                                   {d2: "anna@cantinadue.it", d3: "vendite@cantinadue.it", d5: "luigi@gmail.com", d6: "sei@c6.it", d7: "sette@c7.it"}[x])
                 for x in (d2, d3, d5, d6, d7)}
    ok("stessa persona gia' scritta da un'altra campagna 10 giorni fa: saltata", esiti[d2] == "scartata" and "ha gia' ricevuto" in sql("SELECT nota FROM campagne_posta_dest WHERE id=%s", (d2,))[0][0])
    ok("stessa azienda (stesso dominio di lavoro), altra persona: saltata", esiti[d3] == "scartata", esiti)
    ok("gmail e simili non sono un'azienda: non si salta", esiti[d5] is None, esiti)
    ok("chi ha risposto mesi fa (oltre 4 mesi) si puo' riscrivere; chi ha risposto da poco no", esiti[d6] is None and esiti[d7] == "scartata", esiti)

    # quando si invia
    sql("UPDATE campagne_posta SET stato='in_corso', per_ora=120 WHERE id=%s", (A,))
    sql("UPDATE campagne_posta SET stato='in_pausa' WHERE id=%s", (B,))
    for i in range(3):
        kk = contatto(f"Invio {i}", f"i{i}@inv{i}.it"); dd = dest(A, kk, f"i{i}@inv{i}.it", "approvata")
        sql("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, destinatario_id, decisa_il)
               VALUES ('gmail',%s,'m',%s,'o','t','approvata',%s,'primo',%s,NOW())""", (g1, f"i{i}@inv{i}.it", A, dd))
    ORA[0] = datetime(2026, 9, 15, 9, 30, tzinfo=regole_invio.ROMA)
    with K() as k:
        campagne.invia_in_coda(k)
    ok("in vendemmia non parte nulla", SPEDITE == [])
    ORA[0] = datetime(2026, 11, 24, 15, 0, tzinfo=regole_invio.ROMA)
    with K() as k:
        campagne.invia_in_coda(k)
    ok("fuori dalla fascia oraria non parte nulla", SPEDITE == [])
    ORA[0] = datetime(2026, 11, 24, 9, 30, tzinfo=regole_invio.ROMA)
    with K() as k:
        campagne.invia_in_coda(k)
    ok("nella fascia, giorno feriale: parte", len(SPEDITE) == 1, SPEDITE)

    # riscaldamento
    r = c.put(f"/gestione/campagne/{A}", headers=H, json={"riscalda_casella": True})
    with K() as k:
        t0 = campagne.tetto_casella(k, "gmail", g1)
        k.execute("UPDATE caselle_riscaldamento SET dal = %s", (ORA[0].date() - timedelta(days=3),)); t3 = campagne.tetto_casella(k, "gmail", g1)
        k.execute("UPDATE caselle_riscaldamento SET dal = %s", (ORA[0].date() - timedelta(days=15),)); t15 = campagne.tetto_casella(k, "gmail", g1)
        k.commit()
    ok("casella nuova: 20 il primo giorno, 65 il quarto, poi il tetto normale", r.status_code == 200 and (t0, t3, t15) == (20, 65, 300), (r.text, t0, t3, t15))
    sql("UPDATE caselle_riscaldamento SET dal = %s", (ORA[0].date(),))
    det = c.get(f"/gestione/campagne/{A}", headers=H).json()
    ok("la campagna mostra riscaldamento, invii di oggi e fascia", det["riscalda_casella"] is True and det["partite_oggi"] == 1 and det["ore_dal"] == 8 and det["non_parte"] == "", det)
    r = c.put(f"/gestione/campagne/{A}", headers=H, json={"ore_dal": None, "ore_al": None, "solo_feriali": False, "evita_dal": "", "evita_al": ""})
    ok("fascia e periodo si possono togliere", r.status_code == 200 and sql("SELECT ore_dal, solo_feriali, evita_dal FROM campagne_posta WHERE id=%s", (A,))[0] == (None, False, ""))
    ok("formato del periodo controllato", c.put(f"/gestione/campagne/{A}", headers=H, json={"evita_dal": "20 agosto"}).status_code == 422)

    # ore migliori dai dati
    with K() as k:
        ok("pochi dati: nessun suggerimento", regole_invio.ore_migliori(k, "cantine") is None)
    import random
    random.seed(1)
    for i in range(150):
        h = 8 + (i % 9)
        quando = datetime(2026, 10, 1 + i % 20, h, 15, tzinfo=regole_invio.ROMA)
        st = "risposto" if (h in (8, 9) and i % 3 == 0) or (i % 17 == 0) else "inviata"
        sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, inviata_il) VALUES (%s,%s,%s,%s)", (B, f"h{i}", st, quando))
    with K() as k:
        om = regole_invio.ore_migliori(k, "cantine")
    ok("con abbastanza risposte suggerisce la fascia migliore (la mattina presto)", om and om["ore_dal"] in (7, 8) and om["tasso"] > om["media"], om)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: fascia, feriali, periodo da evitare, riscaldamento, suggerimento", all(x in js for x in ("Fascia oraria dalle", "Solo giorni feriali", "Periodo da evitare", "riscaldala", "Usa questa fascia")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
