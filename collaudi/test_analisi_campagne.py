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
from app import scuola, crm, cassaforte, campagne, flusso, analisi_campagne as an
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

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    g1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    li = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Cantine storiche', 'pubblico') RETURNING id")[0][0]
    A = sql(f"""INSERT INTO campagne_posta (nome, mittente, stato, oggetto, testo, personalizza, spesa) VALUES ('Cantine', 'gmail:{g1}', 'in_corso', 'Un video per {{ente}}',
               '{{saluto}}\nciao', FALSE, 12.5) RETURNING id""")[0][0]
    r = c.put(f"/gestione/campagne/{A}", headers=H, json={"oggetto_b": "La vostra storia in 90 secondi"})
    ok("secondo oggetto salvato", r.status_code == 200 and sql("SELECT oggetto_b FROM campagne_posta WHERE id=%s", (A,))[0][0] == "La vostra storia in 90 secondi")
    kk = []
    for i in range(4):
        k = sql("INSERT INTO crm_contatti (lista_id, tipo, ente_cifrato, email_cifrata, email_hash) VALUES (%s,'cantina',%s,%s,%s) RETURNING id",
                (li, cassaforte.cifra(f"Tenuta {i}"), cassaforte.cifra(f"t{i}@tenuta{i}.it"), crm.hash_email(f"t{i}@tenuta{i}.it")))[0][0]
        kk.append(sql("INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s) RETURNING id", (A, k, crm.hash_email(f"t{i}@tenuta{i}.it")))[0][0])
    with K() as k:
        campagne.prepara(k, A)
    righe = sql("SELECT d.variante, e.oggetto FROM campagne_posta_dest d JOIN email_in_uscita e ON e.id=d.email_id WHERE d.campagna_id=%s ORDER BY d.id", (A,))
    ok("meta' A e meta' B, ognuna col suo oggetto", sorted(v for v, _ in righe) == ["A", "A", "B", "B"]
       and all((o.startswith("Un video per Tenuta") if v == "A" else o == "La vostra storia in 90 secondi") for v, o in righe), righe)

    # i risultati e la decisione
    CONTA = [0]
    def finti(var, n, risposte, inter=0):
        for i in range(n):
            CONTA[0] += 1
            st = "interessato" if i < inter else ("risposto" if i < risposte else "inviata")
            sql("INSERT INTO campagne_posta_dest (campagna_id, email_hash, stato, inviata_il, variante, angolo) VALUES (%s,%s,%s,NOW(),%s,%s)",
                (A, f"{var}{CONTA[0]}", st, var, "La storia della famiglia. Perche' e' antica" if var == "B" else "Il territorio"))
    finti("A", 40, 2); finti("B", 40, 6, 2)
    with K() as k:
        cc = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (A,)).fetchone())
        ok("meno di 50 a testa: ancora nessun vincitore", an.valuta_ab(k, cc) is None)
    finti("A", 12, 0); finti("B", 12, 1)
    with K() as k:
        v = an.valuta_ab(k, dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (A,)).fetchone()))
    cp = sql("SELECT oggetto, oggetto_b, ab_esito FROM campagne_posta WHERE id=%s", (A,))[0]
    ok("vince B (molte piu' risposte): diventa l'oggetto della campagna, prova chiusa", v == "B" and cp[0] == "La vostra storia in 90 secondi" and cp[1] == "" and "Vince l'oggetto B" in cp[2], (v, cp))
    ok("e Lorenzo riceve la notifica", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%prova dei due oggetti%%'")[0][0] == 1)
    det = c.get(f"/gestione/campagne/{A}", headers=H).json()
    ok("la campagna mostra i risultati della prova", {x["variante"] for x in det["ab"]} == {"A", "B"} and det["ab_esito"], det.get("ab"))

    # punteggio e da chiamare
    ok("punteggio: interessato con call fissata, sito studiato, email nominativa > risposto con info@",
       an.punteggio("interessato", "call_fissata", True, "paola@tenuta.it") > an.punteggio("risposto", None, False, "info@tenuta.it") > an.punteggio("inviata", None, False, ""))
    ok("respinti e rimossi: zero", an.punteggio("respinto", None, True, "a@b.it") == 0 and an.punteggio("rimosso", None, True, "a@b.it") == 0)
    ok("da chiamare: solo chi ha risposto o e' interessato, i piu' promettenti prima", det["da_chiamare"] and det["da_chiamare"][0]["stato"] == "interessato"
       and all(x["stato"] in ("interessato", "risposto") for x in det["da_chiamare"]) and det["da_chiamare"][0]["punteggio"] >= det["da_chiamare"][-1]["punteggio"], det["da_chiamare"][:3])

    # classifica
    d = c.get("/gestione/campagne/classifica", headers=H).json()
    x = d["campagne"][0]
    ok("classifica: partite, tasso, costo per risposta", x["nome"] == "Cantine" and x["partite"] == 104 and x["risposte"] == 9 and x["costo_risposta"] == round(12.5 / 9, 2), x)
    ok("classifica degli angoli: il migliore in cima", d["angoli"] and d["angoli"][0]["angolo"].startswith("la storia della famiglia"), d["angoli"])
    ok("solo il titolare", c.get("/gestione/campagne/classifica").status_code in (401, 403))
    js = open("app/static/campagne.js").read()
    ok("interfaccia: da chiamare, prova dei due oggetti, classifica", all(x in js for x in ("Da chiamare prima", "Prova dei due oggetti", "Classifica delle campagne")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
