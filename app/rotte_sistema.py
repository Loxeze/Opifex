"""Backup, tetto di spesa e allarmi: stato e comandi (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import allarmi, backup, cassaforte, registro, spesa
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/sistema")


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"backup": backup.stato(conn), "spesa": {"limiti": spesa.limiti(conn), "consumo": spesa.consumo(conn),
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
