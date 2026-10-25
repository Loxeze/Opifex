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
from .rotte_task import router as router_task
from .rotte_percorsi import router as router_percorsi
from .rotte_social import router as router_social
from .rotte_fornitori import router as router_fornitori
from .rotte_posta import router as router_posta
from .rotte_registro import router as router_registro
from .rotte_sistema import router as router_sistema
from .rotte_voce import router as router_voce
from .rotte_memoria import router as router_memoria
from .rotte_brevo import router as router_brevo
from . import etichetta
from .rotte_plaud import router as router_plaud
from .rotte_iniziative import router as router_iniziative
from .rotte_biblioteca import router as router_biblioteca
from .rotte_cerimoniere import router as router_cerimoniere
from .rotte_studi import router as router_studi
from .rotte_trigger import router as router_quando
from .rotte_dossier import router as router_dossier
from .rotte_crm import router as router_crm
from .rotte_voce_el import router as router_voce_el
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


async def _manutenzione():
    """Ogni 10 minuti: allarmi di funzionamento; una volta al giorno: backup cifrato. Gli errori non fermano il servizio."""
    import asyncio
    from . import allarmi, backup, plaud, prova_ripristino, sintesi_memoria, studio

    def giro():
        with connessione() as conn:
            if backup.da_fare(conn):
                backup.esegui(conn)
            allarmi.controlla(conn)
            if sintesi_memoria.da_fare(conn):
                sintesi_memoria.genera(conn)
            plaud.controlla(conn)
            if prova_ripristino.da_fare(conn):
                prova_ripristino.prova(conn)
            if studio.da_fare(conn):
                studio.rileva_e_segna(conn)
    await asyncio.sleep(90)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:
            pass
        await asyncio.sleep(600)


async def _trigger_orari():
    """Ogni minuto controlla i trigger a orario accesi e li avvia."""
    import asyncio
    from . import trigger

    def giro():
        with connessione() as conn:
            trigger.tick(conn)
    await asyncio.sleep(45)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:
            pass
        await asyncio.sleep(60)


@asynccontextmanager
async def ciclo_vita(app: FastAPI):
    import asyncio
    apri_pool()
    try:
        from . import percorsi
        percorsi.recupera_interrotti()
    except Exception:
        pass
    compiti = [asyncio.create_task(_controllo_aggiornamenti()), asyncio.create_task(_canale_telegram()), asyncio.create_task(_manutenzione()), asyncio.create_task(_trigger_orari())]
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
    risposta.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
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
app.include_router(router_task)
app.include_router(router_percorsi)
app.include_router(router_social)
app.include_router(router_fornitori)
app.include_router(router_posta)
app.include_router(router_registro)
app.include_router(router_sistema)
app.include_router(router_voce)
app.include_router(router_memoria)
app.include_router(router_brevo)
app.include_router(router_plaud)
app.include_router(router_iniziative)
app.include_router(router_biblioteca)
app.include_router(router_cerimoniere)
app.include_router(router_studi)
app.include_router(router_quando)
app.include_router(router_dossier)
app.include_router(router_crm)
app.include_router(router_voce_el)


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
                f"SELECT a.id, a.divisione_id, a.superiore_id, a.nome, a.ruolo, a.livello, a.tipo, a.modello, a.attivo, {etichetta.sql()} AS etichetta "
                "FROM agenti a ORDER BY a.id"
            ).fetchall()
        else:
            righe = conn.execute(
                f"SELECT a.id, a.divisione_id, a.superiore_id, a.nome, a.ruolo, a.livello, a.tipo, a.modello, a.attivo, {etichetta.sql()} AS etichetta "
                "FROM agenti a WHERE a.divisione_id = ANY(%s) ORDER BY a.id",
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
