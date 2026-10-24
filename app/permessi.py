"""Chi e' l'utente corrente e a quali divisioni puo' accedere."""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connessione
from .sicurezza import leggi_token

_schema = HTTPBearer(auto_error=False)


def utente_corrente(cred: HTTPAuthorizationCredentials = Depends(_schema)) -> dict:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")
    try:
        dati = leggi_token(cred.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta o non valida")

    if dati.get("scopo"):   # una sfida di accesso non vale come sessione
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta o non valida")

    with connessione() as conn:
        riga = conn.execute(
            "SELECT id, nome, email, ruolo_globale, totp_attivo, token_valido_dal FROM utenti WHERE id = %s AND attivo",
            (int(dati["sub"]),),
        ).fetchone()
    if riga is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utente non attivo")
    # password o secondo fattore cambiati dopo l'emissione: le vecchie sessioni non valgono piu'
    if int(dati.get("iat", 0)) < int(riga.pop("token_valido_dal").timestamp()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta o non valida")
    return riga


def solo_titolare(utente: dict = Depends(utente_corrente)) -> dict:
    if utente["ruolo_globale"] != "titolare":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Riservato al titolare")
    return utente


def divisioni_visibili(utente: dict) -> list[int] | None:
    """None = tutte le divisioni (titolare). Altrimenti l'elenco degli id consentiti."""
    if utente["ruolo_globale"] == "titolare":
        return None
    with connessione() as conn:
        righe = conn.execute(
            "SELECT divisione_id FROM accessi_divisione WHERE utente_id = %s",
            (utente["id"],),
        ).fetchall()
    return [r["divisione_id"] for r in righe]
