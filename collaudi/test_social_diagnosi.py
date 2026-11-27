import os, sys
from urllib.parse import urlparse, parse_qs
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
import tempfile
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app.sicurezza import cifra_password
from app import social_nativo as sn, buffer, social_diagnosi as sd
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@s.it',%s,'collaboratore')", (cifra_password(PW),))

TOKEN_UTENTE = "EAAGsegretissimo" + "x" * 80
def fake(metodo, url, con_header=False, **kw):
    p = kw.get("params") or {}
    if "graph.facebook.com" in url:
        if url.endswith("/oauth/access_token"):
            return {"access_token": TOKEN_UTENTE}
        if url.endswith("/me/accounts"):
            return {"data": [{"id": "P1", "name": "Pagina Uno", "access_token": "ptok-" + "y" * 70, "instagram_business_account": {"id": "IG1", "username": "uno"}}]}
        if url.endswith("/me/permissions") and str(p.get("access_token", "")).startswith("ptok"):
            raise sn.ErroreSocial("400: (#100) Tried accessing nonexisting field (permissions)")
        if url.endswith("/me") and str(p.get("access_token", "")).startswith("ptok"):
            return {"id": "P1", "name": "Pagina Uno"}
        if url.endswith("/me/permissions"):
            return {"data": [{"permission": "pages_show_list", "status": "granted"}, {"permission": "instagram_content_publish", "status": "declined"}]}
    if "linkedin.com" in url:
        raise sn.ErroreSocial("401: token scaduto")
    raise sn.ErroreSocial("chiamata non prevista nel collaudo: " + url)
sn._http = fake
buffer.stato_account = lambda conn: [{"etichetta": "Buffer prova", "canali": [], "errore": "chiave non valida"}]

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@s.it", PW)}
    ok("collaboratore: 403 sul resoconto", c.get("/gestione/social-nativo/diagnosi", headers=HA).status_code == 403)
    ok("senza accesso: 401", c.get("/gestione/social-nativo/diagnosi").status_code == 401)
    r = c.get("/gestione/social-nativo/diagnosi", headers=H)
    ok("a vuoto: file di testo scaricabile", r.status_code == 200 and "attachment" in r.headers.get("content-disposition", "") and ".txt" in r.headers.get("content-disposition", ""), r.text[:200])
    ok("a vuoto: segnala le app non configurate", "PROBLEMI TROVATI" in r.text and "Meta" in r.text, r.text[:400])

    c.put("/gestione/social-nativo/app/meta", headers=H, json={"client_id": "APPID", "segreto": "segreto-meta-123", "origine": "https://app.opifex.space"})
    c.put("/gestione/social-nativo/app/linkedin", headers=H, json={"client_id": "LIID", "segreto": "segreto-linkedin-456", "origine": "https://app.opifex.space"})
    rr = c.post("/gestione/social-nativo/collega/meta", headers=H, json={})
    st = parse_qs(urlparse(rr.json()["url"]).query)["state"][0]
    c.get(f"/gestione/social-nativo/callback/meta?code=C&state={st}", follow_redirects=False)
    rr = c.post("/gestione/social-nativo/collega/linkedin", headers=H, json={})
    st2 = parse_qs(urlparse(rr.json()["url"]).query)["state"][0]
    c.get(f"/gestione/social-nativo/callback/linkedin?error=user_cancelled_authorize&error_description=Utente+ha+annullato&state={st2}", follow_redirects=False)

    ev = [e[0] for e in sql("SELECT evento FROM social_eventi ORDER BY id")]
    ok("eventi registrati: app salvate, collegamenti avviati, riuscito, rifiutato", len(ev) >= 5 and any("rifiut" in e or "annull" in e or "non" in e for e in ev), str(ev))
    ok("il motivo del rifiuto viene conservato", any("annullato" in (d[0] or "") for d in sql("SELECT dettaglio FROM social_eventi")), str(sql("SELECT evento, dettaglio FROM social_eventi")))

    t = c.get("/gestione/social-nativo/diagnosi", headers=H).text
    ok("riporta l'app Meta, l'ID e l'indirizzo di ritorno", "APPID" in t and "https://app.opifex.space/gestione/social-nativo/callback/meta" in t, t[:800])
    ok("prova dal vivo: elenca i permessi non concessi", "instagram_content_publish" in t, t)
    ok("accesso di pagina: la prova dal vivo usa /me e non segnala un falso guasto", "Meta risponde (accesso della pagina «Pagina Uno»)" in t and "Tried accessing" not in t, t[:1500])
    ok("riporta l'errore Buffer", "chiave non valida" in t)
    for segreto in ("segreto-meta-123", "segreto-linkedin-456", TOKEN_UTENTE, "ptok-", "EAAG"):
        ok(f"nessun segreto nel resoconto ({segreto[:12]}…)", segreto not in t)
    ok("pulito(): toglie access_token e stringhe lunghe", "abc123" not in sd.pulito("errore ?access_token=abc123&x=1") and "z" * 70 not in sd.pulito("tok " + "z" * 70))
    mid = sql("INSERT INTO social_marchi (nome, reti) VALUES ('Prova', '{facebook,instagram}') RETURNING id")[0][0]
    cn = sql("SELECT id FROM canali_nativi WHERE rete='instagram'")[0][0]
    sql("INSERT INTO social_marchi_canali (marchio_id, rete, canale_id) VALUES (%s,'facebook','n:999'), (%s,'instagram',%s)", (mid, mid, f"n:{cn}"))
    t3 = c.get("/gestione/social-nativo/diagnosi?prova=false", headers=H).text
    ok("marchio collegato a un canale che non esiste piu': segnalato", "NON ESISTE PIU'" in t3 and "Marchio «Prova»: nessun canale funzionante collegato per facebook." in t3, t3[-1500:])
    ok("i canali mostrano il loro numero (n:ID)", f"canale n:{cn} instagram" in t3)
    t2 = c.get("/gestione/social-nativo/diagnosi?prova=false", headers=H).text
    ok("senza prova dal vivo funziona lo stesso", "PROBLEMI TROVATI" in t2)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
