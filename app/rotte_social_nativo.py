"""Sezione Canali social nativi: collegamento delle reti (OAuth), pubblicazione diretta, risultati e analisi. Solo il titolare."""
import json
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from . import registro, social_nativo as sn
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/social-nativo", tags=["social"])


def _err(e: Exception, codice: int = status.HTTP_409_CONFLICT):
    return HTTPException(codice, str(e))


@router.get("/stato")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        esito = sn._leggi(conn, "sn_ultimo_esito")
        if esito:
            sn._scrivi(conn, "sn_ultimo_esito", "")
        provider = []
        for p, et in sn.ETICHETTE_PROVIDER.items():
            acc = conn.execute("SELECT id, nome, scade_il, ultimo_errore, extra FROM account_social WHERE provider=%s ORDER BY id", (p,)).fetchall()
            for a in acc:
                a["canali"] = conn.execute("SELECT id, rete, nome, attivo, ultimo_errore FROM canali_nativi WHERE account_id=%s ORDER BY rete, nome", (a["id"],)).fetchall()
            provider.append({"provider": p, "etichetta": et, "client_id": sn._leggi(conn, f"sn_{p}_id"), "segreto_salvato": bool(sn._leggi(conn, f"sn_{p}_secret_cifrato")),
                             "redirect": sn.redirect_uri(conn, p), "account": acc})
        return {"provider": provider, "esito": esito or None, "redirect_base": sn._leggi(conn, "sn_redirect_base"), "ultima_raccolta": sn._leggi(conn, "sn_ultima_raccolta") or None,
                "versione_graph": sn._leggi(conn, "sn_graph_versione")}


class App(BaseModel):
    client_id: str = Field(min_length=3, max_length=300)
    segreto: str | None = Field(default=None, max_length=500)    # mai restituito
    origine: str = Field(min_length=8, max_length=200)           # es. https://app.opifex.space


@router.put("/app/{provider}")
def salva_app(provider: str, d: App, utente: dict = Depends(solo_titolare)):
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(:\d+)?", d.origine.rstrip("/")) and not d.origine.startswith("http://localhost"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'indirizzo del sito deve essere del tipo https://app.tuodominio.it")
    with connessione() as conn:
        try:
            sn.imposta_app(conn, provider, d.client_id, d.segreto, d.origine)
        except (sn.ErroreSocial, Exception) as e:
            if isinstance(e, sn.ErroreSocial):
                raise _err(e, status.HTTP_422_UNPROCESSABLE_ENTITY)
            from . import cassaforte
            if isinstance(e, cassaforte.CassaforteNonConfigurata):
                raise _err(e, status.HTTP_503_SERVICE_UNAVAILABLE)
            raise
        registro.registra(conn, utente, "collegamento", "credenziali app social salvate", sn.ETICHETTE_PROVIDER[provider], "social_app", provider)
        return {"redirect": sn.redirect_uri(conn, provider)}


class Collega(BaseModel):
    pagine: bool = False


@router.post("/collega/{provider}")
def collega(provider: str, d: Collega, _: dict = Depends(solo_titolare)):
    if provider not in sn.ETICHETTE_PROVIDER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rete sconosciuta")
    with connessione() as conn:
        try:
            return {"url": sn.url_autorizzazione(conn, provider, {"pagine": d.pagine})}
        except sn.ErroreSocial as e:
            raise _err(e)


@router.get("/callback/{provider}", include_in_schema=False)
def ritorno(provider: str, code: str | None = Query(default=None, max_length=2000), state: str | None = Query(default=None, max_length=200),
            error: str | None = Query(default=None, max_length=200)):
    """Pagina aperta dalla rete dopo il consenso: vale lo stato monouso creato dal titolare."""
    if provider not in sn.ETICHETTE_PROVIDER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rete sconosciuta")
    with connessione() as conn:
        if error or not code or not state:
            sn._scrivi(conn, "sn_ultimo_esito", f"Collegamento a {sn.ETICHETTE_PROVIDER[provider]} annullato o rifiutato.")
        else:
            try:
                r = sn.completa_autorizzazione(conn, provider, code, state)
                sn._scrivi(conn, "sn_ultimo_esito", f"ok:{sn.ETICHETTE_PROVIDER[provider]}: collegati {r['canali']} canali.")
            except sn.ErroreSocial as e:
                conn.rollback()
                sn._scrivi(conn, "sn_ultimo_esito", f"{sn.ETICHETTE_PROVIDER[provider]}: {e}")
    return RedirectResponse("/app/", status_code=303)


