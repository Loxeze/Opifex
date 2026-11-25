"""FARO su Drive: per ogni bando trovato una cartella Opifex/Bandi/<scadenza - titolo> con tutto il materiale scaricato
(la pagina ufficiale, l'avviso, gli allegati, le FAQ) e la SCHEDA TECNICA, un documento Google da leggere a colpo d'occhio.
La scheda si scrive con i dati della segnalazione e si completa quando c'e' la lettura approfondita. Nessun modello: costo zero.

Il registro delle fonti si copia su Drive come foglio Google (Opifex/Bandi/Registro delle fonti): la copia e' in sola lettura,
il registro vero resta in Opifex (Bandi > Fonti), dove si ampliano e si correggono le fonti."""
import html
import json
import re
import threading
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from . import faro_lettura
from .db import connessione

FUSO = ZoneInfo("Europe/Rome")
MAX_FILE = 10
SINCRONO = False
_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
_corre = threading.Lock()
MIME = {".pdf": "application/pdf", ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".odt": "application/vnd.oasis.opendocument.text", ".rtf": "application/rtf", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".zip": "application/zip"}
MESI = faro_lettura.MESI


class NonCollegato(Exception):
    pass


# ---------- Drive (sostituibile nei collaudi) ----------
def _contesto(conn):
    from . import drive_ordine, google
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        raise NonCollegato("Drive non collegato")
    tok = google.token_accesso(conn, account)
    return tok, google.radice_valida(conn, tok)


def _cartella(conn, tok: str, radice: str, nome: str, esistente: str | None) -> str:
    from . import drive_ordine, google
    return google.cartella(tok, nome, drive_ordine.contenitore(conn, tok, radice, "bandi"), esistente)


def _contenitore(conn, tok: str, radice: str) -> str:
    from . import drive_ordine
    return drive_ordine.contenitore(conn, tok, radice, "bandi")


def _nomi(tok: str, cartella_id: str) -> dict:
    from . import drive_ordine
    return {f["name"]: f["id"] for f in drive_ordine._figli(tok, cartella_id)}


def _carica(tok: str, cartella_id: str, nome: str, mime: str, dati: bytes, converti: str | None = None) -> str:
    from . import google
    limite = "opifex-faro-9b2"
    meta = {"name": nome, "parents": [cartella_id], **({"mimeType": converti} if converti else {})}
    corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{limite}\r\nContent-Type: {mime}\r\n\r\n").encode() + dati + f"\r\n--{limite}--".encode()
    return google._http("POST", _UPLOAD, params={"uploadType": "multipart", "fields": "id"},
                        headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/related; boundary={limite}"}, content=corpo)["id"]


def _riscrivi(tok: str, file_id: str, mime: str, dati: bytes) -> str:
    from . import google
    return google._http("PATCH", f"{_UPLOAD}/{file_id}", params={"uploadType": "media", "fields": "id"},
                        headers={"Authorization": "Bearer " + tok, "Content-Type": mime}, content=dati)["id"]


def link_cartella(cid: str | None) -> str:
    return f"https://drive.google.com/drive/folders/{cid}" if cid else ""


def link_doc(did: str | None) -> str:
    return f"https://docs.google.com/document/d/{did}/edit" if did else ""


# ---------- il materiale ----------
def _pulito(t: str, n: int = 90) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|#]+", " ", t or "")).strip()[:n] or "senza titolo"


def nome_cartella(b: dict) -> str:
    return (b["scadenza"].isoformat() if b.get("scadenza") else "senza data") + " - " + _pulito(b["titolo"])


def materiale(url: str) -> tuple[list[tuple[str, str, bytes, str]], list[str]]:
    """Scarica la pagina del bando e i documenti collegati. Restituisce ([(nome file, tipo, contenuto, indirizzo)], [errori])."""
    errori, out = [], []
    try:
        fin, tipo, dati = faro_lettura.scarica(url)
    except faro_lettura.ErroreLettura as e:
        return [], [f"pagina del bando: {e}"]
    host = (urlparse(fin).hostname or "").removeprefix("www.")
    if dati[:5] == b"%PDF-" or "pdf" in tipo:
        out.append((f"00 - Bando ({host}).pdf", "application/pdf", dati, fin))
        return out, errori
    out.append((f"00 - Pagina del bando ({host}).html", "text/html", dati, fin))
    try:
        link = faro_lettura._in_testo(fin, tipo, dati)[1]
    except faro_lettura.ErroreLettura:
        link = []
    for i, (u, et) in enumerate(faro_lettura.scegli_allegati(fin, link, MAX_FILE), 1):
        try:
            f2, t2, d2 = faro_lettura.scarica(u)
        except faro_lettura.ErroreLettura as e:
            errori.append(f"{et}: {e}")
            continue
        est = next((e for e in MIME if urlparse(f2).path.lower().endswith(e)), ".pdf" if d2[:5] == b"%PDF-" else ".html" if "html" in t2 else "")
        base = urlparse(f2).path.rsplit("/", 1)[-1]
        base = re.sub(r"\.[a-z0-9]{2,4}$", "", base, flags=re.I)
        nome = f"{i:02d} - {_pulito(et, 60)}" + (f" ({_pulito(base, 40)})" if base and _pulito(base, 40).lower() not in _pulito(et, 60).lower() else "") + est
        out.append((nome, MIME.get(est, "text/html" if est == ".html" else t2.split(";")[0] or "application/octet-stream"), d2, f2))
    return out, errori


# ---------- la scheda tecnica ----------
def _data(d) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}" if d else ""


