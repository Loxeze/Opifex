"""Ordine della cartella «Opifex» su Drive (nella 3.0: «Opifex/Opifex 3»). La regola:
  Controllo di gestione/Passive/<anno>/<mm - Mese>   fatture e ricevute che Lorenzo paga (arrivate per posta)
  Controllo di gestione/Attive/<anno>/<mm - Mese>    fatture e incassi a favore di Lorenzo
  Imprese/<nome dell'impresa>                        una cartella per ogni attivita' (Logos, Renovatio...)
  Progetti/<nome del progetto>                       le cartelle dei progetti (con dentro agent/ e repository/)
  Agenti/<nome dell'agente>                          la cartella personale di ogni agente: memoria e documenti che produce
  Agenti/Tavoli/<data - titolo>                      verbali e documenti dei tavoli di lavoro (fonti condivise)
  Agenti/Riunioni/<data - titolo>                    verbali e documenti delle riunioni
  Sistema/<...>                                      cio' che scrive il sistema da solo (backup cifrati, backup dei siti)
Nella radice non nasce piu' niente. Lo spostamento lo fa il sistema, non un agente: riconosce le cartelle dall'identificativo salvato in Opifex,
quindi non sbaglia per nomi simili; cio' che non riconosce resta dov'e' e viene segnalato. Spostare non cambia l'identificativo: nessun collegamento si rompe."""
import json
import re

from . import google
from .google import ErroreGoogle, _DRIVE, _q

CARTELLA = "application/vnd.google-apps.folder"
CONTENITORI = {"gestione": "Controllo di gestione", "imprese": "Imprese", "progetti": "Progetti", "agenti": "Agenti", "sistema": "Sistema"}
CONDIVISE = ("Tavoli", "Riunioni")              # dentro Agenti: le fonti condivise fra gli agenti
GESTIONE = {"uscita": "Passive", "entrata": "Attive"}
DI_SISTEMA = ("Backup", "Maestro di chiavi - backup siti")


def _h(tok: str) -> dict:
    return {"Authorization": "Bearer " + tok}


def sposta(tok: str, file_id: str, genitore: str) -> bool:
    """Sposta un elemento in un'altra cartella (stesso identificativo, stesso nome). Restituisce False se era gia' li'."""
    f = google._http("GET", f"{_DRIVE}/{file_id}", params={"fields": "id,parents"}, headers=_h(tok))
    attuali = f.get("parents") or []
    if genitore in attuali:
        return False
    google._http("PATCH", f"{_DRIVE}/{file_id}", params={"addParents": genitore, "removeParents": ",".join(attuali), "fields": "id,parents"}, headers=_h(tok), json={})
    return True


def _valida(tok: str, cid: str | None) -> bool:
    if not cid:
        return False
    try:
        f = google._http("GET", f"{_DRIVE}/{cid}", params={"fields": "id,trashed,mimeType"}, headers=_h(tok))
        return not f.get("trashed") and f.get("mimeType") == CARTELLA
    except ErroreGoogle:
        return False


def _figli(tok: str, genitore: str) -> list[dict]:
    out, pagina = [], None
    while True:
        p = {"q": f"'{_q(genitore)}' in parents and trashed=false", "fields": "nextPageToken,files(id,name,mimeType)", "pageSize": 200}
        if pagina:
            p["pageToken"] = pagina
        r = google._http("GET", _DRIVE, params=p, headers=_h(tok))
        out.extend(r.get("files", []))
        pagina = r.get("nextPageToken")
        if not pagina:
            return out


def _in_radice(tok: str, radice: str, nome: str) -> str | None:
    q = f"name='{_q(nome)}' and '{_q(radice)}' in parents and mimeType='{CARTELLA}' and trashed=false"
    t = google._http("GET", _DRIVE, params={"q": q, "fields": "files(id)", "pageSize": 1}, headers=_h(tok)).get("files", [])
    return t[0]["id"] if t else None


def _sotto(tok: str, file_id: str, radice: str) -> bool:
    cur = file_id
    for _ in range(12):
        if cur == radice:
            return True
        f = google._http("GET", f"{_DRIVE}/{cur}", params={"fields": "id,parents,trashed"}, headers=_h(tok))
        if f.get("trashed") or not f.get("parents"):
            return False
        cur = f["parents"][0]
    return False


