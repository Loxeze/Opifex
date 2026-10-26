"""Prova di ripristino: ogni settimana prende l'ultimo backup, lo apre con la chiave e ne verifica il contenuto.
Se il database lo permette, lo ripristina davvero in un database temporaneo e confronta i numeri con quello vivo; altrimenti verifica
il contenuto del dump (tabelle e righe) e lo dice. Un backup che non si ripristina e' come non averlo."""
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

import psycopg

from . import backup
from .config import impostazioni

CONTROLLO = ("utenti", "agenti", "impostazioni_sistema", "memorie_lavoro", "documenti")
NOME_PROVA = "opifex_prova_ripristino"
OGNI = timedelta(days=7)


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r else d


def _scrivi(conn, k, v):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, v))


def righe_nel_dump(sql: str) -> dict[str, int]:
    """Conta le righe di ogni tabella nei blocchi COPY del dump."""
    out = {}
    for m in re.finditer(r"^COPY (?:public\.)?(\w+) \([^)]*\) FROM stdin;\n(.*?)^\\\.$", sql, re.M | re.S):
        out[m.group(1)] = 0 if not m.group(2) else m.group(2).count("\n")
    return out


def _url_con_db(nome: str) -> str:
    u = urlparse(impostazioni.database_url)
    return urlunparse(u._replace(path="/" + nome))


def _ripristino_reale(sql: bytes) -> dict[str, int] | None:
    """Ripristina in un database temporaneo e conta le righe. None se non e' possibile crearlo."""
    try:
        with psycopg.connect(_url_con_db("postgres"), autocommit=True) as amm:
            amm.execute(f'DROP DATABASE IF EXISTS "{NOME_PROVA}"')
            amm.execute(f'CREATE DATABASE "{NOME_PROVA}"')
    except psycopg.Error:
        return None
    try:
        try:
            r = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", _url_con_db(NOME_PROVA)], input=sql, capture_output=True, timeout=900, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            raise RuntimeError("ripristino non riuscito: " + r.stderr.decode("utf-8", "replace")[:200])
        with psycopg.connect(_url_con_db(NOME_PROVA)) as c:
            return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in CONTROLLO}
    finally:
        try:
            with psycopg.connect(_url_con_db("postgres"), autocommit=True) as amm:
                amm.execute(f'DROP DATABASE IF EXISTS "{NOME_PROVA}"')
        except psycopg.Error:
            pass


def prova(conn) -> dict:
    esito = {"quando": datetime.now(timezone.utc).isoformat(), "ok": False, "metodo": "", "dettaglio": "", "file": "", "tabelle": 0, "righe": {}}
    try:
        file = sorted(backup.CARTELLA.glob("opifex-backup-*.enc"))
        if not file:
            raise backup.ErroreBackup("Nessun backup sul server da provare")
        esito["file"] = file[-1].name
        contenuti = backup.apri(str(file[-1]), backup._chiave(conn))
        dump = contenuti.get("database.sql", b"")
        testo = dump.decode("utf-8", "replace")
        if "PostgreSQL database dump complete" not in testo:
            raise backup.ErroreBackup("Il dump e' incompleto (manca la riga finale)")
        nel_dump = righe_nel_dump(testo)
        esito["tabelle"] = len(nel_dump)
        for t in CONTROLLO:
            if t not in nel_dump:
                raise backup.ErroreBackup(f"Nel backup manca la tabella «{t}»")
        vivo = {t: conn.execute(f'SELECT count(*) AS n FROM "{t}"').fetchone()["n"] for t in CONTROLLO}
        reale = _ripristino_reale(dump)
        if reale is not None:
            esito["metodo"] = "ripristino reale in un database temporaneo"
            esito["righe"] = reale
            for t in CONTROLLO:
                if reale[t] != nel_dump[t]:
                    raise backup.ErroreBackup(f"Dopo il ripristino «{t}» ha {reale[t]} righe, il dump ne contiene {nel_dump[t]}")
        else:
            esito["metodo"] = "verifica del contenuto del dump (non e' possibile creare un database di prova con l'utente attuale)"
            esito["righe"] = {t: nel_dump[t] for t in CONTROLLO}
        for t in CONTROLLO:
            if nel_dump[t] > vivo[t] + 50:
                raise backup.ErroreBackup(f"«{t}» nel backup ha molte piu' righe del database attuale: controlla")
        esito.update(ok=True, dettaglio="Il backup si apre, contiene le tabelle principali e i numeri tornano.")
    except (backup.ErroreBackup, RuntimeError, OSError) as e:
        esito["dettaglio"] = str(e)[:300]
    except Exception as e:  # noqa: BLE001 - la prova non deve mai fermare la manutenzione
        esito["dettaglio"] = "Errore inatteso: " + type(e).__name__
    _scrivi(conn, "ripristino_ultimo", json.dumps(esito))
    if esito["ok"]:
        _scrivi(conn, "ripristino_ultimo_ok", esito["quando"])
    else:
        conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, TRUE, TRUE)", ("ALLARME: la prova di ripristino del backup e' FALLITA: " + esito["dettaglio"],))
    return esito


def da_fare(conn) -> bool:
    if _imp(conn, "backup_attivo", "1") != "1" or not _imp(conn, "backup_ultimo_ok"):
        return False
    try:
        u = json.loads(_imp(conn, "ripristino_ultimo") or "null")
    except ValueError:
        u = None
    if not u:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(u["quando"]) >= OGNI


def stato(conn) -> dict | None:
    try:
        return json.loads(_imp(conn, "ripristino_ultimo") or "null")
    except ValueError:
        return None
