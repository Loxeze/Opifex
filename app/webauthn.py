"""Verifica delle passkey (WebAuthn) senza librerie aggiuntive: solo 'cryptography', gia' presente.
Supporta chiavi ES256 (P-256) e RS256, attestazione 'none' (nessuna verifica dell'attestazione: serve solo a ricevere la chiave pubblica).
Si richiede sempre la verifica dell'utente (impronta, volto o PIN del telefono)."""
import base64
import hashlib
import json
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa


class ErroreWebAuthn(Exception):
    pass


def b64u(dati: bytes) -> str:
    return base64.urlsafe_b64encode(dati).rstrip(b"=").decode("ascii")


def da_b64u(testo: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(testo + "=" * (-len(testo) % 4))
    except Exception:
        raise ErroreWebAuthn("Dati non validi") from None


# ---------- CBOR minimo (solo cio' che serve alle passkey) ----------
def _cbor(d: bytes, i: int, profondita: int = 0):
    if profondita > 8 or i >= len(d):
        raise ErroreWebAuthn("Dati non validi")
    b = d[i]; i += 1
    tipo, info = b >> 5, b & 31
    if info < 24:
        n = info
    elif info in (24, 25, 26, 27):
        ln = {24: 1, 25: 2, 26: 4, 27: 8}[info]
        if i + ln > len(d):
            raise ErroreWebAuthn("Dati non validi")
        n = int.from_bytes(d[i:i + ln], "big"); i += ln
    else:
        raise ErroreWebAuthn("Dati non validi")
    if tipo == 0:
        return n, i
    if tipo == 1:
        return -1 - n, i
    if tipo in (2, 3):
        if n > len(d) - i:
            raise ErroreWebAuthn("Dati non validi")
        v = d[i:i + n]
        return (v if tipo == 2 else v.decode("utf-8", "replace")), i + n
    if tipo == 4:
        if n > 64:
            raise ErroreWebAuthn("Dati non validi")
        out = []
        for _ in range(n):
            v, i = _cbor(d, i, profondita + 1); out.append(v)
        return out, i
    if tipo == 5:
        if n > 64:
            raise ErroreWebAuthn("Dati non validi")
        out = {}
        for _ in range(n):
            k, i = _cbor(d, i, profondita + 1); v, i = _cbor(d, i, profondita + 1); out[k] = v
        return out, i
    if tipo == 7 and info in (20, 21, 22):
        return {20: False, 21: True, 22: None}[info], i
    raise ErroreWebAuthn("Dati non validi")


def cbor(d: bytes):
    v, _ = _cbor(d, 0)
    return v


def _dati_client(client_json: bytes, tipo: str, sfida: str, origine: str) -> None:
    try:
        c = json.loads(client_json)
    except ValueError:
        raise ErroreWebAuthn("Dati non validi") from None
    if c.get("type") != tipo:
        raise ErroreWebAuthn("Operazione non valida")
    if c.get("challenge") != sfida:
        raise ErroreWebAuthn("Sfida non valida o scaduta")
    if c.get("origin") != origine:
        raise ErroreWebAuthn("Indirizzo non riconosciuto")


def _dati_autenticatore(auth: bytes, rp_id: str) -> tuple[int, int]:
    if len(auth) < 37:
        raise ErroreWebAuthn("Dati non validi")
    if auth[:32] != hashlib.sha256(rp_id.encode()).digest():
        raise ErroreWebAuthn("Dominio non corrispondente")
    flag = auth[32]
    if not flag & 0x01:
        raise ErroreWebAuthn("Presenza non verificata")
    if not flag & 0x04:
        raise ErroreWebAuthn("Serve la verifica con impronta, volto o PIN")
    return flag, struct.unpack(">I", auth[33:37])[0]


def _chiave_da_cose(c: dict) -> tuple[str, int]:
    alg = c.get(3)
    if alg == -7 and c.get(1) == 2 and c.get(-1) == 1:
        x, y = c.get(-2), c.get(-3)
        if not (isinstance(x, bytes) and isinstance(y, bytes) and len(x) == len(y) == 32):
            raise ErroreWebAuthn("Chiave non valida")
        k = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
    elif alg == -257 and c.get(1) == 3:
        n, e = c.get(-1), c.get(-2)
        if not (isinstance(n, bytes) and isinstance(e, bytes)) or len(n) < 256:
            raise ErroreWebAuthn("Chiave non valida")
        k = rsa.RSAPublicNumbers(int.from_bytes(e, "big"), int.from_bytes(n, "big")).public_key()
    else:
        raise ErroreWebAuthn("Tipo di chiave non supportato")
    pem = k.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return pem, alg


def verifica_registrazione(client_json_b64: str, attestazione_b64: str, sfida: str, origine: str, rp_id: str) -> dict:
    """Restituisce credenziale_id, chiave_pubblica (PEM), algoritmo, contatore."""
    client = da_b64u(client_json_b64)
    _dati_client(client, "webauthn.create", sfida, origine)
    att = cbor(da_b64u(attestazione_b64))
    if not isinstance(att, dict) or not isinstance(att.get("authData"), bytes):
        raise ErroreWebAuthn("Dati non validi")
    auth = att["authData"]
    flag, contatore = _dati_autenticatore(auth, rp_id)
    if not flag & 0x40 or len(auth) < 55:
        raise ErroreWebAuthn("Credenziale mancante")
    lung = struct.unpack(">H", auth[53:55])[0]
    cred = auth[55:55 + lung]
    if len(cred) != lung or not 16 <= lung <= 1023:
        raise ErroreWebAuthn("Credenziale non valida")
    chiave, _ = _cbor(auth, 55 + lung)
    if not isinstance(chiave, dict):
        raise ErroreWebAuthn("Chiave non valida")
    pem, alg = _chiave_da_cose(chiave)
    return {"credenziale_id": b64u(cred), "chiave_pubblica": pem, "algoritmo": alg, "contatore": contatore}


def verifica_accesso(client_json_b64: str, auth_b64: str, firma_b64: str, sfida: str, origine: str, rp_id: str,
                     chiave_pem: str, algoritmo: int, contatore_salvato: int) -> int:
    """Verifica la firma; restituisce il nuovo contatore."""
    client = da_b64u(client_json_b64)
    _dati_client(client, "webauthn.get", sfida, origine)
    auth = da_b64u(auth_b64)
    _, contatore = _dati_autenticatore(auth, rp_id)
    if (contatore or contatore_salvato) and contatore <= contatore_salvato:
        raise ErroreWebAuthn("Credenziale gia' usata o clonata")
    firmato = auth + hashlib.sha256(client).digest()
    k = serialization.load_pem_public_key(chiave_pem.encode())
    try:
        if algoritmo == -7:
            k.verify(da_b64u(firma_b64), firmato, ec.ECDSA(hashes.SHA256()))
        elif algoritmo == -257:
            k.verify(da_b64u(firma_b64), firmato, padding.PKCS1v15(), hashes.SHA256())
        else:
            raise ErroreWebAuthn("Tipo di chiave non supportato")
    except InvalidSignature:
        raise ErroreWebAuthn("Firma non valida") from None
    return contatore
