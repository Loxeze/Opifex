"""Accesso degli utenti umani: password + secondo fattore (app di autenticazione), codici di recupero,
blocco dopo troppi errori, gestione dei collaboratori da parte del titolare."""
import hashlib
import hmac
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import registro
from . import cassaforte, totp
from .config import impostazioni
from .db import connessione
from .permessi import solo_titolare, utente_corrente
from .sicurezza import HASH_FINTO, cifra_password, crea_sfida, crea_token, leggi_sfida, verifica_password

router = APIRouter()

MAX_ERRORI_IP = 30      # errori ammessi da uno stesso indirizzo di rete (qualunque email), per la stessa finestra
MAX_ERRORI = 5          # errori consentiti ...
FINESTRA_MIN = 15       # ... ogni 15 minuti, per ogni email
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _impronta(testo: str) -> str:
    return hmac.new(impostazioni.secret_key.encode(), testo.strip().lower().encode(), hashlib.sha256).hexdigest()


def _chiave_ip(request: Request) -> str:
    return _impronta("ip:" + (request.client.host if request.client else "?"))


def _bloccato(conn, chiave: str, massimo: int = MAX_ERRORI) -> bool:
    n = conn.execute("SELECT count(*) AS n FROM tentativi_accesso WHERE chiave=%s AND quando > NOW() - make_interval(mins => %s)",
                     (chiave, FINESTRA_MIN)).fetchone()["n"]
    return n >= massimo


def _errore_tentativo(conn, chiave: str, ip: str | None = None):
    # connessione a parte: l'errore resta registrato anche se la richiesta fallisce e annulla il resto
    with connessione() as c2:
        c2.execute("INSERT INTO tentativi_accesso (chiave) VALUES (%s)", (chiave,))
        if ip:
            c2.execute("INSERT INTO tentativi_accesso (chiave) VALUES (%s)", (ip,))
        c2.execute("DELETE FROM tentativi_accesso WHERE quando < NOW() - INTERVAL '1 day'")


