"""Codici a 6 cifre dell'app di autenticazione (RFC 6238, SHA-1, 30 secondi) con la sola libreria standard."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PASSO = 30


def nuovo_segreto() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _codice(segreto: str, contatore: int) -> str:
    chiave = base64.b32decode(segreto + "=" * (-len(segreto) % 8))
    d = hmac.new(chiave, struct.pack(">Q", contatore), hashlib.sha1).digest()
    o = d[-1] & 15
    return f"{(struct.unpack('>I', d[o:o + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def codice_adesso(segreto: str, ora: float | None = None) -> str:
    return _codice(segreto, int((ora if ora is not None else time.time()) // PASSO))


def verifica(segreto: str, codice: str, ultimo_passo: int = 0, ora: float | None = None) -> int | None:
    """Accetta il passo corrente e quello adiacente (orologi non perfetti). Un passo gia' usato non vale due volte.
    Restituisce il passo accettato oppure None."""
    codice = (codice or "").replace(" ", "")
    if len(codice) != 6 or not codice.isdigit():
        return None
    adesso = int((ora if ora is not None else time.time()) // PASSO)
    trovato = None
    for passo in (adesso - 1, adesso, adesso + 1):
        if hmac.compare_digest(_codice(segreto, passo), codice) and passo > ultimo_passo:
            trovato = passo
    return trovato


def uri(segreto: str, email: str, emittente: str = "Opifex") -> str:
    return f"otpauth://totp/{quote(emittente)}:{quote(email)}?secret={segreto}&issuer={quote(emittente)}&algorithm=SHA1&digits=6&period=30"


def matrice_qr(testo: str) -> list[list[int]]:
    import segno
    return [[1 if b else 0 for b in riga] for riga in segno.make(testo, error="m", micro=False).matrix]
