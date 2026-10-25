"""Notifiche push sul telefono e sul tablet (Web Push, RFC 8030/8291/8292) senza dipendenze esterne: cifratura con `cryptography`, firma VAPID con PyJWT.
Le chiavi VAPID si generano al primo uso; la privata e' nella cassaforte. Le iscrizioni accettate puntano solo ai servizi push noti dei browser."""
import base64
import json
import os
import struct
import time
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import cassaforte

SERVIZI = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com", "web.push.apple.com")
MAX_PAYLOAD = 2000
SOGGETTO = "mailto:lo.zeppa@gmail.com"


class ErrorePush(Exception):
    pass


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def endpoint_valido(url: str) -> bool:
    p = urlparse(url or "")
    host = (p.hostname or "").lower()
    return p.scheme == "https" and bool(host) and p.port in (None, 443) and any(host == s or host.endswith("." + s) for s in SERVIZI)


# ---------- cifratura (RFC 8291, aes128gcm) ----------
def cifra(payload: bytes, p256dh: str, auth: str, chiave_server: ec.EllipticCurvePrivateKey | None = None, salt: bytes | None = None) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ErrorePush("Messaggio troppo lungo")
    ua_pub = b64u_dec(p256dh)
    segreto = b64u_dec(auth)
    try:
        ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    except ValueError as e:
        raise ErrorePush("Chiave del dispositivo non valida") from e
    k = chiave_server or ec.generate_private_key(ec.SECP256R1())
    as_pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ecdh = k.exchange(ec.ECDH(), ua_key)
    salt = salt or os.urandom(16)
    ikm = HKDF(hashes.SHA256(), 32, segreto, b"WebPush: info\x00" + ua_pub + as_pub).derive(ecdh)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    cifrato = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!I", 4096) + bytes([len(as_pub)]) + as_pub + cifrato


# ---------- chiavi VAPID ----------
def _imp(conn, chiave):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else None


def chiavi(conn) -> tuple[str, str]:
    """(privata PEM, pubblica base64url non compressa). Le crea una volta sola."""
    priv, pub = _imp(conn, "vapid_privata"), _imp(conn, "vapid_pubblica")
    if priv and pub:
        return cassaforte.decifra(priv), pub
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub = b64u(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    for nome, v in (("vapid_privata", cassaforte.cifra(pem)), ("vapid_pubblica", pub)):
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (nome, v))
    return pem, pub


def intestazione_vapid(endpoint: str, pem: str, pub: str) -> str:
    p = urlparse(endpoint)
    token = jwt.encode({"aud": f"{p.scheme}://{p.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SOGGETTO}, pem, algorithm="ES256")
    return f"vapid t={token},k={pub}"


# ---------- invio ----------
def _post(endpoint: str, corpo: bytes, intestazioni: dict) -> int:
    """Isolato per poterlo sostituire nei collaudi."""
    return httpx.post(endpoint, content=corpo, headers=intestazioni, timeout=15, follow_redirects=False).status_code


def invia(conn, sottoscrizione: dict, titolo: str, testo: str, url: str = "/app/") -> str:
    """Invia un messaggio a un dispositivo. Ritorna 'ok', 'scaduta' (iscrizione da eliminare) o 'errore'."""
    if not endpoint_valido(sottoscrizione["endpoint"]):
        return "scaduta"
    pem, pub = chiavi(conn)
    corpo = cifra(json.dumps({"titolo": titolo[:80], "testo": testo[:300], "url": url}, ensure_ascii=False).encode(), sottoscrizione["p256dh"], sottoscrizione["auth"])
    try:
        stato = _post(sottoscrizione["endpoint"], corpo, {"TTL": "86400", "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                                                         "Authorization": intestazione_vapid(sottoscrizione["endpoint"], pem, pub), "Urgency": "normal"})
    except httpx.HTTPError:
        return "errore"
    if stato in (404, 410):
        return "scaduta"
    return "ok" if 200 <= stato < 300 else "errore"


def a_tutti(conn, titolo: str, testo: str, utente_id: int | None = None) -> int:
    """Invia a tutti i dispositivi (o a quelli di un utente); elimina le iscrizioni scadute. Ritorna i dispositivi raggiunti."""
    n = 0
    q, par = "SELECT * FROM push_iscrizioni", ()
    if utente_id is not None:
        q, par = q + " WHERE utente_id = %s", (utente_id,)
    for s in conn.execute(q, par).fetchall():
        esito = invia(conn, s, titolo, testo)
        if esito == "scaduta":
            conn.execute("DELETE FROM push_iscrizioni WHERE id = %s", (s["id"],))
        elif esito == "ok":
            n += 1
    return n


def invia_notifiche(conn) -> int:
    """Manda come push le notifiche del sistema non ancora spedite (ultime 24 ore) al titolare. Ritorna quante ne ha spedite."""
    tit = conn.execute("SELECT id FROM utenti WHERE ruolo_globale = 'titolare' AND attivo ORDER BY id LIMIT 1").fetchone()
    if tit is None or not conn.execute("SELECT 1 FROM push_iscrizioni WHERE utente_id = %s LIMIT 1", (tit["id"],)).fetchone():
        conn.execute("UPDATE notifiche SET push_il = NOW() WHERE push_il IS NULL AND creata_il < NOW() - interval '1 day'")
        return 0
    n = 0
    for x in conn.execute("SELECT id, testo, urgente FROM notifiche WHERE push_il IS NULL AND creata_il > NOW() - interval '1 day' ORDER BY id LIMIT 10").fetchall():
        a_tutti(conn, "Opifex · urgente" if x["urgente"] else "Opifex", x["testo"], tit["id"])
        conn.execute("UPDATE notifiche SET push_il = NOW() WHERE id = %s", (x["id"],))
        conn.commit()
        n += 1
    return n