def _controlla_blocco(conn, chiave: str, ip: str | None = None):
    if _bloccato(conn, chiave) or (ip and _bloccato(conn, ip, MAX_ERRORI_IP)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Troppi tentativi sbagliati. Riprova tra {FINESTRA_MIN} minuti.")


def _hash_recupero(codice: str) -> str:
    return _impronta("recupero:" + codice.replace("-", "").replace(" ", "").upper())


def _nuovi_recupero(conn, uid: int) -> list[str]:
    conn.execute("DELETE FROM codici_recupero WHERE utente_id=%s", (uid,))
    codici = ["".join(secrets.choice(ALFABETO) for _ in range(10)) for _ in range(8)]
    for c in codici:
        conn.execute("INSERT INTO codici_recupero (utente_id, codice_hash) VALUES (%s,%s)", (uid, _hash_recupero(c)))
    return [c[:5] + "-" + c[5:] for c in codici]


def _utente_da_sfida(conn, sfida: str) -> dict:
    try:
        uid = leggi_sfida(sfida)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso scaduto: riparti dalla password")
    u = conn.execute("SELECT * FROM utenti WHERE id=%s AND attivo", (uid,)).fetchone()
    if u is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso scaduto: riparti dalla password")
    return u


def _prossimo_passo(conn, u: dict) -> dict:
    """Dice cosa manca per entrare, oppure apre la sessione."""
    if u["deve_cambiare_password"]:
        return {"passo": "cambia_password", "sfida": crea_sfida(u["id"])}
    if u["totp_attivo"]:
        return {"passo": "codice", "sfida": crea_sfida(u["id"])}
    if u["ruolo_globale"] != "titolare":   # per i collaboratori il secondo fattore e' obbligatorio
        return {"passo": "configura_2fa", "sfida": crea_sfida(u["id"])}
    return _sessione(conn, u)


def _sessione(conn, u: dict, extra: dict | None = None) -> dict:
    conn.execute("UPDATE utenti SET ultimo_accesso = NOW() WHERE id=%s", (u["id"],))
    conn.execute("DELETE FROM tentativi_accesso WHERE chiave=%s", (_impronta(u["email"]),))
    return {"passo": "ok", "token": crea_token(u["id"], u["ruolo_globale"]), "nome": u["nome"], "ruolo": u["ruolo_globale"],
            "secondo_fattore": u["totp_attivo"] or bool(extra), **(extra or {})}


class DatiLogin(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(d: DatiLogin, request: Request):
    chiave, ip = _impronta(d.email), _chiave_ip(request)
    with connessione() as conn:
        _controlla_blocco(conn, chiave, ip)
        u = conn.execute("SELECT * FROM utenti WHERE email=%s AND attivo", (d.email.strip().lower(),)).fetchone()
        # stessi messaggi e stessi tempi per email o password errate
        if u is None:
            verifica_password(d.password, HASH_FINTO)
            _errore_tentativo(conn, chiave, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide")
        if not verifica_password(d.password, u["password_hash"]):
            _errore_tentativo(conn, chiave, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide")
        r = _prossimo_passo(conn, u)
    # compatibilita': chi entra subito riceve anche nome e ruolo come prima
    return r


def _controlla_password_nuova(p: str):
    if len(p) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password troppo corta (minimo 10 caratteri)")
    if p.lower() in ("password123!", "0123456789", "passwordpassword"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password troppo banale")


class NuovaPasswordSfida(BaseModel):
    sfida: str
    nuova: str = Field(max_length=200)


@router.post("/login/password")
def cambia_password_iniziale(d: NuovaPasswordSfida):
    """Prima password personale al posto di quella temporanea."""
    with connessione() as conn:
        u = _utente_da_sfida(conn, d.sfida)
        if not u["deve_cambiare_password"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Password gia' personalizzata")
        _controlla_password_nuova(d.nuova)
        if verifica_password(d.nuova, u["password_hash"]):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli una password diversa da quella temporanea")
        conn.execute("UPDATE utenti SET password_hash=%s, deve_cambiare_password=FALSE, token_valido_dal=NOW() WHERE id=%s",
                     (cifra_password(d.nuova), u["id"]))
        u = conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone()
        return _prossimo_passo(conn, u)


class SoloSfida(BaseModel):
    sfida: str


def _avvia(conn, u: dict) -> dict:
    if u["totp_attivo"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Secondo fattore gia' attivo")
    segreto = totp.nuovo_segreto()
    conn.execute("UPDATE utenti SET totp_segreto_cifrato=%s, totp_ultimo_passo=0 WHERE id=%s", (cassaforte.cifra(segreto), u["id"]))
    link = totp.uri(segreto, u["email"])
    return {"segreto": segreto, "uri": link, "matrice": totp.matrice_qr(link)}


@router.post("/login/2fa/avvia")
def avvia_da_sfida(d: SoloSfida):
    with connessione() as conn:
        u = _utente_da_sfida(conn, d.sfida)
        if u["deve_cambiare_password"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Prima scegli la tua password")
        return _avvia(conn, u)


class ConfermaSfida(BaseModel):
    sfida: str
    codice: str = Field(max_length=20)


def _conferma(conn, u: dict, codice: str, ip: str | None = None) -> list[str]:
    chiave = _impronta(u["email"])
    _controlla_blocco(conn, chiave, ip)
    if not u["totp_segreto_cifrato"] or u["totp_attivo"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nessuna configurazione in corso")
    passo = totp.verifica(cassaforte.decifra(u["totp_segreto_cifrato"]), codice)
    if passo is None:
        _errore_tentativo(conn, chiave, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codice non corretto")
    conn.execute("UPDATE utenti SET totp_attivo=TRUE, totp_ultimo_passo=%s, token_valido_dal=NOW() WHERE id=%s", (passo, u["id"]))
    return _nuovi_recupero(conn, u["id"])


@router.post("/login/2fa/conferma")
def conferma_da_sfida(d: ConfermaSfida, request: Request):
    with connessione() as conn:
        u = _utente_da_sfida(conn, d.sfida)
        if u["deve_cambiare_password"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Prima scegli la tua password")
        codici = _conferma(conn, u, d.codice, _chiave_ip(request))
        u = conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone()
        return _sessione(conn, u, {"codici_recupero": codici})


@router.post("/login/2fa")
def secondo_fattore(d: ConfermaSfida, request: Request):
    ip = _chiave_ip(request)
    with connessione() as conn:
        u = _utente_da_sfida(conn, d.sfida)
        if u["deve_cambiare_password"] or not u["totp_attivo"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Passo non valido")
        chiave = _impronta(u["email"])
        _controlla_blocco(conn, chiave, ip)
        passo = totp.verifica(cassaforte.decifra(u["totp_segreto_cifrato"]), d.codice, u["totp_ultimo_passo"])
        if passo is not None:
            # il passo si consuma con un aggiornamento condizionato: due richieste insieme non passano entrambe
            if not conn.execute("UPDATE utenti SET totp_ultimo_passo=%s WHERE id=%s AND totp_ultimo_passo < %s RETURNING 1",
                                (passo, u["id"], passo)).fetchone():
                passo = None
        if passo is None:
            rec = conn.execute("""UPDATE codici_recupero SET usato_il=NOW() WHERE id = (
                                    SELECT id FROM codici_recupero WHERE utente_id=%s AND codice_hash=%s AND usato_il IS NULL LIMIT 1)
                                  RETURNING id""", (u["id"], _hash_recupero(d.codice))).fetchone() if len(d.codice.replace("-", "").replace(" ", "")) == 10 else None
            if rec is None:
                _errore_tentativo(conn, chiave, ip)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codice non corretto")
            rimasti = conn.execute("SELECT count(*) AS n FROM codici_recupero WHERE utente_id=%s AND usato_il IS NULL", (u["id"],)).fetchone()["n"]
            return _sessione(conn, u, {"recupero_usato": True, "codici_rimasti": rimasti})
        return _sessione(conn, u)


# ---------- Il mio account (utente gia' dentro) ----------
@router.get("/account")
def il_mio_account(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        n = conn.execute("SELECT count(*) AS n FROM codici_recupero WHERE utente_id=%s AND usato_il IS NULL", (u["id"],)).fetchone()["n"]
    return {"nome": u["nome"], "email": u["email"], "ruolo": u["ruolo_globale"],
            "secondo_fattore": u["totp_attivo"], "codici_recupero_rimasti": n}


class CambioPassword(BaseModel):
    attuale: str = Field(max_length=200)
    nuova: str = Field(max_length=200)


@router.post("/account/password")
def cambia_password(d: CambioPassword, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        chiave = _impronta(u["email"])
        _controlla_blocco(conn, chiave)
        riga = conn.execute("SELECT password_hash FROM utenti WHERE id=%s", (u["id"],)).fetchone()
        if not verifica_password(d.attuale, riga["password_hash"]):
            _errore_tentativo(conn, chiave)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password attuale non corretta")
        _controlla_password_nuova(d.nuova)
        conn.execute("UPDATE utenti SET password_hash=%s, deve_cambiare_password=FALSE, token_valido_dal=NOW() WHERE id=%s",
                     (cifra_password(d.nuova), u["id"]))
        nuovo = crea_token(u["id"], u["ruolo_globale"])
    return {"token": nuovo}   # le altre sessioni aperte vengono chiuse


@router.post("/account/2fa/avvia")
def mio_avvia(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return _avvia(conn, conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone())


class SoloCodice(BaseModel):
    codice: str = Field(max_length=20)


@router.post("/account/2fa/conferma")
def mio_conferma(d: SoloCodice, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        codici = _conferma(conn, conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone(), d.codice)
        return {"codici_recupero": codici, "token": crea_token(u["id"], u["ruolo_globale"])}


class Disattiva(BaseModel):
    password: str = Field(max_length=200)
    codice: str = Field(max_length=20)


@router.post("/account/2fa/disattiva")
def mio_disattiva(d: Disattiva, u: dict = Depends(utente_corrente)):
    if u["ruolo_globale"] != "titolare":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Per i collaboratori il secondo fattore e' obbligatorio")
    with connessione() as conn:
        chiave = _impronta(u["email"])
        _controlla_blocco(conn, chiave)
        riga = conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone()
        if not riga["totp_attivo"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Secondo fattore non attivo")
        if not verifica_password(d.password, riga["password_hash"]) or totp.verifica(
                cassaforte.decifra(riga["totp_segreto_cifrato"]), d.codice, riga["totp_ultimo_passo"]) is None:
            _errore_tentativo(conn, chiave)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password o codice non corretti")
        conn.execute("UPDATE utenti SET totp_attivo=FALSE, totp_segreto_cifrato=NULL, token_valido_dal=NOW() WHERE id=%s", (u["id"],))
        conn.execute("DELETE FROM codici_recupero WHERE utente_id=%s", (u["id"],))
        return {"token": crea_token(u["id"], u["ruolo_globale"])}


@router.post("/account/2fa/nuovi-codici")
def mio_nuovi_codici(d: Disattiva, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        chiave = _impronta(u["email"])
        _controlla_blocco(conn, chiave)
        riga = conn.execute("SELECT * FROM utenti WHERE id=%s", (u["id"],)).fetchone()
        if not riga["totp_attivo"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Secondo fattore non attivo")
        if not verifica_password(d.password, riga["password_hash"]) or totp.verifica(
                cassaforte.decifra(riga["totp_segreto_cifrato"]), d.codice, riga["totp_ultimo_passo"]) is None:
            _errore_tentativo(conn, chiave)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password o codice non corretti")
        return {"codici_recupero": _nuovi_recupero(conn, u["id"])}


# ---------- Gestione collaboratori (solo titolare) ----------
gestione = APIRouter(prefix="/gestione/utenti")


def _password_temporanea() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(4)) + "-" + "".join(secrets.choice(ALFABETO) for _ in range(4)) + \
           "-" + "".join(secrets.choice(ALFABETO) for _ in range(4)) + "-" + "".join(secrets.choice(ALFABETO) for _ in range(4))


@gestione.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = conn.execute("""SELECT u.id, u.nome, u.email, u.ruolo_globale AS ruolo, u.attivo, u.totp_attivo AS secondo_fattore,
                                       u.deve_cambiare_password AS password_temporanea, u.ultimo_accesso,
                                       COALESCE((SELECT array_agg(divisione_id ORDER BY divisione_id) FROM accessi_divisione WHERE utente_id=u.id), '{}') AS divisioni,
                                       COALESCE((SELECT array_agg(azienda_id ORDER BY azienda_id) FROM accessi_azienda WHERE utente_id=u.id), '{}') AS aziende
                                FROM utenti u ORDER BY u.id""").fetchall()
        divisioni = conn.execute("SELECT id, nome FROM divisioni ORDER BY nome").fetchall()
        aziende = conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall()
    return {"utenti": righe, "divisioni": divisioni, "aziende": aziende}


class NuovoCollaboratore(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    divisioni: list[int] = []
    aziende: list[int] = []


@gestione.post("", status_code=201)
def crea(d: NuovoCollaboratore, _: dict = Depends(solo_titolare)):
    email = d.email.strip().lower()
    if "@" not in email or " " in email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Email non valida")
    temp = _password_temporanea()
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM utenti WHERE email=%s", (email,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email gia' registrata")
        _verifica_divisioni(conn, d.divisioni)
        uid = conn.execute("INSERT INTO utenti (nome,email,password_hash,ruolo_globale,deve_cambiare_password) VALUES (%s,%s,%s,'collaboratore',TRUE) RETURNING id",
                           (d.nome.strip(), email, cifra_password(temp))).fetchone()["id"]
        for dv in set(d.divisioni):
            conn.execute("INSERT INTO accessi_divisione (utente_id, divisione_id) VALUES (%s,%s)", (uid, dv))
        _imposta_aziende(conn, uid, d.aziende)
    return {"id": uid, "password_temporanea": temp}   # mostrata una sola volta


def _imposta_aziende(conn, uid: int, ids: list[int]):
    ids = list(set(ids))
    if ids and conn.execute("SELECT count(*) AS n FROM aziende WHERE id = ANY(%s)", (ids,)).fetchone()["n"] != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Impresa inesistente")
    conn.execute("DELETE FROM accessi_azienda WHERE utente_id = %s", (uid,))
    for a in ids:
        conn.execute("INSERT INTO accessi_azienda (utente_id, azienda_id) VALUES (%s,%s)", (uid, a))


class Aziende(BaseModel):
    aziende: list[int]


@gestione.put("/{uid}/aziende")
def aziende_utente(uid: int, d: Aziende, t: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _altro_utente(conn, uid, t)
        _imposta_aziende(conn, uid, d.aziende)
        registro.registra(conn, t, "organizzazione", "imprese del collaboratore aggiornate", f"utente {uid}", "utente", uid)
    return {"ok": True}


def _verifica_divisioni(conn, ids):
    if ids:
        n = conn.execute("SELECT count(*) AS n FROM divisioni WHERE id = ANY(%s)", (list(set(ids)),)).fetchone()["n"]
        if n != len(set(ids)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Divisione inesistente")


def _altro_utente(conn, uid: int, titolare: dict) -> dict:
    u = conn.execute("SELECT * FROM utenti WHERE id=%s", (uid,)).fetchone()
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato")
    if u["id"] == titolare["id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Non puoi modificare il tuo stesso profilo da qui")
    return u


class Divisioni(BaseModel):
    divisioni: list[int]


@gestione.put("/{uid}/divisioni")
def divisioni(uid: int, d: Divisioni, t: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _altro_utente(conn, uid, t)
        _verifica_divisioni(conn, d.divisioni)
        conn.execute("DELETE FROM accessi_divisione WHERE utente_id=%s", (uid,))
        for dv in set(d.divisioni):
            conn.execute("INSERT INTO accessi_divisione (utente_id, divisione_id) VALUES (%s,%s)", (uid, dv))
    return {"ok": True}


class Attivo(BaseModel):
    attivo: bool


@gestione.put("/{uid}/attivo")
def attiva(uid: int, d: Attivo, t: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _altro_utente(conn, uid, t)
        conn.execute("UPDATE utenti SET attivo=%s, token_valido_dal=NOW() WHERE id=%s", (d.attivo, uid))
    return {"ok": True}


@gestione.post("/{uid}/reimposta")
def reimposta(uid: int, t: dict = Depends(solo_titolare)):
    """Password dimenticata o telefono perso: nuova password temporanea e secondo fattore da rifare."""
    temp = _password_temporanea()
    with connessione() as conn:
        _altro_utente(conn, uid, t)
        conn.execute("""UPDATE utenti SET password_hash=%s, deve_cambiare_password=TRUE, totp_attivo=FALSE, totp_segreto_cifrato=NULL,
                        totp_ultimo_passo=0, token_valido_dal=NOW() WHERE id=%s""", (cifra_password(temp), uid))
        conn.execute("DELETE FROM codici_recupero WHERE utente_id=%s", (uid,))
        conn.execute("DELETE FROM tentativi_accesso WHERE chiave=%s", (_impronta(conn.execute("SELECT email FROM utenti WHERE id=%s", (uid,)).fetchone()["email"]),))
    return {"password_temporanea": temp}