def contenitore(conn, tok: str, radice: str, quale: str) -> str:
    """Id di Opifex/Agenti, Opifex/Progetti o Opifex/Sistema (lo crea se manca, lo ritrova se e' stato spostato)."""
    nome, chiave = CONTENITORI[quale], "drive_contenitore_" + quale
    salvato = google._leggi(conn, chiave)
    cid = google.cartella(tok, nome, radice, salvato or None)
    if cid != salvato:
        google._scrivi(conn, chiave, cid)
    return cid


def _adotta_contenitori(conn, tok: str, radice: str) -> None:
    """Se «Agenti», «Progetti» o «Sistema» esistono gia' altrove dentro Opifex (per esempio create da un agente nella propria cartella) e nella radice mancano,
    porta nella radice quelle invece di farne un doppione."""
    for quale, nome in CONTENITORI.items():
        if _valida(tok, google._leggi(conn, "drive_contenitore_" + quale)) or _in_radice(tok, radice, nome):
            continue
        q = f"name='{_q(nome)}' and mimeType='{CARTELLA}' and trashed=false"
        for f in google._http("GET", _DRIVE, params={"q": q, "fields": "files(id)", "pageSize": 20}, headers=_h(tok)).get("files", []):
            if _sotto(tok, f["id"], radice):
                sposta(tok, f["id"], radice)
                google._scrivi(conn, "drive_contenitore_" + quale, f["id"])
                break


def percorso(conn, tok: str, radice: str, quale: str, *nomi: str) -> str:
    """Id di <contenitore>/<nome>/<nome>/... (crea cio' che manca, mai doppioni)."""
    cid = contenitore(conn, tok, radice, quale)
    for n in nomi:
        cid = google.cartella(tok, n, cid)
    return cid


