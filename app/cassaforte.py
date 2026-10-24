"""Cassaforte delle credenziali dei siti: cifratura con chiave che vive solo nel file .env."""
from cryptography.fernet import Fernet, InvalidToken

from .config import impostazioni


class CassaforteNonConfigurata(Exception):
    pass


def _fernet() -> Fernet:
    if not impostazioni.chiave_cassaforte:
        raise CassaforteNonConfigurata("Cassaforte non configurata sul server (manca CHIAVE_CASSAFORTE)")
    try:
        return Fernet(impostazioni.chiave_cassaforte.encode())
    except ValueError:
        raise CassaforteNonConfigurata("CHIAVE_CASSAFORTE non valida")


def cifra(testo: str) -> str:
    return _fernet().encrypt(testo.encode("utf-8")).decode("ascii")


def decifra(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise CassaforteNonConfigurata("Impossibile decifrare: la chiave della cassaforte e' cambiata")
