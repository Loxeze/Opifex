"""Avatar degli agenti: opere antiche di pubblico dominio cercate su Wikimedia Commons.
Lorenzo vede le candidate (con autore, opera, licenza e fonte) e sceglie; il server riscarica l'anteprima da upload.wikimedia.org, mai da un indirizzo
fornito dal browser. Cornice e medaglie crescono con la formazione: sono derivate dai livelli delle competenze, non scelte a mano."""
import html
import re
from urllib.parse import urlparse

from . import casati, ginnasio

API = "https://commons.wikimedia.org/w/api.php"
HOST_IMMAGINI = "upload.wikimedia.org"
LARGHEZZA = 400
MAX_BYTE = 700_000
MIME_OK = ("image/jpeg", "image/png", "image/webp")
CORNICI = {0: "nessuna", 1: "bronzo", 2: "argento", 3: "oro", 4: "platino", 5: "alloro"}
MEDAGLIE = {1: "🥉", 2: "🥈", 3: "🥇", 4: "💎", 5: "👑"}


class ErroreAvatar(Exception):
    pass


def _testo(v) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(str(v or "")))
    return re.sub(r"\s+", " ", t).strip()[:300]


def _pubblico_dominio(licenza: str) -> bool:
    l = (licenza or "").lower()
    return "public domain" in l or l.startswith("pd") or l.startswith("cc0") or "pubblico dominio" in l


def _candidata(p: dict) -> dict | None:
    ii = (p.get("imageinfo") or [None])[0]
    if not ii:
        return None
    meta = ii.get("extmetadata") or {}
    lic = _testo((meta.get("LicenseShortName") or {}).get("value"))
    if not _pubblico_dominio(lic) or ii.get("mime") not in MIME_OK:
        return None
    thumb = ii.get("thumburl") or ""
    if urlparse(thumb).hostname != HOST_IMMAGINI:
        return None
    titolo = p.get("title", "")
    return {"file": titolo, "anteprima": thumb, "opera": _testo((meta.get("ObjectName") or {}).get("value")) or titolo.replace("File:", "").rsplit(".", 1)[0],
            "autore": _testo((meta.get("Artist") or {}).get("value")) or "Autore non indicato (opera antica)", "licenza": lic,
            "fonte_url": ii.get("descriptionurl") or "", "larghezza": ii.get("thumbwidth"), "altezza": ii.get("thumbheight")}