def _pulito(nome: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", " ", nome or "").strip()[:90] or "senza titolo"


def struttura(conn, tok: str | None = None) -> dict:
    """Prepara l'ossatura: i contenitori, Passive e Attive, Agenti/Tavoli e Agenti/Riunioni, una cartella per ogni impresa.
    Restituisce cosa c'e'. Senza Drive collegato non fa nulla."""
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        return {"drive": False}
    tok = tok or google.token_accesso(conn, account)
    radice = google.radice_valida(conn, tok)
    for q in CONTENITORI:
        contenitore(conn, tok, radice, q)
    for v in GESTIONE.values():
        percorso(conn, tok, radice, "gestione", v)
    for c in CONDIVISE:
        percorso(conn, tok, radice, "agenti", c)
    imprese = [r["nome"] for r in conn.execute("SELECT nome FROM aziende ORDER BY id").fetchall()]
    for nome in imprese:
        percorso(conn, tok, radice, "imprese", _pulito(nome))
    return {"drive": True, "imprese": imprese}


def salva_testo(conn, quale: str, cartelle: list[str], nome: str, testo: str) -> str | None:
    """Salva un testo (un verbale) come documento Google in <contenitore>/<cartelle...>. Restituisce il link, oppure None se Drive non c'e'.
    Non fa fallire chi lo chiama: un verbale resta comunque in Opifex."""
    try:
        account = int(google._leggi(conn, "drive_account_id") or 0)
        if not account:
            return None
        tok = google.token_accesso(conn, account)
        dove = percorso(conn, tok, google.radice_valida(conn, tok), quale, *[_pulito(c) for c in cartelle])
        limite = "opifex-testo-3a9"
        meta = json.dumps({"name": _pulito(nome), "parents": [dove], "mimeType": "application/vnd.google-apps.document"})
        corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{limite}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n").encode() \
            + (testo or "").encode() + f"\r\n--{limite}--".encode()
        f = google._http("POST", "https://www.googleapis.com/upload/drive/v3/files", params={"uploadType": "multipart", "fields": "id,webViewLink"},
                         headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/related; boundary={limite}"}, content=corpo)
        return f.get("webViewLink") or ""
    except Exception:  # noqa: BLE001
        return None


def cartella_ordinata(conn, tok: str, radice: str, quale: str, nome: str, esistente: str | None = None) -> str:
    """Come google.cartella, ma dentro il contenitore giusto. Una cartella senza identificativo salvato, nata nella radice prima della regola,
    viene ritrovata per nome e portata al suo posto (cosi' non nasce un doppione)."""
    dentro = contenitore(conn, tok, radice, quale)
    if not esistente:
        try:
            vecchia = _in_radice(tok, radice, nome)
            if vecchia and vecchia != dentro:
                sposta(tok, vecchia, dentro)
                return vecchia
        except Exception:  # noqa: BLE001 - se il controllo non riesce si procede: al piu' la cartella nasce nel contenitore
            pass
    return google.cartella(tok, nome, dentro, esistente)


def _contesto(conn):
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        raise ErroreGoogle("Google Drive non e' collegato (Impostazioni > Collegamenti)")
    tok = google.token_accesso(conn, account)
    return tok, google.radice_valida(conn, tok)


def riordina(conn, esegui: bool) -> dict:
    """Mette al loro posto gli elementi della radice che il sistema riconosce. Con esegui=False restituisce solo il piano."""
    tok, radice = _contesto(conn)
    agenti = {r["drive_cartella_id"]: r["nome"] for r in conn.execute("SELECT nome, drive_cartella_id FROM agenti WHERE drive_cartella_id IS NOT NULL").fetchall()}
    progetti = {r["drive_cartella_id"]: r["nome"] for r in conn.execute("SELECT nome, drive_cartella_id FROM progetti WHERE drive_cartella_id IS NOT NULL AND eliminato_il IS NULL").fetchall()}
    if esegui:
        _adotta_contenitori(conn, tok, radice)
        ids = {q: contenitore(conn, tok, radice, q) for q in CONTENITORI}
    else:
        ids = {q: (google._leggi(conn, "drive_contenitore_" + q) or None) for q in CONTENITORI}
    piano = {"agenti": [], "progetti": [], "sistema": [], "imprese": [], "gestione": [], "da_chiarire": [], "spostati": 0, "errori": []}
    for f in _figli(tok, radice):
        if f["id"] in ids.values() or (f["mimeType"] == CARTELLA and f["name"] in CONTENITORI.values()):
            continue
        dove = ("agenti" if f["id"] in agenti else "progetti" if f["id"] in progetti
                else "sistema" if f["mimeType"] == CARTELLA and f["name"] in DI_SISTEMA else "da_chiarire")
        piano[dove].append({"id": f["id"], "nome": f["name"], "cartella": f["mimeType"] == CARTELLA})
        if esegui and dove != "da_chiarire":
            try:
                if sposta(tok, f["id"], ids[dove]):
                    piano["spostati"] += 1
            except ErroreGoogle as e:
                piano["errori"].append(f"{f['name']}: {e}")
    if esegui:
        conn.execute("INSERT INTO registro_azioni (azione, dettagli) VALUES ('drive_riordinato', %s::jsonb)",
                     (json.dumps({"spostati": piano["spostati"], "da_chiarire": [x["nome"] for x in piano["da_chiarire"]], "errori": piano["errori"][:10]}),))
    return piano


def da_fare(conn) -> bool:
    import datetime
    from . import edizione
    attivo = google._leggi(conn, "drive_ordine_attivo")
    attivo = attivo == "true" or (not attivo and edizione.tre())   # nella 3.0 il Drive nasce ordinato: la regola e' accesa di serie
    return bool(int(google._leggi(conn, "drive_account_id") or 0)) and attivo and google._leggi(conn, "drive_ordine_ultimo") != datetime.date.today().isoformat()


def giro(conn) -> None:
    """Una volta al giorno, se la regola e' attiva: rimette a posto cio' che e' finito nella radice e avvisa (una volta sola per elenco) di cio' che non riconosce."""
    import datetime
    google._scrivi(conn, "drive_ordine_ultimo", datetime.date.today().isoformat())
    try:
        struttura(conn)
    except Exception:  # noqa: BLE001 - l'ossatura si riprova domani; il riordino va avanti
        pass
    p = riordina(conn, True)
    nomi = sorted(x["nome"] for x in p["da_chiarire"])
    firma = json.dumps(nomi, ensure_ascii=False)
    if nomi and firma != google._leggi(conn, "drive_ordine_segnalati"):
        google._scrivi(conn, "drive_ordine_segnalati", firma)
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     ("Drive, cartella Opifex: nella radice ci sono elementi che non so a chi appartengono e che ho lasciato dove sono: " + ", ".join(nomi[:12])
                      + (" e altri" if len(nomi) > 12 else "") + ". Spostali tu in Controllo di gestione, Imprese, Progetti, Agenti o Sistema, oppure dimmi dove vanno.",))
