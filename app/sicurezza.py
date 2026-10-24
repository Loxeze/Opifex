"""Password cifrate e token di accesso."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import impostazioni

ALGORITMO = "HS256"


def _byte(password: str) -> bytes:
    # bcrypt considera solo i primi 72 byte: il taglio e' esplicito e uguale in cifratura e verifica
    return password.encode("utf-8")[:72]


def cifra_password(password: str) -> str:
    return bcrypt.hashpw(_byte(password), bcrypt.gensalt()).decode("ascii")


def verifica_password(password: str, hash_salvato: str) -> bool:
    try:
        return bcrypt.checkpw(_byte(password), hash_salvato.encode("ascii"))
    except ValueError:
        return False


# Serve a far durare uguale il login anche quando l'email non esiste (non rivela quali email sono registrate)
HASH_FINTO = cifra_password("password-finta-per-uniformare-i-tempi")


def crea_token(utente_id: int, ruolo: str) -> str:
    adesso = datetime.now(timezone.utc)
    payload = {"sub": str(utente_id), "ruolo": ruolo, "iat": int(adesso.timestamp()),
               "exp": adesso + timedelta(hours=impostazioni.token_durata_ore)}
    return jwt.encode(payload, impostazioni.secret_key, algorithm=ALGORITMO)


def crea_sfida(utente_id: int) -> str:
    """Gettone breve (5 minuti) dato dopo la password giusta: serve solo a completare i passi successivi, non apre il sistema."""
    adesso = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(utente_id), "scopo": "sfida", "exp": adesso + timedelta(minutes=5)},
                      impostazioni.secret_key, algorithm=ALGORITMO)


def leggi_sfida(sfida: str) -> int:
    """Restituisce l'id utente oppure solleva jwt.PyJWTError."""
    d = jwt.decode(sfida, impostazioni.secret_key, algorithms=[ALGORITMO])
    if d.get("scopo") != "sfida":
        raise jwt.InvalidTokenError("non e' una sfida")
    return int(d["sub"])


def leggi_token(token: str) -> dict:
    """Solleva jwt.PyJWTError se il token e' scaduto o non valido."""
    return jwt.decode(token, impostazioni.secret_key, algorithms=[ALGORITMO])