def _interroga(extra: dict) -> list[dict]:
    params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": LARGHEZZA,
              "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName", **extra}
    st, corpo, _ = casati._http_get(API, params)
    if st != 200:
        raise ErroreAvatar(f"Commons ha risposto {st}")
    try:
        import json
        dati = json.loads(corpo.decode("utf-8", "replace"))
    except ValueError:
        raise ErroreAvatar("Risposta di Commons non leggibile") from None
    pagine = sorted((dati.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [c for c in (_candidata(p) for p in pagine) if c]


def cerca(testo: str) -> list[dict]:
    q = _testo(testo)
    if len(q) < 3:
        raise ErroreAvatar("Scrivi cosa cercare (almeno 3 caratteri), per esempio «Hermes statua» o «Minerva dipinto»")
    try:
        return _interroga({"generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 20})[:12]
    except casati.ErroreCasati as e:
        raise ErroreAvatar(str(e)) from None


def scegli(conn, agente_id: int, file_commons: str, utente_id: int) -> dict:
    if not str(file_commons).startswith("File:") or len(file_commons) > 250:
        raise ErroreAvatar("File non valido")
    if conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone() is None:
        raise ErroreAvatar("Agente inesistente")
    try:
        trovate = _interroga({"titles": file_commons})
    except casati.ErroreCasati as e:
        raise ErroreAvatar(str(e)) from None
    if not trovate:
        raise ErroreAvatar("L'opera non risulta di pubblico dominio o non e' piu' disponibile")
    c = trovate[0]
    try:
        url = casati.url_valido(c["anteprima"])
        st, dati, intest = casati._scarica(url)
    except casati.ErroreCasati as e:
        raise ErroreAvatar(str(e)) from None
    mime = (intest.get("content-type") or intest.get("Content-Type") or "").split(";")[0].strip().lower()
    if st != 200 or mime not in MIME_OK:
        raise ErroreAvatar("Immagine non scaricabile")
    if len(dati) > MAX_BYTE:
        raise ErroreAvatar("Immagine troppo pesante")
    conn.execute("""INSERT INTO agenti_avatar (agente_id, immagine, mime, byte, opera, autore, licenza, file_commons, fonte_url, scelto_da_utente_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (agente_id) DO UPDATE SET immagine = EXCLUDED.immagine, mime = EXCLUDED.mime, byte = EXCLUDED.byte, opera = EXCLUDED.opera, autore = EXCLUDED.autore,
                      licenza = EXCLUDED.licenza, file_commons = EXCLUDED.file_commons, fonte_url = EXCLUDED.fonte_url, scelto_da_utente_id = EXCLUDED.scelto_da_utente_id, scelto_il = NOW()""",
                 (agente_id, dati, mime, len(dati), c["opera"], c["autore"], c["licenza"], c["file"], c["fonte_url"], utente_id))
    conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s, 'avatar_scelto', %s::jsonb, %s)",
                 (agente_id, '{"file": "%s"}' % c["file"].replace('"', "'")[:200], utente_id))
    return info(conn, agente_id)


def info(conn, agente_id: int) -> dict | None:
    return conn.execute("SELECT agente_id, opera, autore, licenza, fonte_url, byte, scelto_il FROM agenti_avatar WHERE agente_id = %s", (agente_id,)).fetchone()


def immagine(conn, agente_id: int):
    return conn.execute("SELECT immagine, mime FROM agenti_avatar WHERE agente_id = %s", (agente_id,)).fetchone()


def rimuovi(conn, agente_id: int):
    conn.execute("DELETE FROM agenti_avatar WHERE agente_id = %s", (agente_id,))


def cornice(livello: int) -> str:
    return CORNICI[max(0, min(5, int(livello)))]


def medaglie(conn, agente_id: int) -> list[dict]:
    """Una medaglia per ogni competenza posseduta, del livello raggiunto."""
    return [{"competenza": c["nome"], "livello": c["livello"], "medaglia": MEDAGLIE[c["livello"]]} for c in ginnasio.competenze_agente(conn, agente_id)]


def scheda_giocatore(conn, agente_id: int) -> dict:
    """Solo dati misurati: niente umore o stress inventati."""
    from . import dossier, squadre
    a = conn.execute("SELECT id, nome, ruolo, livello, budget_token_mensile FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if a is None:
        raise ErroreAvatar("Agente inesistente")
    liv = ginnasio.livello_agente(conn, agente_id)
    st = dossier.statistiche(conn, agente_id)
    mese = conn.execute("""SELECT COALESCE(sum(token_input + token_output), 0) AS token, COALESCE(sum(costo_stimato), 0) AS costo FROM costi_api
                           WHERE agente_id = %s AND creato_il >= date_trunc('month', NOW())""", (agente_id,)).fetchone()
    task = conn.execute("""SELECT count(*) FILTER (WHERE stato <> 'completata') AS aperte, count(*) FILTER (WHERE stato = 'completata') AS chiuse,
                                  count(*) FILTER (WHERE stato <> 'completata' AND scadenza < CURRENT_DATE) AS ritardo FROM task WHERE assegnato_agente_id = %s""", (agente_id,)).fetchone()
    kpi = conn.execute("""SELECT count(*) FILTER (WHERE NOT chiuso) AS aperti, count(*) FILTER (WHERE esito = 'raggiunto') AS raggiunti,
                                 count(*) FILTER (WHERE NOT chiuso AND esito IN ('a_rischio','fuori_rotta')) AS a_rischio FROM kpi_progetto WHERE agente_id = %s""", (agente_id,)).fetchone()
    nprog = conn.execute("SELECT count(*) AS n FROM progetti_agenti x JOIN progetti p ON p.id = x.progetto_id WHERE x.agente_id = %s AND NOT p.archiviato AND p.eliminato_il IS NULL", (agente_id,)).fetchone()["n"]
    budget = a["budget_token_mensile"]
    return {"agente": {"id": a["id"], "nome": a["nome"], "ruolo": a["ruolo"], "livello": a["livello"]},
            "formazione": {"livello": liv, "cornice": cornice(liv), "medaglie": medaglie(conn, agente_id)},
            "affidabilita": {"tasso": st["tasso_approvazione"], "casi": st["casi"], "pollici_su": st["pollici_su"], "pollici_giu": st["pollici_giu"],
                             "approvati": st["approvati"], "respinti": st["respinti"], "giorni": st["giorni"], "sufficienti": st["dati_sufficienti"]},
            "carico": {"task_aperte": int(task["aperte"]), "task_chiuse": int(task["chiuse"]), "in_ritardo": int(task["ritardo"]), "progetti": int(nprog)},
            "costo": {"token_mese": int(mese["token"]), "costo_mese": float(mese["costo"]), "budget_mensile": budget, "percentuale_budget": round(100 * mese["token"] / budget) if budget else None},
            "kpi": {k: int(v) for k, v in kpi.items()}}