@router.delete("/account/{aid}")
def scollega(aid: int, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        a = conn.execute("SELECT provider, nome FROM account_social WHERE id=%s", (aid,)).fetchone()
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account inesistente")
        sn.scollega_account(conn, aid)
        registro.registra(conn, utente, "collegamento", "account social scollegato", f"{a['nome']} ({a['provider']})", "account_social", aid)
    return {"ok": True}


class Pagina(BaseModel):
    org_id: str = Field(min_length=1, max_length=30)
    nome: str = Field(default="", max_length=100)


@router.post("/account/{aid}/pagina-linkedin")
def pagina_linkedin(aid: int, d: Pagina, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"canale": sn.aggiungi_pagina_linkedin(conn, aid, d.org_id, d.nome)}
        except sn.ErroreSocial as e:
            raise _err(e, status.HTTP_422_UNPROCESSABLE_ENTITY)


class Attivo(BaseModel):
    attivo: bool


@router.put("/canale/{cid}")
def canale_attivo(cid: int, d: Attivo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE canali_nativi SET attivo=%s WHERE id=%s", (d.attivo, cid))
    return {"ok": True}


# ---------- post scritti da Lorenzo ----------
class NuovoPost(BaseModel):
    canali: list[str] = Field(min_length=1, max_length=20)
    testo: str = Field(default="", max_length=5000)
    media: list[dict] = []
    programmato_il: datetime | None = None   # vuoto = subito


@router.post("/post")
def nuovo_post(d: NuovoPost, utente: dict = Depends(solo_titolare)):
    """Lorenzo scrive e decide lui: il post va direttamente in pubblicazione (subito o all'orario scelto)."""
    if d.programmato_il is not None and d.programmato_il.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica anche il fuso orario")
    if d.programmato_il is not None and d.programmato_il <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'orario scelto e' gia' passato")
    ids = []
    with connessione() as conn:
        righe = []
        for cid in d.canali:
            n = sn.id_canale(cid)
            c = conn.execute("SELECT id, rete, nome FROM canali_nativi WHERE id=%s AND attivo", (n,)).fetchone() if n else None
            if c is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Canale non trovato o non collegato")
            try:
                sn.verifica_post(c["rete"], d.testo, d.media)
            except sn.ErroreSocial as e:
                raise _err(e, status.HTTP_422_UNPROCESSABLE_ENTITY)   # nessun post parte se uno dei canali non e' valido
            righe.append(c)
        media = json.dumps(sn._media(d.media, ""))
        for c in righe:
            pid = conn.execute("""INSERT INTO post_social (canale_id, canale_nome, servizio, testo, media, programmato_il, stato, approvato_da_utente_id)
                                  VALUES (%s,%s,%s,%s,%s::jsonb,%s,'programmato',%s) RETURNING id""",
                               (f"n:{c['id']}", c["nome"], c["rete"], d.testo, media, d.programmato_il, utente["id"])).fetchone()["id"]
            ids.append(pid)
        registro.registra(conn, utente, "post_social", "scritto da Lorenzo, in pubblicazione", d.testo[:200], "post_social", ids[0], "", {"canali": len(ids)})
        conn.commit()
    if d.programmato_il is None:
        for pid in ids:
            sn.avvia_pubblicazione(pid)
    return {"post": ids}


# ---------- file da pubblicare ----------
@router.post("/media")
async def carica_media(request: Request, file: UploadFile = File(...), _: dict = Depends(solo_titolare)):
    """Carica una foto o un video da pubblicare: le reti li scaricano da un indirizzo pubblico (casuale, non indovinabile) che dura 45 giorni."""
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", (file.filename or "file"))[:80] or "file"
    if not re.search(r"\.(jpe?g|png|webp|mp4|mov|m4v)$", nome, re.I):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sono ammessi JPG, PNG, WEBP, MP4 e MOV")
    tok = secrets.token_urlsafe(16)
    d = sn.cartella_media() / tok
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(d / nome, "wb") as f:
        while blocco := await file.read(1024 * 1024):
            n += len(blocco)
            if n > sn.MAX_VIDEO:
                f.close()
                import shutil
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File troppo grande (massimo 1 GB)")
            f.write(blocco)
    with connessione() as conn:
        base = sn._leggi(conn, "sn_redirect_base") or str(request.base_url).rstrip("/")
    return {"url": f"{base}/gestione/social-nativo/media/{tok}/{nome}", "tipo": "video" if re.search(r"\.(mp4|mov|m4v)$", nome, re.I) else "image", "byte": n}


@router.get("/media/{tok}/{nome}", include_in_schema=False)
def servi_media(tok: str, nome: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,32}", tok) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", nome):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Non trovato")
    p = sn.cartella_media() / tok / nome
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Non trovato")
    return FileResponse(p)


# ---------- risultati ----------
@router.get("/analisi")
def analisi(giorni: int = Query(default=30, ge=1, le=365), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return sn.analisi(conn, giorni)


@router.get("/analisi.csv")
def analisi_csv(giorni: int = Query(default=90, ge=1, le=365), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        corpo = sn.esporta_csv(conn, giorni)
    return Response(corpo, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="risultati_social.csv"'})


@router.post("/raccogli")
def raccogli_ora(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return sn.raccogli(conn, forza=True)
