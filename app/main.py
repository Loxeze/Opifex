"""Punto di ingresso dell'API della piattaforma agenti AI."""
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import impostazioni
from .db import apri_pool, chiudi_pool, connessione
from .permessi import divisioni_visibili, solo_titolare, utente_corrente
from .rotte_agenti import router as router_agenti
from .rotte_briefing import router as router_briefing
from .rotte_accessi import router as router_accessi
from .rotte_progetti import router as router_progetti
from .rotte_utenti import router as router_utenti, gestione as gestione_utenti
from .rotte_dialoghi import router as router_dialoghi
from .rotte_richieste import router as router_richieste
from .rotte_organizzazione import router as router_organizzazione
from .rotte_aggiornamenti import router as router_aggiornamenti
from .rotte_canali import router as router_canali
from .rotte_documenti import router as router_documenti
from .rotte_gestione import router as router_gestione
from .sicurezza import HASH_FINTO, cifra_password, crea_token, verifica_password


async def _controllo_aggiornamenti():
    """Ogni 6 ore cerca nuove versioni (in silenzio: gli errori non fermano il servizio)."""
    import asyncio
    from . import aggiornamenti

    def giro():
        with connessione() as conn:
            aggiornamenti.controllo_periodico(conn)
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:
            pass
        await asyncio.sleep(6 * 3600)


async def _canale_telegram():
    """Ascolta Telegram (se configurato). Gli errori non fermano il servizio: si riprova."""
    import asyncio
    from . import telegram
    while True:
        try:
            attivo = await asyncio.to_thread(telegram.giro, 20)
            await asyncio.sleep(1 if attivo else 15)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(15)


@asynccontextmanager
async def ciclo_vita(app: FastAPI):
    import asyncio
    apri_pool()
    compiti = [asyncio.create_task(_controllo_aggiornamenti()), asyncio.create_task(_canale_telegram())]
    yield
    for c in compiti:
        c.cancel()
    chiudi_pool()


app = FastAPI(title="Piattaforma agenti AI", lifespan=ciclo_vita)
app.add_middleware(
    CORSMiddleware,
    allow_origins=impostazioni.origini,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def intestazioni_sicure(richiesta, call_next):
    risposta = await call_next(richiesta)
    risposta.headers["X-Frame-Options"] = "DENY"
    risposta.headers["X-Content-Type-Options"] = "nosniff"
    risposta.headers["Referrer-Policy"] = "no-referrer"
    return risposta


app.include_router(router_agenti)
app.include_router(router_briefing)
app.include_router(router_gestione)
app.include_router(router_documenti)
app.include_router(router_accessi)
app.include_router(router_utenti)
app.include_router(router_progetti)
app.include_router(gestione_utenti)
app.include_router(router_dialoghi)
app.include_router(router_richieste)
app.include_router(router_organizzazione)
app.include_router(router_aggiornamenti)
app.include_router(router_canali)


@app.get("/", include_in_schema=False)
def inizio():
    return RedirectResponse("/app/")


# Interfaccia web (pagine statiche): tutto il resto passa dall'API con il token di accesso
app.mount("/app", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="interfaccia")


class DatiLogin(BaseModel):
    email: str
    password: str


class NuovoUtente(BaseModel):
    nome: str
    email: str
    password: str
    ruolo_globale: str = "collaboratore"


@app.get("/salute")
def salute():
    """Controllo rapido: il server e il database rispondono."""
    with connessione() as conn:
        conn.execute("SELECT 1")
    from .versione import versione_corrente
    return {"stato": "ok", "versione": versione_corrente()}


@app.get("/io")
def profilo(utente: dict = Depends(utente_corrente)):
    return utente


@app.post("/utenti", status_code=201)
def crea_utente(nuovo: NuovoUtente, _: dict = Depends(solo_titolare)):
    """Solo il titolare crea i profili dei collaboratori."""
    if nuovo.ruolo_globale not in ("titolare", "collaboratore"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ruolo non valido")
    if len(nuovo.password) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password troppo corta (minimo 10 caratteri)")
    with connessione() as conn:
        esistente = conn.execute("SELECT 1 FROM utenti WHERE email = %s", (nuovo.email.strip().lower(),)).fetchone()
        if esistente:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email gia' registrata")
        riga = conn.execute(
            "INSERT INTO utenti (nome, email, password_hash, ruolo_globale) VALUES (%s, %s, %s, %s) RETURNING id",
            (nuovo.nome, nuovo.email.strip().lower(), cifra_password(nuovo.password), nuovo.ruolo_globale),
        ).fetchone()
    return {"id": riga["id"]}


@app.get("/agenti")
def elenco_agenti(utente: dict = Depends(utente_corrente)):
    """Il titolare vede tutti gli agenti (anche di sistema); i collaboratori solo le proprie divisioni."""
    visibili = divisioni_visibili(utente)
    with connessione() as conn:
        if visibili is None:
            righe = conn.execute(
                "SELECT id, divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, attivo "
                "FROM agenti ORDER BY id"
            ).fetchall()
        else:
            righe = conn.execute(
                "SELECT id, divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, attivo "
                "FROM agenti WHERE divisione_id = ANY(%s) ORDER BY id",
                (visibili,),
            ).fetchall()
    return righe


@app.get("/divisioni")
def elenco_divisioni(utente: dict = Depends(utente_corrente)):
    visibili = divisioni_visibili(utente)
    with connessione() as conn:
        if visibili is None:
            return conn.execute("SELECT id, nome, descrizione, attiva FROM divisioni ORDER BY id").fetchall()
        return conn.execute(
            "SELECT id, nome, descrizione, attiva FROM divisioni WHERE id = ANY(%s) ORDER BY id",
            (visibili,),
        ).fetchall()
