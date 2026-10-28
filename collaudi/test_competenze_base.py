import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import agente_browser, crm
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
from app import competenze_base as cb
from app.db import connessione
def E(n): return cb.con_blocchi(n, "manager", cb.COMPETENZE[n])
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    with connessione() as cn:
        ok("prima dell'applicazione c'e' da fare", cb.da_fare(cn) is True)
        quanti = cb.applica(cn)
    ok("applicate: marcatore di versione e agenti aggiornati", quanti >= 20 and sql("SELECT valore FROM impostazioni_sistema WHERE chiave='competenze_base_versione'")[0][0] == cb.VERSIONE, str(quanti))
    marco = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    ok("Marco ha la nuova competenza", sql("SELECT istruzioni FROM agenti WHERE id=%s", (marco,))[0][0] == E("Marco"))
    st = sql("SELECT istruzioni, motivo FROM agenti_istruzioni_storico WHERE agente_id=%s", (marco,))
    ok("il testo precedente e' nello storico", len(st) == 1 and st[0][0].startswith("Sei Marco, manager della divisione Bandi. Coordini") and "competenze di base" in st[0][1], str(st)[:200])
    # tutti gli agenti di base hanno una competenza (tranne quelli gia' scritti con cura)
    nomi = [r[0] for r in sql("SELECT nome FROM agenti")]
    mancanti = [n for n in nomi if n not in cb.COMPETENZE and n not in ("Maestro di chiavi", "Osservatore dell'uso")]
    ok("nessun agente di base senza competenza riscritta", mancanti == [], str(mancanti))
    ok("gli agenti curati a mano non vengono toccati", "Maestro di chiavi" not in cb.COMPETENZE and "Osservatore dell'uso" not in cb.COMPETENZE and "Esperto SEO" not in cb.COMPETENZE)
    ok("ogni competenza ha missione, cosa fa, come lavora, consegna e cosa non fa",
       all(all(k in t for k in ("MISSIONE:", "COSA FAI:", "COME LAVORI:", "CONSEGNI:", "NON FAI:")) for n, t in cb.COMPETENZE.items() if n != "Capo sviluppo") and "CONSEGNI:" in cb.COMPETENZE["Capo sviluppo"])
    ok("le regole comuni non sono ripetute", not any("REGOLA FERREA" in t or "NON INVENTARE MAI" in t.upper() for t in cb.COMPETENZE.values()))
    ok("nessuna competenza e' troppo lunga", max(len(t) for n, t in cb.COMPETENZE.items() if n != "Capo sviluppo") < 2500 and len(cb.COMPETENZE["Capo sviluppo"]) < 4500)
    # idempotenza e rieseguibilita' per nuova versione
    with connessione() as cn:
        ok("seconda applicazione: nulla da fare", cb.da_fare(cn) is False and cb.applica(cn) == 0)
    ok("niente duplicati nello storico", sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s", (marco,))[0][0] == 1)
    sql("UPDATE agenti SET istruzioni='Testo personalizzato da Lorenzo' WHERE id=%s", (marco,))
    sql("UPDATE impostazioni_sistema SET valore='0.0.1' WHERE chiave='competenze_base_versione'")
    with connessione() as cn:
        n = cb.applica(cn)
    ok("nuova versione: riscrive e conserva anche il testo personalizzato", n >= 1 and sql("SELECT istruzioni FROM agenti WHERE id=%s", (marco,))[0][0] == E("Marco")
       and sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s AND istruzioni='Testo personalizzato da Lorenzo'", (marco,))[0][0] == 1)
    # modifica dall'interfaccia: lo storico si aggiorna, ma non se il testo e' lo stesso
    r = c.put(f"/gestione/agenti/{marco}", headers=H, json={"istruzioni": "Una nuova versione scritta a mano"})
    ok("modifica dalle impostazioni: il testo precedente si conserva", r.status_code == 200 and sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s AND istruzioni=%s", (marco, E("Marco")))[0][0] == 1, r.text)
    n0 = sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s", (marco,))[0][0]
    c.put(f"/gestione/agenti/{marco}", headers=H, json={"istruzioni": "Una nuova versione scritta a mano"})
    ok("salvare lo stesso testo non crea versioni", sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s", (marco,))[0][0] == n0)
    v = c.get(f"/gestione/agenti/{marco}/istruzioni-storico", headers=H).json()["versioni"]
    ok("elenco versioni precedenti (dalla piu' recente)", len(v) == n0 and v[0]["istruzioni"] == E("Marco") and "creato_il" in v[0])
    ok("storico: collaboratore 403, agente inesistente 404", c.get(f"/gestione/agenti/{marco}/istruzioni-storico", headers=HA).status_code == 403 and c.get("/gestione/agenti/99999/istruzioni-storico", headers=H).status_code == 404)
    # esportazione
    r = c.get("/gestione/competenze/esporta", headers=H)
    ok("elenco competenze scaricabile", r.status_code == 200 and "markdown" in r.headers["content-type"] and "## Marco" in r.text and "Dipartimento: Bandi" in r.text and "attachment" in r.headers["content-disposition"])
    ok("esportazione: collaboratore 403", c.get("/gestione/competenze/esporta", headers=HA).status_code == 403)
    ok("interfaccia: scarica competenze e versioni precedenti", "Scarica competenze" in c.get("/app/app.js").text and "versioniPrecedenti" in c.get("/app/app.js").text)
    # aggiornamento 1.50.0: solo i testi cambiati dopo l'ultima applicazione; le modifiche a mano agli altri agenti restano
    if not sql("SELECT 1 FROM agenti WHERE nome='Capo sviluppo'"):
        sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES ('Capo sviluppo','Capo','manager','divisione','claude-sonnet-5-5','riservato','Sei il capo.')")
    aur = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]; capo = sql("SELECT id FROM agenti WHERE nome='Capo sviluppo'")[0][0]
    with connessione() as cn:
        cb.applica(cn)
    sql("UPDATE agenti SET istruzioni='Scout personalizzato da Lorenzo' WHERE id=%s", (aur,))
    sql("UPDATE agenti SET istruzioni='Vecchio testo del Capo' WHERE id=%s", (capo,))
    sql("UPDATE impostazioni_sistema SET valore='1.49.0' WHERE chiave='competenze_base_versione'")
    with connessione() as cn:
        n150 = cb.applica(cn)
    ok("1.50.0: aggiornato il team di sviluppo, non gli altri", sql("SELECT istruzioni FROM agenti WHERE id=%s", (capo,))[0][0] == E("Capo sviluppo") and sql("SELECT istruzioni FROM agenti WHERE id=%s", (aur,))[0][0].startswith("Scout personalizzato da Lorenzo") and 1 <= n150 <= 60, str(n150))
    ok("il vecchio testo del Capo e' nello storico", sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s AND istruzioni='Vecchio testo del Capo'", (capo,))[0][0] == 1)
    cs = cb.COMPETENZE["Capo sviluppo"]
    ok("Capo sviluppo: domande iniziali una sola volta, poi niente brief ne' accessi", "UNA sola volta" in cs and "al massimo cinque" in cs and "NON fai piu' domande" in cs and "non chiedi mai password" in cs and "[DA CONFERMARE]" in cs)
    ok("i ruoli di sviluppo lavorano senza chiedere accessi e brief", all("SITI WEB, LAVORO IN PARALLELO E SENZA DOMANDE" in cb.COMPETENZE[n] for n in ("Sviluppatore Front-end", "Tester", "Designer UX", "Analista Requisiti e documentazione")))
    ok("documentazione generata", cb.documentazione().startswith("# Competenze di base degli agenti") and "## Padre Casati" in cb.documentazione())
print("TOTALE", sum(ris), "/", len(ris))
