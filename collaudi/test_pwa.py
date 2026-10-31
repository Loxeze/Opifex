import os, sys, tempfile, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import webpush, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")



import base64, struct, jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from app.db import connessione
def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64d(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
# dispositivo finto: chiavi del browser
ua = ec.generate_private_key(ec.SECP256R1())
ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
auth = os.urandom(16)
def decifra(corpo):
    """Lato browser (RFC 8291): ricava le chiavi e decifra."""
    salt, rs, idlen = corpo[:16], struct.unpack("!I", corpo[16:20])[0], corpo[20]
    as_pub, ct = corpo[21:21 + idlen], corpo[21 + idlen:]
    ecdh = ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = HKDF(hashes.SHA256(), 32, auth, b"WebPush: info\x00" + ua_pub + as_pub).derive(ecdh)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    pt = AESGCM(cek).decrypt(nonce, ct, None)
    return pt.rstrip(b"\x00")[:-1]
inviati, stato_risposta = [], {"codice": 201}
def finto_post(endpoint, corpo, intestazioni):
    inviati.append((endpoint, corpo, intestazioni)); return stato_risposta["codice"]
webpush._post = finto_post
EP = "https://fcm.googleapis.com/fcm/send/abc123"
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    # ---- file dell'app installabile
    m = c.get("/app/manifest.webmanifest")
    j = m.json()
    ok("manifest servito con il tipo corretto, installabile (start_url, standalone, icone 192/512)", m.status_code == 200 and "manifest+json" in m.headers["content-type"] and j["display"] == "standalone" and j["start_url"] == "/app/" and {i["sizes"] for i in j["icons"]} >= {"192x192", "512x512"}, m.headers.get("content-type"))
    ok("icone e service worker raggiungibili", all(c.get("/app/" + f).status_code == 200 for f in ("icona-192.png", "icona-512.png", "icona-apple-180.png", "sw.js", "offline.html")))
    ok("l'interfaccia non resta in cache vecchia (no-cache)", c.get("/app/stile.css").headers.get("cache-control") == "no-cache")
    idx = c.get("/app/").text
    ok("index: manifest, icona Apple, colore tema", 'rel="manifest"' in idx and "apple-touch-icon" in idx and 'name="theme-color"' in idx)
    # ---- QR
    ok("invito: solo titolare", c.get("/gestione/app/invito", headers=HC).status_code == 403)
    inv = c.get("/gestione/app/invito", headers={**H, "host": "app.opifex.space", "x-forwarded-proto": "https"}).json()
    ok("QR: SVG e indirizzo dell'app", inv["svg"].startswith("<svg") and inv["url"] == "https://app.opifex.space/app/" and not inv["personalizzato"], inv["url"])
    ok("indirizzo personalizzato validato e usato", c.put("/gestione/app/url", headers=H, json={"url": "http://x"}).status_code == 422 and c.put("/gestione/app/url", headers=H, json={"url": "https://miaapp.example.it/"}).status_code == 200
       and c.get("/gestione/app/invito", headers=H).json()["url"] == "https://miaapp.example.it/app/")
    # ---- chiavi VAPID
    k1 = c.get("/pwa/chiave", headers=H).json()["chiave"]; k2 = c.get("/pwa/chiave", headers=HC).json()["chiave"]
    ok("chiave pubblica VAPID: 65 byte, stabile, uguale per tutti", len(b64d(k1)) == 65 and k1 == k2)
    ok("chiave privata cifrata nel database", "BEGIN" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='vapid_privata'")[0][0])
    ok("senza accesso: 401", c.get("/pwa/chiave").status_code in (401, 403))
    # ---- iscrizione
    body = {"endpoint": EP, "p256dh": b64u(ua_pub), "auth": b64u(auth), "dispositivo": "Android Chrome"}
    ok("iscrizione dispositivo", c.post("/pwa/iscrivi", headers=H, json=body).status_code == 201 and sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 1)
    ok("stessa iscrizione: aggiornata, non duplicata", c.post("/pwa/iscrivi", headers=H, json=body).status_code == 201 and sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 1)
    ok("indirizzi non dei servizi push noti rifiutati (anti SSRF)", all(c.post("/pwa/iscrivi", headers=H, json={**body, "endpoint": e}).status_code == 422 for e in
       ("https://127.0.0.1/x", "http://fcm.googleapis.com/x", "https://evil.example.com/fcm.googleapis.com", "https://fcm.googleapis.com.evil.com/x", "https://localhost/x", "https://fcm.googleapis.com:8443/x")))
    ok("chiavi non valide rifiutate", c.post("/pwa/iscrivi", headers=H, json={**body, "endpoint": EP + "2", "p256dh": "AAAA"}).status_code == 422)
    ok("dispositivi dell'utente", [d["dispositivo"] for d in c.get("/pwa/dispositivi", headers=H).json()["dispositivi"]] == ["Android Chrome"] and c.get("/pwa/dispositivi", headers=HC).json()["dispositivi"] == [])
    # ---- invio
    r = c.post("/pwa/prova", headers=H).json()
    ep, corpo, ih = inviati[-1]
    msg = json.loads(decifra(corpo))
    ok("prova: raggiunge il dispositivo e il messaggio si decifra lato browser", r["raggiunti"] == 1 and msg["titolo"] == "Opifex" and "funzionano" in msg["testo"], str(msg))
    ok("intestazioni Web Push corrette", ih["Content-Encoding"] == "aes128gcm" and ih["TTL"] == "86400" and ih["Authorization"].startswith("vapid t="))
    tok = ih["Authorization"].split("t=")[1].split(",k=")[0]; chiave_k = ih["Authorization"].split(",k=")[1]
    pub_pem = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64d(chiave_k))
    cl = jwt.decode(tok, pub_pem, algorithms=["ES256"], audience="https://fcm.googleapis.com")
    ok("firma VAPID valida (ES256), audience = servizio push, scadenza entro 24 ore", chiave_k == k1 and cl["exp"] - __import__("time").time() < 86400 and cl["sub"].startswith("mailto:"))
    # unicode e lunghezza
    with connessione() as cn:
        webpush.a_tutti(cn, "Opifex", "Perché l'è già così — ✓ àèìòù")
    ok("testo con accenti e simboli", "Perché l'è già così — ✓ àèìòù" in json.loads(decifra(inviati[-1][1]))["testo"])
    try:
        webpush.cifra(b"x" * 5000, b64u(ua_pub), b64u(auth)); lungo = False
    except webpush.ErrorePush: lungo = True
    ok("messaggi troppo lunghi rifiutati", lungo)
    # ---- notifiche del sistema -> push
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Bando in scadenza domani', TRUE)")
    n0 = len(inviati)
    with connessione() as cn:
        n = webpush.invia_notifiche(cn); n2 = webpush.invia_notifiche(cn)
    ok("la notifica del sistema arriva come push (urgente) una volta sola", n == 1 and n2 == 0 and len(inviati) == n0 + 1 and "urgente" in json.loads(decifra(inviati[-1][1]))["titolo"] and "Bando in scadenza" in json.loads(decifra(inviati[-1][1]))["testo"])
    ok("le notifiche gia' esistenti all'attivazione non vengono rispedite", sql("SELECT count(*) FROM notifiche WHERE push_il IS NULL")[0][0] == 0)
    # ---- iscrizione scaduta
    stato_risposta["codice"] = 410
    sql("INSERT INTO notifiche (testo) VALUES ('Altra notifica')")
    with connessione() as cn: webpush.invia_notifiche(cn)
    ok("dispositivo scaduto (410): iscrizione rimossa", sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 0)
    stato_risposta["codice"] = 500
    c.post("/pwa/iscrivi", headers=H, json=body)
    ok("errore temporaneo del servizio: l'iscrizione resta", c.post("/pwa/prova", headers=H).json()["raggiunti"] == 0 and sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 1)
    ok("scollegare un dispositivo; non quello di un altro", c.post("/pwa/disiscrivi", headers=HC, json={"endpoint": EP}).status_code == 200 and sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 1
       and c.post("/pwa/disiscrivi", headers=H, json={"endpoint": EP}).status_code == 200 and sql("SELECT count(*) FROM push_iscrizioni")[0][0] == 0)
    sql("INSERT INTO notifiche (testo) VALUES ('Senza dispositivi')")
    with connessione() as cn: ok("senza dispositivi nulla da inviare, ma non resta in coda", webpush.invia_notifiche(cn) == 0 and sql("SELECT count(*) FROM notifiche WHERE push_il IS NULL")[0][0] == 1)
print("TOTALE", sum(ris), "/", len(ris))