def _euro(x) -> str:
    return f"{int(round(float(x))):,}".replace(",", ".") + " €"


def scheda_html(b: dict, profili: list[dict], file: list[dict], errori: list[str] | None = None) -> str:
    """Una pagina: in alto il colpo d'occhio (scadenza, contributo, copertura, per chi, consiglio), poi i dati letti con la loro fonte, il giudizio e il materiale."""
    e = html.escape
    sc = b.get("scheda") if b.get("scheda_stato") == "pronta" else None
    campi = (sc or {}).get("campi") or {}
    g = (sc or {}).get("giudizio") or {}
    oggi = datetime.now(FUSO).date()
    if b.get("scadenza"):
        gg = (b["scadenza"] - oggi).days
        scad = _data(b["scadenza"]) + (" (scaduto)" if gg < 0 else " (oggi)" if gg == 0 else f" (tra {gg} giorni)")
    else:
        scad = b.get("scadenza_nota") or "non indicata"
    contr = ("fino a " + _euro(b["importo"])) if b.get("importo") is not None else (b.get("importo_nota") or "non indicato")
    righe = [("Scadenza", (campi.get("scadenza") or {}).get("valore") or scad),
             ("Contributo", (campi.get("importo_max") or {}).get("valore") or contr),
             ("Copertura dei costi", (campi.get("intensita") or {}).get("valore") or (f"{b['copertura']}%" if b.get("copertura") else "non indicata")),
             ("Chi può partecipare", (campi.get("beneficiari") or {}).get("valore") or b.get("beneficiari") or "non indicato"),
             ("Come si presenta", (campi.get("invio") or {}).get("valore") or "da leggere nell'avviso"),
             ("Per chi di noi", "; ".join(f"{p['profilo']}{' (da valutare)' if p['esito'] == 'da_valutare' else ''}" for p in profili) or "—")]
    if g.get("consiglio"):
        righe.append(("Consiglio", f"{g['consiglio'].upper()} — {g.get('motivo') or ''}"))
    t = [f"<h1>{e(b['titolo'])}</h1>", f"<p><b>{e(b['ente'])}</b>" + (f" · {e(b['regione'])}" if b.get("regione") else "") + (f" · {e(b['categoria'])}" if b.get("categoria") else "") + "</p>",
         f"<p>Pagina ufficiale: <a href=\"{e(b['url'])}\">{e(b['url'])}</a></p>", "<h2>A colpo d'occhio</h2>", "<table border=\"1\" cellpadding=\"6\" style=\"border-collapse:collapse\">"]
    t += [f"<tr><td><b>{e(k)}</b></td><td>{e(str(v))}</td></tr>" for k, v in righe]
    t += ["</table>", f"<h2>Che cosa finanzia</h2><p>{e(b['sintesi'])}</p>"]
    if profili:
        t += ["<h2>Perché ci riguarda</h2><ul>"] + [f"<li><b>{e(p['profilo'])}</b>{' — da valutare' if p['esito'] == 'da_valutare' else ''}: {e(p['motivo'])}</li>" for p in profili] + ["</ul>"]
    if sc:
        docs = {d["id"]: d for d in sc.get("documenti") or []}
        t += ["<h2>Dati del bando (lettura approfondita)</h2>", "<table border=\"1\" cellpadding=\"6\" style=\"border-collapse:collapse\">",
              "<tr><td><b>Voce</b></td><td><b>Che cosa dice il bando</b></td><td><b>Dove è scritto</b></td></tr>"]
        for k, et in faro_lettura.CAMPI:
            c = campi.get(k)
            if c:
                d = docs.get(c["documento"]) or {}
                t.append(f"<tr><td>{e(et)}</td><td>{e(c['valore'])}<br><i>«{e(c['citazione'])}»</i></td><td>{e(c['documento'])} {e(d.get('titolo', ''))}, {e(c['punto'])}</td></tr>")
            else:
                t.append(f"<tr><td>{e(et)}</td><td><i>non scritto nei documenti letti</i></td><td></td></tr>")
        t.append("</table>")
        if g:
            lista = lambda titolo, v: [f"<h3>{titolo}</h3><ul>"] + [f"<li>{e(x)}</li>" for x in v] + ["</ul>"] if v else []  # noqa: E731
            t += ["<h2>Giudizio</h2>", f"<p><b>Consiglio: {e(g.get('consiglio', ''))}</b>" + (f" (per {e(g['profilo'])})" if g.get("profilo") else "") + f". {e(g.get('motivo', ''))}</p>"]
            t += lista("Requisiti che abbiamo", g.get("requisiti_ok")) + lista("Requisiti che mancano o da verificare", g.get("requisiti_mancanti"))
            t += ([f"<p><b>Impegno richiesto:</b> {e(g['impegno'])}</p>"] if g.get("impegno") else []) + lista("Rischi", g.get("rischi"))
        if sc.get("non_confermati"):
            t.append("<p><i>Dati proposti dalla lettura ma non ritrovati nel testo, quindi esclusi: " + e("; ".join(f"{x['campo']}: {x['proposto']}" for x in sc["non_confermati"])) + "</i></p>")
    else:
        t.append("<p><i>Lettura approfondita non ancora fatta: i dati qui sopra vengono dalla segnalazione di Faro. Quando il bando passa il primo setaccio, la scheda si completa da sola.</i></p>")
    if b.get("verifica") and b["verifica"] != "confermato":
        t.append(f"<p><b>Attenzione:</b> {e(b.get('verifica_nota') or '')}</p>")
    t += ["<h2>Materiale in questa cartella</h2><ul>"] + [f"<li>{e(f['nome'])} — <a href=\"{e(f['url'])}\">originale</a></li>" for f in file] + ["</ul>"]
    if errori:
        t.append("<p><i>Non scaricati: " + e("; ".join(errori)) + "</i></p>")
    t.append(f"<p><small>Scheda scritta da Opifex il {_data(oggi)} con i dati letti da Faro, senza aggiunte.</small></p>")
    return "<html><head><meta charset=\"utf-8\"></head><body>" + "\n".join(t) + "</body></html>"


