"""Backup cifrato giornaliero: database + file .env (che contiene la chiave della cassaforte), in una cartella del server e su Drive.
L'archivio e' cifrato con una chiave di backup che Lorenzo conserva: senza quella chiave il file non si apre, nemmeno dal server."""
import gzip
import io
import json
import os
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import cassaforte, google
from .config import impostazioni

CARTELLA = Path(os.environ.get("BACKUP_DIR", "/opt/agenti/backup"))
FILE_ENV = Path(os.environ.get("ENV_FILE", "/opt/agenti/.env"))
CONSERVA = 14


class ErroreBackup(Exception):
    pass


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r else d


def _scrivi(conn, k, v):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, v))


def crea_chiave(conn, rigenera: bool = False) -> str:
    """Genera la chiave di backup. Si mostra UNA volta sola: Lorenzo la conserva fuori dal server."""
    if _imp(conn, "backup_chiave_cifrata") and not rigenera:
        raise ErroreBackup("La chiave di backup esiste gia'. Rigenerarla rende illeggibili i backup vecchi se non hai la vecchia chiave.")
    k = Fernet.generate_key().decode()
    _scrivi(conn, "backup_chiave_cifrata", cassaforte.cifra(k))
    return k


def _chiave(conn) -> str:
    v = _imp(conn, "backup_chiave_cifrata")
    if not v:
        raise ErroreBackup("Chiave di backup non ancora creata")
    return cassaforte.decifra(v)


def _dump() -> bytes:
    url = impostazioni.database_url
    try:
        r = subprocess.run(["pg_dump", "--no-owner", "--clean", "--if-exists", url], capture_output=True, timeout=600, check=False)
    except FileNotFoundError:
        raise ErroreBackup("pg_dump non e' installato sul server") from None
    except subprocess.TimeoutExpired:
        raise ErroreBackup("pg_dump troppo lento (oltre 10 minuti)") from None
    if r.returncode != 0:
        raise ErroreBackup("pg_dump non riuscito: " + r.stderr.decode("utf-8", "replace")[:200])
    return r.stdout


def costruisci(conn) -> tuple[bytes, str]:
    """Ritorna (contenuto cifrato, nome file)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        def aggiungi(nome, dati):
            i = tarfile.TarInfo(nome); i.size = len(dati); i.mtime = int(datetime.now().timestamp()); i.mode = 0o600
            t.addfile(i, io.BytesIO(dati))
        aggiungi("database.sql", _dump())
        try:
            aggiungi("env.txt", FILE_ENV.read_bytes())
        except OSError:
            aggiungi("env.txt", b"# file .env non leggibile dal servizio: copialo a mano\n")
    cifrato = Fernet(_chiave(conn).encode()).encrypt(buf.getvalue())
    return cifrato, "opifex-backup-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".enc"


def _potatura():
    file = sorted(CARTELLA.glob("opifex-backup-*.enc"))
    for f in file[:-CONSERVA]:
        try: f.unlink()
        except OSError: pass


def _su_drive(conn, dati: bytes, nome: str) -> str:
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        return "Drive non collegato: backup solo sul server"
    tok = google.token_accesso(conn, account)
    radice = google.radice_valida(conn, tok)
    cart = google.cartella(tok, "Backup", radice)
    limite = "opifexbackup"
    meta = json.dumps({"name": nome, "parents": [cart]}).encode()
    corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n").encode() + meta + \
            (f"\r\n--{limite}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + dati + f"\r\n--{limite}--".encode()
    google._http("POST", "https://www.googleapis.com/upload/drive/v3/files", params={"uploadType": "multipart", "fields": "id"},
                 headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/related; boundary={limite}"}, content=corpo)
    return "caricato su Drive"


def esegui(conn) -> dict:
    """Backup completo: cifra, salva sul server, carica su Drive. Registra l'esito (anche l'errore) per lo stato e gli allarmi."""
    esito = {"quando": datetime.now(timezone.utc).isoformat(), "ok": False, "dettaglio": "", "dimensione": 0, "drive": ""}
    try:
        dati, nome = costruisci(conn)
        CARTELLA.mkdir(parents=True, exist_ok=True)
        (CARTELLA / nome).write_bytes(dati)
        os.chmod(CARTELLA / nome, 0o600)
        _potatura()
        esito.update(ok=True, dimensione=len(dati), dettaglio=nome)
        try:
            esito["drive"] = _su_drive(conn, dati, nome)
        except google.ErroreGoogle as e:
            esito["drive"] = "Drive non raggiunto: " + str(e)[:150]
    except (ErroreBackup, cassaforte.CassaforteNonConfigurata, OSError) as e:
        esito["dettaglio"] = str(e)[:300]
    _scrivi(conn, "backup_ultimo", json.dumps(esito))
    if esito["ok"]:
        _scrivi(conn, "backup_ultimo_ok", esito["quando"])
    return esito


def stato(conn) -> dict:
    try:
        ultimo = json.loads(_imp(conn, "backup_ultimo") or "null")
    except ValueError:
        ultimo = None
    try:
        locali = [{"nome": f.name, "dimensione": f.stat().st_size} for f in sorted(CARTELLA.glob("opifex-backup-*.enc"), reverse=True)]
    except OSError:
        locali = []
    return {"attivo": _imp(conn, "backup_attivo", "1") == "1", "chiave_creata": bool(_imp(conn, "backup_chiave_cifrata")),
            "ultimo": ultimo, "locali": locali, "conserva": CONSERVA, "cartella": str(CARTELLA)}


def da_fare(conn) -> bool:
    """Vero se il backup e' attivo, la chiave esiste e l'ultimo riuscito ha piu' di 24 ore."""
    if _imp(conn, "backup_attivo", "1") != "1" or not _imp(conn, "backup_chiave_cifrata"):
        return False
    ora = datetime.now(timezone.utc)
    try:   # dopo un tentativo fallito si riprova al massimo ogni 2 ore
        t = json.loads(_imp(conn, "backup_ultimo") or "null")
        if t and not t.get("ok") and ora - datetime.fromisoformat(t["quando"]) < timedelta(hours=2):
            return False
    except (ValueError, KeyError):
        pass
    u = _imp(conn, "backup_ultimo_ok")
    if not u:
        return True
    return ora - datetime.fromisoformat(u) >= timedelta(hours=24)


def apri(percorso: str, chiave: str) -> dict[str, bytes]:
    """Per il ripristino: decifra un file di backup e restituisce {nome: contenuto}."""
    try:
        grezzo = Fernet(chiave.encode()).decrypt(Path(percorso).read_bytes())
    except (InvalidToken, ValueError):
        raise ErroreBackup("Chiave di backup errata o file danneggiato") from None
    out = {}
    with tarfile.open(fileobj=io.BytesIO(grezzo), mode="r:gz") as t:
        for m in t.getmembers():
            if m.isfile() and m.name in ("database.sql", "env.txt"):
                out[m.name] = t.extractfile(m).read()
    return out
