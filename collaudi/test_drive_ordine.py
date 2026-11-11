import os, sys, json, itertools
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import google, drive_ordine, strumenti_google
from app.db import connessione
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
CART = "application/vnd.google-apps.folder"
D = {"ROOT": {"name": "Opifex", "parents": [], "mimeType": CART, "trashed": False}}
conta = itertools.count(1); mosse = []
def nuovo(nome, gen, mime=CART, fid=None):
    i = fid or "N%d" % next(conta); D[i] = {"name": nome, "parents": [gen], "mimeType": mime, "trashed": False}; return i
def finto(metodo, url, **kw):
    p = kw.get("params") or {}
    if url == google._DRIVE and metodo == "GET":
        q = p["q"]; out = [dict(id=i, **f) for i, f in D.items() if not f["trashed"]]
        if "name='" in q: nome = q.split("name='")[1].split("'")[0].replace("\\'", "'"); out = [f for f in out if f["name"] == nome]
        if "' in parents" in q: gen = q.split("' in parents")[0].split("'")[-1]; out = [f for f in out if gen in f["parents"]]
        if "mimeType='" in q: out = [f for f in out if f["mimeType"] == CART]
        return {"files": [{"id": f["id"], "name": f["name"], "mimeType": f["mimeType"], "parents": f["parents"]} for f in out]}
    if url.startswith(google._DRIVE + "/") and metodo == "GET":
        i = url.rsplit("/", 1)[1]
        if i not in D: raise google.ErroreGoogle("Google ha risposto 404")
        return {"id": i, "trashed": D[i]["trashed"], "mimeType": D[i]["mimeType"], "parents": list(D[i]["parents"])}
    if url.startswith(google._DRIVE + "/") and metodo == "PATCH":
        i = url.rsplit("/", 1)[1]
        if "addParents" in p:
            D[i]["parents"] = [x for x in D[i]["parents"] if x not in p["removeParents"].split(",")] + [p["addParents"]]; mosse.append((D[i]["name"], D[p["addParents"]]["name"]))
        return {"id": i}
    if url == google._DRIVE and metodo == "POST":
        return {"id": nuovo(kw["json"]["name"], kw["json"]["parents"][0])}
    return {}
