import os, sys, tempfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
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
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}
    r = c.post("/uso", headers=H, json={"eventi": [
        {"vista": "ginnasio", "azione": "vista"},
        {"vista": "ginnasio", "azione": "errore", "categoria": "timeout", "durata_ms": 30010},
        {"vista": "ginnasio", "azione": "errore", "categoria": "<script>", "durata_ms": -5},
        {"vista": "ginnasio", "azione": "uscita", "durata_s": 42},
        {"vista": "task", "azione": "uscita", "durata_s": 999999},
        {"vista": "x y", "azione": "vista"}, {"vista": "task", "azione": "cancella"}]})
    ok("/uso accetta vista, errore e uscita e scarta il resto", r.status_code == 200 and r.json()["registrati"] == 5, r.text)
    righe = sql("SELECT vista, azione, categoria, durata_s, durata_ms FROM uso_eventi ORDER BY id")
    ok("categoria ammessa salvata, categoria strana scartata", righe[1][2] == "timeout" and righe[2][2] is None, str(righe))
    ok("durate limitate (uscita max 2 ore, ms mai negativi)", righe[3][3] == 42 and righe[4][3] == 7200 and righe[2][4] == 0 and righe[1][4] == 30010, str(righe))
    ok("nessun contenuto: la tabella ha solo pagina, tipo, categoria e durate", {r[0] for r in sql("SELECT column_name FROM information_schema.columns WHERE table_name='uso_eventi'")} == {"id", "utente_id", "vista", "azione", "creato_il", "categoria", "durata_s", "durata_ms"})
    from app import uso_ux
    from app.db import connessione
    for i in range(3): sql("INSERT INTO uso_eventi (utente_id, vista, azione, durata_s) SELECT id, 'ginnasio', 'uscita', %s FROM utenti LIMIT 1", (40 + i,))
    with connessione() as conn: rie = uso_ux.riepilogo(conn)
    ok("il riepilogo d'uso usa la permanenza misurata (non 0 s)", "Ginnasio" in rie and "permanenza mediana 4" in rie and "(stima)" not in rie.split("Ginnasio")[1].split("\n")[0], rie)
    # memoria vettoriale: lettura veloce e ripetuta (cache) che si azzera dopo l'indicizzazione
    r1 = c.get("/gestione/memoria-vettoriale", headers=H); r2 = c.get("/gestione/memoria-vettoriale", headers=H)
    ok("memoria vettoriale: due letture ravvicinate danno lo stesso stato", r1.status_code == 200 and r1.json() == r2.json())
    from app import memoria_vettoriale as mv
    ok("la cache si azzera con indicizza e importa", mv._CACHE_VISTA["v"] is not None and (mv._azzera_cache() or mv._CACHE_VISTA["v"] is None))
    js = {n: c.get("/app/" + n).text for n in ("app.js", "chat.js", "ginnasio.js", "riunioni.js", "controlli.js", "plancia.js", "progetti.js")}
    ok("api(): categorie rete/timeout/server/validazione e lettura con limite esplicito", all(k in js["app.js"] for k in ('"timeout"', '"rete"', '"server"', '"validazione"', "SCADENZA_LETTURA_MS")))
    ok("l'avviso rosso non conta piu' come errore, lo conta la chiamata fallita (una volta per episodio)", 'tipo === "no" && typeof registraUso' not in js["app.js"] and "segnalaErrore" in js["app.js"] and "60000" in js["app.js"])
    ok("banner unico con Riprova e contatore, aggiornamenti che rallentano e si fermano a scheda nascosta", all(k in js["app.js"] for k in ("function mostraErrore", "tentativi non riusciti", "document.hidden", "function ticker")))
    ok("le pagine usano il banner", all("mostraErrore" in js[n] for n in ("ginnasio.js", "riunioni.js", "controlli.js", "plancia.js", "progetti.js")))
    ok("permanenza misurata dal browser", "chiudiVistaUso" in js["chat.js"] and '"uscita"' in js["chat.js"])
    ok("errori salvati mostrati come stato, non come avviso rosso", "Elaborazione non riuscita:" in js["riunioni.js"] and "Ultimo problema registrato:" in js["progetti.js"])
print("TOTALE", sum(ris), "/", len(ris))
