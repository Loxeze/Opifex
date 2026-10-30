import os, sys, time
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import sfondo_arte as sa
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
JPG = b"\xff\xd8\xff\xe0" + b"0" * 2000
chiamate = {"api": 0, "scarica": 0}
rete_ok = [True]
def finta_api(p):
    chiamate["api"] += 1
    if not rete_ok[0]:
        raise sa.ErroreArte("Commons non raggiungibile")
    if p.get("list") == "categorymembers":
        return {"query": {"categorymembers": [{"ns": 6, "title": "File:Opera %d.jpg" % i} for i in range(5)] + [{"ns": 6, "title": "File:Sound.ogg"}, {"ns": 14, "title": "Category:Sotto"}]}}
    t = p["titles"]
    if t.endswith("0.jpg"):   # verticale: scartata
        w, hh, lic = 1500, 2000, "Public domain"
    elif t.endswith("1.jpg"):   # licenza non libera: scartata
        w, hh, lic = 3000, 2000, "All rights reserved"
    else:
        w, hh, lic = 3000, 2000, "Public domain"
    return {"query": {"pages": {"1": {"imageinfo": [{"width": w, "height": hh, "mime": "image/jpeg", "thumburl": "https://upload.wikimedia.org/x/" + t[5:].replace(" ", "_"),
            "descriptionurl": "https://commons.wikimedia.org/wiki/" + t.replace(" ", "_"),
            "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": "<a href='x'>Claude <b>Monet</b></a>"}, "ObjectName": {"value": "Le ninfee"}}}]}}}}
def finta_scarica(u):
    chiamate["scarica"] += 1
    return JPG, "image/jpeg"
ORIG = sa._scarica
sa._api, sa._scarica, sa.SINCRONO = finta_api, finta_scarica, True
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ok("senza accesso non si vede", c.get("/sfondo-arte/corrente").status_code == 401)
    ok("la preferenza 'arte' e' ammessa", c.put("/account/preferenze/sfondo", headers=H, json={"valore": "arte"}).status_code == 200)
    ok("un valore inventato resta rifiutato", c.put("/account/preferenze/sfondo", headers=H, json={"valore": "http://x"}).status_code == 422)
    s = sa.slot_di(); ok("lo slot dura 10 minuti", sa.slot_di(0) == 0 and sa.slot_di(599) == 0 and sa.slot_di(600) == 1)
    d = c.get("/sfondo-arte/corrente", headers=H).json()
    ok("prepara l'opera dell'intervallo", d["disponibile"] and d["slot"] == s and d["aggiornata"] and d["titolo"] == "Le ninfee", str(d))
    ok("autore ripulito dall'HTML e licenza libera", d["autore"] == "Claude Monet" and d["licenza"] == "Public domain" and d["pagina"].startswith("https://commons.wikimedia.org/"), str(d))
    ok("solo opere orizzontali e di licenza libera", sql("SELECT count(*) FROM sfondi_arte")[0][0] == 1 and chiamate["scarica"] == 1)
    r = c.get(f"/sfondo-arte/immagine/{s}", headers=H)
    ok("l'immagine si scarica dall'app", r.status_code == 200 and r.content == JPG and r.headers["content-type"] == "image/jpeg")
    ok("immagine inesistente: 404", c.get("/sfondo-arte/immagine/1", headers=H).status_code == 404)
    n = chiamate["api"]; c.get("/sfondo-arte/corrente", headers=H)
    ok("nello stesso intervallo non richiede di nuovo nulla", chiamate["api"] == n and chiamate["scarica"] == 1)
    # intervallo successivo con la rete assente: resta l'ultima opera
    rete_ok[0] = False; sa._ultimo_errore[0] = 0
    real = sa.slot_di; sa.slot_di = lambda ora=None: real(ora) + 1
    d = c.get("/sfondo-arte/corrente", headers=H).json()
    ok("senza Commons resta l'opera precedente", d["disponibile"] and d["slot"] == s and d["aggiornata"] is False and d["cambia_tra"] <= 60, str(d))
    ok("un insuccesso non blocca il servizio ne lo martella", c.get("/sfondo-arte/corrente", headers=H).status_code == 200)
    rete_ok[0] = True; sa._ultimo_errore[0] = 0
    d = c.get("/sfondo-arte/corrente", headers=H).json()
    ok("tornata la rete, arriva la nuova opera", d["slot"] == s + 1 and d["aggiornata"], str(d))
    sa.slot_di = real
    # archivio: se ne tengono solo 8
    for k in range(20, 30): sql("INSERT INTO sfondi_arte (slot,titolo,mime,immagine) VALUES (%s,'x','image/jpeg',%s)", (k, JPG))
    sa.prepara(s)  # gia' presente: non fa nulla
    sql("DELETE FROM sfondi_arte WHERE slot=%s", (s + 1,)); sa._ultimo_errore[0] = 0
    sa.slot_di = lambda ora=None: real(ora) + 2
    sa.prepara(s + 2)
    ok("l'archivio resta piccolo", sql("SELECT count(*) FROM sfondi_arte")[0][0] <= 8)
    sa.slot_di = real
    # indirizzi non di Wikimedia rifiutati
    sa._scarica = ORIG
    try: sa._scarica("http://evil.example/x.jpg"); rifiutato = False
    except sa.ErroreArte: rifiutato = True
    ok("scarica solo da Wikimedia", rifiutato)
src = open("app/static/vetro.js").read()
ok("l'app ruota l'opera e mostra autore e licenza", "aggiornaArte" in src and "vetro-didascalia" in src and "/sfondo-arte/corrente" in src)
print("TOTALE", sum(ris), "/", len(ris))