# ---------- archiviazione ----------
def acceso(conn) -> bool:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'faro_drive'").fetchone()
    return (r["valore"] if r else "1") != "0"


def archivia(bid: int, scarica: bool = True) -> str:
    """Crea (o ritrova) la cartella del bando, scarica il materiale che non c'e' ancora e scrive o aggiorna la scheda tecnica. Restituisce lo stato."""
    with connessione() as conn:
        b = conn.execute("SELECT * FROM faro_bandi WHERE id = %s", (bid,)).fetchone()
        if b is None:
            return ""
        profili = conn.execute("""SELECT p.nome AS profilo, a.esito, a.motivo FROM faro_abbinamenti a JOIN faro_profili p ON p.id = a.profilo_id
                                  WHERE a.bando_id = %s AND (p.tipo = 'impresa' OR (SELECT valore FROM impostazioni_sistema WHERE chiave='faro_clienti_acceso') = '1')
                                  ORDER BY p.id""", (bid,)).fetchall()
        try:
            tok, radice = _contesto(conn)
        except NonCollegato:
            conn.execute("UPDATE faro_bandi SET drive_stato='drive_non_collegato', drive_il=NOW() WHERE id=%s", (bid,))
            return "drive_non_collegato"
        except Exception as e:  # noqa: BLE001
            conn.execute("UPDATE faro_bandi SET drive_stato=%s, drive_il=NOW() WHERE id=%s", (("errore: " + str(e))[:200], bid))
            return "errore"
        conn.commit()
    try:
        with connessione() as conn:
            cid = _cartella(conn, tok, radice, nome_cartella(b), b["drive_cartella_id"])
        file = list(b["drive_file"] or [])
        errori = []
        if scarica:
            gia = _nomi(tok, cid)
            roba, errori = materiale(b["url"])
            visti = {f["url"] for f in file}
            for nome, mime, dati, url in roba:
                if url in visti and nome in gia:
                    continue
                fid = gia.get(nome) or _carica(tok, cid, nome, mime, dati)
                file = [f for f in file if f["url"] != url] + [{"nome": nome, "id": fid, "url": url}]
        doc = scheda_html(b, profili, file, errori).encode()
        nome_doc = "Scheda tecnica - " + _pulito(b["titolo"], 80)
        did = None
        if b["drive_scheda_id"]:
            try:
                did = _riscrivi(tok, b["drive_scheda_id"], "text/html", doc)
            except Exception:  # noqa: BLE001 - la scheda e' stata tolta da Drive: se ne scrive una nuova
                did = None
        if not did:
            did = _carica(tok, cid, nome_doc, "text/html", doc, converti="application/vnd.google-apps.document")
        with connessione() as conn:
            conn.execute("""UPDATE faro_bandi SET drive_cartella_id=%s, drive_scheda_id=%s, drive_file=%s::jsonb, drive_stato='salvato', drive_il=NOW() WHERE id=%s""",
                         (cid, did, json.dumps(file, ensure_ascii=False), bid))
        return "salvato"
    except Exception as e:  # noqa: BLE001 - Drive che non risponde: si riprova piu' tardi
        with connessione() as conn:
            conn.execute("UPDATE faro_bandi SET drive_stato=%s, drive_il=NOW() WHERE id=%s", (("errore: " + str(e))[:200], bid))
        return "errore"