google._http = finto
google.token_accesso = lambda conn, a: "tok"; strumenti_google.token_accesso = google.token_accesso; google.radice_valida = lambda conn, t: "ROOT"
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('drive_account_id','1') ON CONFLICT (chiave) DO UPDATE SET valore='1'")
def figli(pid): return sorted(f["name"] for f in D.values() if pid in f["parents"] and not f["trashed"])
def dove(fid): return D[D[fid]["parents"][0]]["name"]

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ag = sql("SELECT id, nome FROM agenti WHERE attivo ORDER BY id LIMIT 4")
    # stato di partenza: tutto nella radice, come oggi; «Agenti» e «Progetti» vuote dentro la cartella del primo agente
    for i, (aid, nome) in enumerate(ag[:3]):
        nuovo(nome, "ROOT", fid="A%d" % i); sql("UPDATE agenti SET drive_cartella_id=%s WHERE id=%s", ("A%d" % i, aid))
    nuovo("Agenti", "A0", fid="CA"); nuovo("Progetti", "A0", fid="CP")
    pid = sql("SELECT id, nome FROM progetti WHERE eliminato_il IS NULL ORDER BY id LIMIT 1")[0]
    nuovo(pid[1], "ROOT", fid="P0"); sql("UPDATE progetti SET drive_cartella_id='P0' WHERE id=%s", (pid[0],)); nuovo("agent", "P0"); nuovo("repository", "P0")
    nuovo("PM " + pid[1], "ROOT", fid="X1")            # nome quasi uguale a un progetto, ma non e' ne' agente ne' progetto noti
    nuovo("Backup", "ROOT", fid="BK"); nuovo("vecchio.enc", "BK", "application/octet-stream")
    nuovo("Maestro di chiavi - backup siti", "ROOT", fid="MK")
    nuovo("Ricognizione.xlsx", "ROOT", "application/vnd.ms-excel", fid="F1"); nuovo("Bandi", "ROOT", fid="BA")

    p = c.get("/gestione/google/ordine", headers=H).json()
    ok("piano: agenti, progetti e sistema riconosciuti dall'identificativo, il resto «da chiarire»", sorted(x["id"] for x in p["agenti"]) == ["A0", "A1", "A2"] and [x["id"] for x in p["progetti"]] == ["P0"]
       and sorted(x["id"] for x in p["sistema"]) == ["BK", "MK"] and sorted(x["id"] for x in p["da_chiarire"]) == ["BA", "F1", "X1"], json.dumps(p)[:400])
    ok("piano: non sposta nulla e non crea nulla", not mosse and len(figli("ROOT")) == 9 and p["spostati"] == 0)
    r = c.post("/gestione/google/ordine", headers=H).json()
    ok("riordino: «Agenti» e «Progetti» gia' esistenti dentro un agente vengono portate nella radice, senza doppioni", D["CA"]["parents"] == ["ROOT"] and D["CP"]["parents"] == ["ROOT"]
       and len([f for f in D.values() if f["name"] == "Agenti"]) == 1 and len([f for f in D.values() if f["name"] == "Progetti"]) == 1, str(mosse))
    ok("riordino: ogni cartella al suo posto, con lo stesso identificativo e lo stesso nome", all(dove(x) == "Agenti" for x in ("A0", "A1", "A2")) and dove("P0") == "Progetti" and dove("BK") == "Sistema" and dove("MK") == "Sistema"
       and r["spostati"] == 6 and not r["errori"], str(r)[:300])
    ok("riordino: il contenuto delle cartelle non viene toccato", figli("P0") == ["agent", "repository"] and figli("BK") == ["vecchio.enc"])
    ok("riordino: cio' che non riconosce resta nella radice (anche un nome quasi uguale a un progetto)", figli("ROOT") == sorted(["Agenti", "Progetti", "Sistema", "Bandi", "PM " + pid[1], "Ricognizione.xlsx"]), str(figli("ROOT")))
    ok("riordino registrato", sql("SELECT dettagli->>'spostati' FROM registro_azioni WHERE azione='drive_riordinato' ORDER BY id DESC LIMIT 1")[0][0] == "6")
    n = len(mosse); r2 = c.post("/gestione/google/ordine", headers=H).json()
    ok("ripetuto: non sposta piu' nulla", r2["spostati"] == 0 and len(mosse) == n)

    # la regola per il nuovo
    with connessione() as conn:
        cid = strumenti_google.cartella_agente(conn, "tok", "ROOT", ag[3][0])
    ok("un agente senza cartella: nasce in Opifex/Agenti, non nella radice", dove(cid) == "Agenti" and ag[3][1] not in figli("ROOT"))
    with connessione() as conn:
        ok("un agente gia' ordinato: stessa cartella, nessun doppione", strumenti_google.cartella_agente(conn, "tok", "ROOT", ag[0][0]) == "A0" and figli("Agenti" and "CA").count(ag[0][1]) == 1)
        b1 = drive_ordine.cartella_ordinata(conn, "tok", "ROOT", "sistema", "Backup")
    ok("il backup notturno ritrova la sua cartella in Sistema", b1 == "BK")
    nuovo("Backup", "ROOT", fid="BK2"); D["BK"]["trashed"] = True
    with connessione() as conn:
        b2 = drive_ordine.cartella_ordinata(conn, "tok", "ROOT", "sistema", "Backup")
    ok("una cartella di sistema nata nella radice prima della regola viene portata in Sistema, non duplicata", b2 == "BK2" and dove("BK2") == "Sistema" and len([f for f in D.values() if f["name"] == "Backup" and not f["trashed"]]) == 1)
    with connessione() as conn:
        g = strumenti_google.gestore(conn, ag[1][0])
        out = g("google_crea_cartella", {"nome": "Materiali nuovi", "dentro": "ROOT"})
    nuova = [i for i, f in D.items() if f["name"] == "Materiali nuovi"]
    ok("un agente che chiede di creare una cartella nella radice: finisce nella sua cartella", len(nuova) == 1 and D[nuova[0]]["parents"] != ["ROOT"] and "Materiali nuovi" not in figli("ROOT"), out[:200] + str(D[nuova[0]]["parents"] if nuova else ""))

    # riordino automatico
    with connessione() as conn:
        ok("automatico: spento finche' non lo accendi", drive_ordine.da_fare(conn) is False)
    ok("automatico: si accende dalle impostazioni", c.put("/gestione/google/ordine", headers=H, json={"automatico": True}).status_code == 200 and c.get("/gestione/google/ordine", headers=H).json()["automatico"] is True)
    nuovo(ag[2][1] + " bis", "ROOT", fid="Z9"); sql("UPDATE agenti SET drive_cartella_id='Z9' WHERE id=%s", (ag[2][0],)); n0 = sql("SELECT count(*) FROM notifiche")[0][0]
    with connessione() as conn:
        fare = drive_ordine.da_fare(conn); drive_ordine.giro(conn); dopo = drive_ordine.da_fare(conn)
    ok("automatico: una volta al giorno rimette a posto cio' che e' finito nella radice", fare and not dopo and dove("Z9") == "Agenti")
    ok("automatico: avvisa una volta di cio' che non riconosce", sql("SELECT count(*) FROM notifiche")[0][0] == n0 + 1 and "Bandi" in sql("SELECT testo FROM notifiche ORDER BY id DESC LIMIT 1")[0][0])
    sql("DELETE FROM impostazioni_sistema WHERE chiave='drive_ordine_ultimo'")
    with connessione() as conn: drive_ordine.giro(conn)
    ok("automatico: stesso elenco, nessun nuovo avviso", sql("SELECT count(*) FROM notifiche")[0][0] == n0 + 1)
    ok("solo il titolare", c.get("/gestione/google/ordine").status_code in (401, 403) and c.post("/gestione/google/ordine").status_code in (401, 403))
print("TOTALE %d / %d" % (sum(ris), len(ris)))
