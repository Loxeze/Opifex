"""Backup, tetto di spesa e allarmi: stato e comandi (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import allarmi, backup, cassaforte, prova_ripristino, registro, spesa, versione
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/sistema")


MINIMA_POSTGRES = 12   # colonne generate per la ricerca testuale (documenti, memoria di lavoro, dossier)


def info_database(conn) -> dict:
    """Versione di PostgreSQL, nome e peso del database, migrazioni applicate. Solo lettura, nessun dato degli utenti."""
    out: dict = {"versione_app": versione.versione_corrente(), "minima": MINIMA_POSTGRES}
    try:
        v = conn.execute("SHOW server_version").fetchone()
        num = int(conn.execute("SHOW server_version_num").fetchone()["server_version_num"])
        out["postgres"] = v["server_version"]
        out["postgres_numero"] = num
        out["compatibile"] = num // 10000 >= MINIMA_POSTGRES
        out["nome"] = conn.execute("SELECT current_database() AS n").fetchone()["n"]
        out["dimensione"] = int(conn.execute("SELECT pg_database_size(current_database()) AS d").fetchone()["d"])
        out["tabelle"] = int(conn.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = 'public'").fetchone()["n"])
    except Exception as e:   # noqa: BLE001 - e' una pagina informativa: non deve mai rompere lo stato del sistema
        out["errore"] = type(e).__name__
        return out
    if conn.execute("SELECT to_regclass('public.schema_migrazioni') AS t").fetchone()["t"] is None:
        out["migrazioni"] = None   # la tabella la crea lo script di aggiornamento: puo' mancare in un'installazione di sviluppo
    else:
        r = conn.execute("SELECT count(*) AS n, max(nome) AS ultima, max(applicata_il) AS quando FROM schema_migrazioni").fetchone()
        out["migrazioni"] = {"applicate": int(r["n"]), "ultima": r["ultima"], "quando": r["quando"].isoformat(timespec="minutes") if r["quando"] else None}
    return out


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"database": info_database(conn), "backup": {**backup.stato(conn), "ripristino": prova_ripristino.stato(conn)}, "spesa": {"limiti": spesa.limiti(conn), "consumo": spesa.consumo(conn),
                                                        "modelli_senza_prezzo": spesa.modelli_senza_prezzo(conn)}}


class Tetti(BaseModel):
    giorno: float | None = Field(default=None, ge=0, le=1_000_000)
    mese: float | None = Field(default=None, ge=0, le=10_000_000)


@router.put("/spesa")
def tetti(d: Tetti, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        for k, v in (("tetto_spesa_giorno", d.giorno), ("tetto_spesa_mese", d.mese)):
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore",
                         (k, str(v or 0)))
        registro.registra(conn, u, "tetto_spesa", "impostato", "Tetto di spesa", dettagli={"giorno": d.giorno, "mese": d.mese})
    return {"stato": "ok"}


@router.post("/backup/chiave", status_code=201)
def chiave_backup(rigenera: bool = False, u: dict = Depends(solo_titolare)):
    """Crea la chiave di backup e la mostra UNA volta: va conservata fuori dal server."""
    with connessione() as conn:
        try:
            k = backup.crea_chiave(conn, rigenera)
        except backup.ErroreBackup as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        registro.registra(conn, u, "backup", "chiave di backup " + ("rigenerata" if rigenera else "creata"), "Backup", "backup", "chiave")
    return {"chiave": k}


class Attivo(BaseModel):
    attivo: bool


@router.put("/backup")
def attiva(d: Attivo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('backup_attivo',%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", ("1" if d.attivo else "0",))
    return {"stato": "ok"}


@router.post("/backup/prova-ripristino")
def prova_del_ripristino(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        e = prova_ripristino.prova(conn)
        registro.registra(conn, u, "backup", "prova di ripristino riuscita" if e["ok"] else "prova di ripristino fallita", "Backup", "backup", "prova", e["dettaglio"])
    return e


@router.post("/backup/ora")
def ora(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        e = backup.esegui(conn)
        registro.registra(conn, u, "backup", "eseguito a mano" if e["ok"] else "tentato a mano: errore", "Backup", "backup", "manuale")
    return e


@router.post("/allarmi/prova")
def prova_allarmi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"inviati": allarmi.controlla(conn)}


# ---------- Ore di silenzio (1.24.3) ----------
import re as _re  # noqa: E402

from . import silenzio  # noqa: E402


@router.get("/silenzio")
def leggi_silenzio(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {**silenzio.impostazioni(conn), "adesso_in_silenzio": silenzio.in_silenzio(conn)}


class Silenzio(BaseModel):
    attivo: bool
    da: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    a: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.put("/silenzio")
def imposta_silenzio(d: Silenzio, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        for k, v in (("silenzio_attivo", "true" if d.attivo else "false"), ("silenzio_da", d.da), ("silenzio_a", d.a)):
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))
        return {**silenzio.impostazioni(conn), "adesso_in_silenzio": silenzio.in_silenzio(conn)}