def in_sospeso(conn, limite: int = 6) -> list[int]:
    """Bandi aperti ancora senza cartella (o con un errore vecchio di un'ora, o in attesa che Drive sia collegato). Quelli non ritrovati sulla pagina restano fuori."""
    if not acceso(conn):
        return []
    collegato = bool(conn.execute("SELECT 1 FROM impostazioni_sistema WHERE chiave='drive_account_id' AND valore <> '' AND valore <> '0'").fetchone())
    return [r["id"] for r in conn.execute("""SELECT id FROM faro_bandi WHERE stato IN ('nuovo','interessante','candidatura') AND verifica <> 'non_trovato'
                                              AND (drive_stato = '' OR (drive_stato LIKE 'errore%%' AND drive_il < NOW() - interval '1 hour')
                                                   OR (drive_stato = 'drive_non_collegato' AND %s))
                                             ORDER BY id LIMIT %s""", (collegato, limite)).fetchall()]


_coda: dict[int, bool] = {}   # bando -> scaricare il materiale? (in attesa del lavoratore)


def archivia_tutti(ids: list[int], scarica: bool = True) -> None:
    """In sottofondo, uno alla volta: le richieste che arrivano mentre il lavoratore e' occupato si mettono in coda, non si perdono."""
    with _corre:
        for i in ids:
            _coda[i] = _coda.get(i, False) or scarica
        avvia = bool(_coda) and not getattr(archivia_tutti, "attivo", False)
        if avvia:
            archivia_tutti.attivo = True
    if not avvia:
        return

    def lavora():
        try:
            while True:
                with _corre:
                    if not _coda:
                        archivia_tutti.attivo = False
                        return
                    i, sc = next(iter(_coda.items()))
                    del _coda[i]
                try:
                    archivia(i, sc)
                except Exception:  # noqa: BLE001 - un bando che non va non ferma gli altri
                    pass
        finally:
            with _corre:
                archivia_tutti.attivo = False
    if SINCRONO:
        lavora()
    else:
        threading.Thread(target=lavora, daemon=True).start()


# ---------- il registro delle fonti su Drive ----------
def copia_registro(conn) -> str:
    """Copia il registro delle fonti in un foglio Google dentro Opifex/Bandi. Restituisce il link. Il registro vero resta in Opifex."""
    import csv
    import io
    tok, radice = _contesto(conn)
    righe = conn.execute("""SELECT categoria, regione, nome, url, CASE WHEN scartata THEN 'scartata' WHEN proposta THEN 'proposta da Faro' WHEN attiva THEN 'attiva' ELSE 'in pausa' END AS stato,
                                   trovati, to_char(ultima_il AT TIME ZONE 'Europe/Rome', 'YYYY-MM-DD') AS ultimo, CASE WHEN raggiungibile IS FALSE THEN 'non risponde' ELSE '' END AS indirizzo,
                                   origine, motivo FROM faro_fonti ORDER BY categoria, regione NULLS FIRST, nome""").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Categoria", "Regione", "Ente / fonte", "Pagina dei bandi", "Stato", "Bandi trovati", "Ultimo controllo", "Indirizzo", "Origine", "Note"])
    for r in righe:
        w.writerow([r["categoria"], r["regione"] or "", r["nome"], r["url"], r["stato"], r["trovati"], r["ultimo"] or "", r["indirizzo"], r["origine"], r["motivo"]])
    dati = buf.getvalue().encode()
    cid = _contenitore(conn, tok, radice)
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'faro_registro_drive'").fetchone()
    fid = None
    if r and r["valore"]:
        try:
            fid = _riscrivi(tok, r["valore"], "text/csv", dati)
        except Exception:  # noqa: BLE001
            fid = None
    if not fid:
        fid = _carica(tok, cid, "Registro delle fonti dei bandi", "text/csv", dati, converti="application/vnd.google-apps.spreadsheet")
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_registro_drive', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (fid,))
    return f"https://docs.google.com/spreadsheets/d/{fid}/edit"
