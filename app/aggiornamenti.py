"""Aggiornamenti dell'applicazione da un repository GitHub privato.

L'app (utente senza privilegi) controlla le release, scarica il pacchetto, ne verifica l'impronta SHA-256 e
deposita una richiesta. L'installazione vera la fa lo script di root /usr/local/sbin/opifex-aggiorna
(backup del database, verifica, riavvio, ritorno indietro in caso di problemi).
Il token GitHub e' cifrato nella cassaforte e non viene mai mostrato ne' mandato a un agente.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import cassaforte
from .versione import come_numeri, versione_corrente

API = "https://api.github.com"
REPO_OK = re.compile(r"^[A-Za-z0-9_.-]{1,60}/[A-Za-z0-9_.-]{1,100}$")
MAX_BYTE = 200 * 1024 * 1024


class ErroreAggiornamento(Exception):
    pass


def cartella() -> Path:
    return Path(os.environ.get("OPIFEX_DIR", Path(__file__).resolve().parent.parent)) / "aggiornamenti"


def _leggi(conn, chiave: str, default: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else default


def _scrivi(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) "
                 "ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def salva_configurazione(conn, repo: str | None, token: str | None, automatico: str | None):
    if repo is not None:
        repo = repo.strip()
        if repo and not REPO_OK.match(repo):
            raise ErroreAggiornamento("Il repository va scritto come proprietario/nome, ad esempio Loxeze/Opifex")
        _scrivi(conn, "github_repo", repo)
    if token:
        _scrivi(conn, "github_token", cassaforte.cifra(token.strip()))
    if automatico is not None:
        if automatico not in ("no", "patch"):
            raise ErroreAggiornamento("Valore non valido per l'aggiornamento automatico")
        _scrivi(conn, "aggiornamento_automatico", automatico)


def _token(conn) -> str:
    c = _leggi(conn, "github_token")
    return cassaforte.decifra(c) if c else ""


def _intestazioni(token: str, accetta: str = "application/vnd.github+json") -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": accetta, "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "opifex-aggiornamenti"}


def ultima_release(repo: str, token: str) -> dict | None:
    try:
        r = httpx.get(f"{API}/repos/{repo}/releases/latest", headers=_intestazioni(token), timeout=30)
    except httpx.HTTPError as e:
        raise ErroreAggiornamento("GitHub non raggiungibile: " + type(e).__name__)
    if r.status_code == 404:
        return None  # nessuna release ancora (o repository/token non corretti)
    if r.status_code in (401, 403):
        raise ErroreAggiornamento("GitHub ha rifiutato il token: controlla che sia valido e abbia accesso in lettura al repository")
    if r.status_code != 200:
        raise ErroreAggiornamento(f"GitHub ha risposto {r.status_code}")
    d = r.json()
    ver = str(d.get("tag_name", "")).lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        raise ErroreAggiornamento("La release piu' recente non ha un numero di versione valido (es. v0.9.1)")
    return {"versione": ver, "note": str(d.get("body") or "")[:2000],
            "asset": {a["name"]: a["url"] for a in d.get("assets", []) if "name" in a and "url" in a}}


def stato(conn) -> dict:
    esito = None
    try:
        esito = json.loads((cartella() / "esito.json").read_text())
    except (OSError, ValueError):
        pass
    repo = _leggi(conn, "github_repo")
    return {
        "versione": versione_corrente(),
        "repo": repo,
        "token_presente": bool(_leggi(conn, "github_token")),
        "automatico": _leggi(conn, "aggiornamento_automatico", "no"),
        "ultima_verifica": _leggi(conn, "aggiornamento_ultima_verifica") or None,
        "disponibile": _leggi(conn, "aggiornamento_disponibile") or None,
        "note": _leggi(conn, "aggiornamento_note") or None,
        "esito": esito,
        "storico": conn.execute(
            "SELECT versione, esito, dettagli, creato_il FROM aggiornamenti_registro ORDER BY id DESC LIMIT 10").fetchall(),
    }


def controlla(conn) -> dict:
    repo, token = _leggi(conn, "github_repo"), _token(conn)
    if not repo or not token:
        raise ErroreAggiornamento("Prima inserisci repository e token GitHub")
    rel = ultima_release(repo, token)
    _scrivi(conn, "aggiornamento_ultima_verifica", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    nuova = rel is not None and come_numeri(rel["versione"]) > come_numeri(versione_corrente())
    if nuova:
        if _leggi(conn, "aggiornamento_disponibile") != rel["versione"]:
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Opifex: disponibile l'aggiornamento {rel['versione']} (installata la {versione_corrente()}).",))
        _scrivi(conn, "aggiornamento_disponibile", rel["versione"])
        _scrivi(conn, "aggiornamento_note", rel["note"])
    else:
        _scrivi(conn, "aggiornamento_disponibile", "")
        _scrivi(conn, "aggiornamento_note", "")
    return stato(conn)


def _scarica(url: str, token: str, destinazione: Path) -> str:
    """Scarica un asset (anche privato) e restituisce l'impronta SHA-256."""
    h = hashlib.sha256()
    try:
        with httpx.stream("GET", url, headers=_intestazioni(token, "application/octet-stream"),
                          follow_redirects=True, timeout=120) as r:
            if r.status_code != 200:
                raise ErroreAggiornamento(f"Download non riuscito (GitHub {r.status_code})")
            tot = 0
            with open(destinazione, "wb") as f:
                for blocco in r.iter_bytes(1 << 16):
                    tot += len(blocco)
                    if tot > MAX_BYTE:
                        raise ErroreAggiornamento("Il pacchetto e' troppo grande")
                    h.update(blocco); f.write(blocco)
    except httpx.HTTPError as e:
        raise ErroreAggiornamento("Download interrotto: " + type(e).__name__)
    return h.hexdigest()


def prepara_installazione(conn, utente_id: int | None = None) -> str:
    """Scarica la release piu' recente, verifica l'impronta e deposita la richiesta per lo script di root."""
    repo, token = _leggi(conn, "github_repo"), _token(conn)
    if not repo or not token:
        raise ErroreAggiornamento("Prima inserisci repository e token GitHub")
    rel = ultima_release(repo, token)
    if rel is None or come_numeri(rel["versione"]) <= come_numeri(versione_corrente()):
        raise ErroreAggiornamento("Non ci sono aggiornamenti piu' recenti di quello installato")
    ver = rel["versione"]
    nome, nome_h = f"opifex-{ver}.tgz", f"opifex-{ver}.tgz.sha256"
    if nome not in rel["asset"] or nome_h not in rel["asset"]:
        raise ErroreAggiornamento(f"La release non contiene i file {nome} e {nome_h}")
    cart = cartella(); cart.mkdir(parents=True, exist_ok=True)
    if (cart / "richiesta").exists():
        raise ErroreAggiornamento("C'e' gia' un aggiornamento in corso")
    tmp = cart / "scarico.tmp"
    atteso_h = cart / "scarico-impronta.tmp"
    try:
        reale = _scarica(rel["asset"][nome], token, tmp)
        _scarica(rel["asset"][nome_h], token, atteso_h)
        atteso = (atteso_h.read_text().split() or [""])[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", atteso) or atteso != reale:
            raise ErroreAggiornamento("L'impronta del pacchetto scaricato non corrisponde: aggiornamento annullato")
        os.replace(tmp, cart / "pacchetto.tgz")
        (cart / "pacchetto.sha256").write_text(f"{reale}  pacchetto.tgz\n")
        (cart / "richiesta").write_text(ver)   # ultimo: fa partire lo script di root
    finally:
        for p in (tmp, atteso_h):
            try: p.unlink()
            except OSError: pass
    conn.execute("INSERT INTO aggiornamenti_registro (versione, esito, dettagli) VALUES (%s,'richiesto',%s)",
                 (ver, f"Richiesto dall'utente {utente_id}" if utente_id else "Richiesto automaticamente"))
    return ver


def controllo_periodico(conn):
    """Chiamato ogni poche ore: verifica e, solo se l'utente l'ha scelto, installa le correzioni (stessa X.Y)."""
    if not (_leggi(conn, "github_repo") and _leggi(conn, "github_token")):
        return
    s = controlla(conn)
    if s["disponibile"] and _leggi(conn, "aggiornamento_automatico", "no") == "patch":
        a, b = come_numeri(versione_corrente()), come_numeri(s["disponibile"])
        if a[:2] == b[:2]:
            prepara_installazione(conn, None)
