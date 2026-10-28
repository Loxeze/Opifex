"""Il Maestro di chiavi opera sui siti: scrive direttamente, scarica e carica file e cartelle, e ogni notte (23:33, ora italiana)
fa il backup cifrato di tutti i siti su una cartella Drive dedicata. La chiave di backup nasce al primo uso, vive nella cassaforte e non esce mai:
nessuna rotta, nessuno strumento e nessun registro la mostra. Su Drive finiscono solo archivi cifrati."""
import io
import json
import posixpath
import struct
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken

from . import cassaforte, google
from . import siti_hosting as sh

FUSO = ZoneInfo("Europe/Rome")
ORA_BACKUP = (23, 33)
FINESTRA_FINO_ALLE = 4          # se il server era spento alle 23:33, recupera fino alle 4 del mattino
MAX_DEPOSITO = 50_000_000       # un elemento del deposito
MAX_FILE_BACKUP = 100_000_000
MAX_BACKUP = 1_500_000_000
MAX_FILE_N = 50_000
MAX_PROFONDITA = 20
CHUNK = 1_000_000
MAGIA = b"OPXB1"
CARTELLA_DRIVE = "Maestro di chiavi - backup siti"
CONSERVA_GIORNI_DEPOSITO = 30
CONSERVA_COPIE_DRIVE = 14   # per ogni sito: le ultime 14 copie notturne


class ErroreCustode(Exception):
    pass


# ---------- chiave di backup (mai mostrata) ----------
def _chiave(conn) -> bytes:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_chiave_backup'").fetchone()
    if r:
        return cassaforte.decifra(r["valore"]).encode()
    k = Fernet.generate_key()
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('custode_chiave_backup', %s) ON CONFLICT (chiave) DO NOTHING", (cassaforte.cifra(k.decode()),))
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_chiave_backup'").fetchone()
    return cassaforte.decifra(r["valore"]).encode()


def cifra_file(conn, src, dst):
    f = Fernet(_chiave(conn))
    dst.write(MAGIA)
    src.seek(0)
    while True:
        b = src.read(CHUNK)
        if not b:
            break
        t = f.encrypt(b)
        dst.write(struct.pack(">I", len(t)) + t)


def decifra_file(conn, src, dst):
    f = Fernet(_chiave(conn))
    if src.read(len(MAGIA)) != MAGIA:
        raise ErroreCustode("Non e' un archivio di backup del Maestro di chiavi")
    while True:
        h = src.read(4)
        if not h:
            break
        try:
            dst.write(f.decrypt(src.read(struct.unpack(">I", h)[0])))
        except (InvalidToken, struct.error):
            raise ErroreCustode("Archivio danneggiato o cifrato con un'altra chiave") from None


# ---------- percorsi nei siti ----------
def _aperto(conn, nome: str) -> dict:
    s = sh.carica(conn, nome=nome or "")
    if s is None or not s["attivo"]:
        raise ErroreCustode(f"Non esiste un sito attivo chiamato «{nome}»")
    if s["tipo"] not in sh.OPERATIVI or s["tipo"] == "wordpress":
        raise ErroreCustode("Per file e cartelle serve un sito SFTP o FTPS (WordPress si salva e si modifica per pagine)")
    return s


def cammina(c, base: str, note: dict):
    """Genera (percorso, byte) di tutti i file sotto base. Collegamenti simbolici saltati, profondita' limitata."""
    pila = [(base, 0)]
    while pila:
        d, prof = pila.pop()
        try:
            voci = sorted(c.voci(d))
        except sh.ErroreSito as e:
            raise ErroreCustode(str(e)) from None
        except Exception as e:  # noqa: BLE001
            note["errori"].append(f"{d}: {type(e).__name__}")
            continue
        for nome, e_dir, byte, link in voci:
            if nome in (".", ".."):
                continue
            p = posixpath.join(d, nome)
            if link:
                note["saltati"].append(p + " (collegamento)")
            elif e_dir:
                if prof < MAX_PROFONDITA:
                    pila.append((p, prof + 1))
                else:
                    note["saltati"].append(p + " (troppo in profondita')")
            else:
                yield p, byte


def _zip_cartella(c, base: str, massimo: int, note: dict, f_zip) -> tuple[int, int]:
    """Comprime la cartella nel file indicato; ritorna (file, byte non compressi)."""
    n = tot = 0
    with zipfile.ZipFile(f_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p, byte in cammina(c, base, note):
            if byte > MAX_FILE_BACKUP:
                note["saltati"].append(f"{p} (oltre {MAX_FILE_BACKUP // 1_000_000} MB)")
                continue
            if n >= MAX_FILE_N or tot + byte > massimo:
                note["saltati"].append(f"{p} (limite raggiunto)")
                continue
            try:
                dati = c.leggi_bytes(p, MAX_FILE_BACKUP)
            except sh.ErroreSito as e:
                note["saltati"].append(f"{p} ({str(e)[:60]})")
                continue
            except Exception as e:  # noqa: BLE001
                note["errori"].append(f"{p}: {type(e).__name__}")
                continue
            z.writestr(p[len(base):].lstrip("/") or posixpath.basename(p), dati)
            n += 1
            tot += len(dati)
    return n, tot


def _log(conn, agente_id, azione, dett):
    conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli) VALUES (%s,%s,%s::jsonb)", (agente_id, azione, json.dumps(dett)))


# ---------- deposito ----------
def deposita(conn, nome: str, dati: bytes, tipo: str, sito_nome: str | None, origine: str) -> int:
    if len(dati) > MAX_DEPOSITO:
        raise ErroreCustode(f"Troppo grande per il deposito (massimo {MAX_DEPOSITO // 1_000_000} MB): scegli una parte piu' piccola")
    return conn.execute("INSERT INTO custode_file (nome, tipo, sito_nome, origine, byte, contenuto) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (nome[:200], tipo, sito_nome, origine[:300], len(dati), dati)).fetchone()["id"]


def scarica(conn, agente_id, sito: str, percorso: str) -> str:
    s = _aperto(conn, sito)
    perc = sh.percorso_sicuro(s["percorso_base"], percorso)
    note = {"saltati": [], "errori": []}
    with sh._apri(s) as c:
        try:
            c.voci(perc)
            e_dir = True
        except Exception:  # noqa: BLE001 - se non si elenca e' un file
            e_dir = False
        if e_dir:
            buf = io.BytesIO()
            n, tot = _zip_cartella(c, perc, MAX_DEPOSITO * 2, note, buf)
            if n == 0:
                return "ERRORE: la cartella e' vuota o non leggibile" + (" (" + "; ".join(note["errori"][:3]) + ")" if note["errori"] else "")
            dati, nome, tipo = buf.getvalue(), (posixpath.basename(perc.rstrip("/")) or s["nome"]) + ".zip", "zip"
        else:
            dati, nome, tipo = c.leggi_bytes(perc, MAX_DEPOSITO), posixpath.basename(perc), "file"
    sh._memorizza_impronta(conn, s)
    fid = deposita(conn, nome, dati, tipo, s["nome"], perc)
    _log(conn, agente_id, "sito_scarica", {"sito": s["nome"], "percorso": perc[:200], "deposito": fid, "byte": len(dati)})
    extra = f" Saltati {len(note['saltati'])} elementi." if note["saltati"] else ""
    return f"Scaricato nel deposito con id {fid}: {nome} ({len(dati)} byte, {'cartella compressa' if tipo == 'zip' else 'file'}).{extra}"


def carica_su_sito(conn, agente_id, sito: str, deposito_id: int, percorso: str, estrai: bool) -> str:
    s = _aperto(conn, sito)
    d = conn.execute("SELECT * FROM custode_file WHERE id = %s", (int(deposito_id),)).fetchone()
    if d is None:
        raise ErroreCustode("Elemento del deposito inesistente (usa deposito_elenca)")
    dest = sh.percorso_sicuro(s["percorso_base"], percorso)
    dati = bytes(d["contenuto"])
    scritti = 0
    with sh._apri(s) as c:
        if estrai:
            if d["tipo"] != "zip":
                raise ErroreCustode("Solo un archivio zip si puo' estrarre come cartella")
            try:
                z = zipfile.ZipFile(io.BytesIO(dati))
            except zipfile.BadZipFile:
                raise ErroreCustode("Archivio zip non valido") from None
            tot = 0
            c.crea_cartella(dest)
            for i in z.infolist():
                if i.is_dir():
                    continue
                nome = i.filename.replace("\\", "/")
                if nome.startswith("/") or ".." in nome.split("/"):
                    raise ErroreCustode("L'archivio contiene percorsi non ammessi: mi fermo")
                tot += i.file_size
                if i.file_size > MAX_FILE_BACKUP or tot > MAX_BACKUP or scritti >= MAX_FILE_N:
                    raise ErroreCustode("Archivio troppo grande da estrarre")
                p = posixpath.join(dest, nome)
                c.crea_cartella(posixpath.dirname(p))
                c.scrivi_bytes(p, z.read(i))
                scritti += 1
            esito = f"Estratti {scritti} file in {dest}"
        else:
            c.crea_cartella(posixpath.dirname(dest))
            c.scrivi_bytes(dest, dati)
            scritti = 1
            esito = f"Caricato {dest} ({len(dati)} byte)"
    sh._memorizza_impronta(conn, s)
    _log(conn, agente_id, "sito_carica", {"sito": s["nome"], "destinazione": dest[:200], "deposito": d["id"], "file": scritti})
    return esito


def crea_cartella(conn, agente_id, sito: str, percorso: str) -> str:
    s = _aperto(conn, sito)
    perc = sh.percorso_sicuro(s["percorso_base"], percorso)
    with sh._apri(s) as c:
        c.crea_cartella(perc)
    _log(conn, agente_id, "sito_cartella", {"sito": s["nome"], "percorso": perc[:200]})
    return f"Cartella pronta: {perc}"


def scrivi_diretto(conn, agente_id, sito: str, percorso: str, contenuto: str, motivo: str) -> str:
    """Il Maestro non aspetta il via libera: la copia di sicurezza del contenuto precedente resta nella modifica."""
    s = sh.carica(conn, nome=sito or "")
    if s is None or not s["attivo"]:
        raise ErroreCustode(f"Non esiste un sito attivo chiamato «{sito}»")
    r = conn.execute("INSERT INTO siti_scritture (sito_id, agente_id, percorso, contenuto, motivo) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                     (s["id"], agente_id, percorso, contenuto, motivo)).fetchone()
    esito = sh.applica(conn, r["id"], None)
    if esito["stato"] != "applicata":
        return "ERRORE: " + esito.get("errore", "")
    return "Modifica applicata" + (" (copia di sicurezza conservata)." if esito["con_copia"] else " (file nuovo: nessuna versione precedente).")


# ---------- backup ----------
def _drive_cartelle(conn, nome_sito: str):
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        raise ErroreCustode("Drive non collegato: collega un account Google con Drive nella scheda Collegamenti")
    try:
        tok = google.token_accesso(conn, account)
        radice = google.radice_valida(conn, tok)
        mia = google.cartella(tok, CARTELLA_DRIVE, radice)
        return tok, google.cartella(tok, nome_sito[:80], mia)
    except google.ErroreGoogle as e:
        raise ErroreCustode(str(e)) from None


def _carica_drive(tok: str, nome: str, genitore: str, f, byte: int) -> str:
    """Caricamento a pezzi (resumable): niente archivio intero in memoria."""
    h = {"Authorization": "Bearer " + tok}
    try:
        r = httpx.post("https://www.googleapis.com/upload/drive/v3/files", params={"uploadType": "resumable", "fields": "id"},
                       headers=h | {"X-Upload-Content-Length": str(byte)}, json={"name": nome, "parents": [genitore]}, timeout=30)
        if r.status_code >= 400 or not r.headers.get("location"):
            raise ErroreCustode(f"Drive ha rifiutato il caricamento ({r.status_code})")
        url, pos = r.headers["location"], 0
        f.seek(0)
        while True:
            pezzo = f.read(8 * 1024 * 1024)
            fine = pos + len(pezzo)
            r = httpx.put(url, content=pezzo, timeout=120, headers={"Content-Length": str(len(pezzo)), "Content-Range": f"bytes {pos}-{fine - 1}/{byte}" if pezzo else f"bytes */{byte}"})
            if r.status_code in (200, 201):
                return r.json()["id"]
            if r.status_code != 308:
                raise ErroreCustode(f"Drive ha interrotto il caricamento ({r.status_code})")
            pos = fine
    except httpx.HTTPError as e:
        raise ErroreCustode("Drive non raggiungibile durante il caricamento (" + type(e).__name__ + ")") from None


def _scarica_drive(tok: str, file_id: str, dst):
    try:
        with httpx.stream("GET", f"https://www.googleapis.com/drive/v3/files/{file_id}", params={"alt": "media"}, headers={"Authorization": "Bearer " + tok}, timeout=120) as r:
            if r.status_code >= 400:
                raise ErroreCustode(f"Drive ha risposto {r.status_code}")
            for b in r.iter_bytes():
                dst.write(b)
    except httpx.HTTPError as e:
        raise ErroreCustode("Drive non raggiungibile (" + type(e).__name__ + ")") from None


def id_custode(conn) -> int | None:
    r = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale = 'custode' LIMIT 1").fetchone()
    return r["id"] if r else None


def backup_sito(conn, s: dict) -> dict:
    """Archivia il sito, cifra con la chiave del Maestro e carica su Drive. Registra sempre l'esito."""
    quando = datetime.now(FUSO)
    nome = f"{quando:%Y-%m-%d_%H%M}.opxb"
    note = {"saltati": [], "errori": []}
    esito = {"sito": s["nome"], "ok": False, "errore": "", "file": 0, "byte": 0, "drive": None}
    try:
        with tempfile.TemporaryFile() as zf, tempfile.TemporaryFile() as cf:
            with sh._apri(s) as c:
                if s["tipo"] == "wordpress":
                    with zipfile.ZipFile(zf, "w", zipfile.ZIP_DEFLATED) as z:
                        z.writestr("wordpress.json", c.esporta())
                    n = 1
                else:
                    n, _ = _zip_cartella(c, sh.percorso_sicuro(s["percorso_base"], ""), MAX_BACKUP, note, zf)
            if n == 0:
                raise ErroreCustode("Nessun file letto" + (": " + "; ".join(note["errori"][:3]) if note["errori"] else " (cartella vuota?)"))
            cifra_file(conn, zf, cf)
            byte = cf.seek(0, 2)
            tok, cart = _drive_cartelle(conn, s["nome"])
            fid = _carica_drive(tok, nome, cart, cf, byte)
            try:
                esito["potati"] = google.pota_cartella(tok, cart, CONSERVA_COPIE_DRIVE)   # i backup piu' vecchi vanno nel cestino di Drive
            except google.ErroreGoogle:
                pass
        esito.update(ok=True, file=n, byte=byte, drive=fid)
        sh._memorizza_impronta(conn, s)
    except (ErroreCustode, sh.ErroreSito, cassaforte.CassaforteNonConfigurata) as e:
        esito["errore"] = str(e)[:300]
    except Exception as e:  # noqa: BLE001
        esito["errore"] = "Backup non riuscito (" + type(e).__name__ + ")"
    sal = "; ".join((note["saltati"] + note["errori"])[:30])[:2000] or None
    conn.execute("""INSERT INTO custode_backup (sito_id, sito_nome, nome_file, drive_file_id, byte_cifrati, file_n, ok, errore, saltati) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                 (s["id"], s["nome"], nome if esito["ok"] else None, esito["drive"], esito["byte"], esito["file"], esito["ok"], esito["errore"] or None, sal))
    _log(conn, id_custode(conn), "sito_backup", {"sito": s["nome"], "ok": esito["ok"], "file": esito["file"]})
    esito["saltati"] = len(note["saltati"]) + len(note["errori"])
    return esito


def backup_tutti(conn, solo: str | None = None) -> list[dict]:
    siti = conn.execute("SELECT id FROM siti_hosting WHERE attivo AND tipo IN ('sftp','ftp','wordpress') AND (%s::text IS NULL OR lower(nome) = lower(%s)) ORDER BY nome", (solo, solo)).fetchall()
    out = [backup_sito(conn, sh.carica(conn, r["id"])) for r in siti]
    conn.execute("DELETE FROM custode_file WHERE creato_il < NOW() - make_interval(days => %s)", (CONSERVA_GIORNI_DEPOSITO,))
    return out


def _giornata(adesso: datetime) -> str:
    return (adesso - timedelta(hours=FINESTRA_FINO_ALLE)).date().isoformat()


def da_fare(conn, adesso: datetime | None = None) -> bool:
    """Dalle 23:33 (ora italiana) alle 4 del mattino, una volta per giornata; dopo un tentativo con errori si riprova dopo mezz'ora."""
    ora = (adesso or datetime.now(FUSO)).astimezone(FUSO)
    if (conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_backup_attivo'").fetchone() or {"valore": "1"})["valore"] != "1":
        return False
    if not (ora.hour * 60 + ora.minute >= ORA_BACKUP[0] * 60 + ORA_BACKUP[1] or ora.hour < FINESTRA_FINO_ALLE):
        return False
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_backup_ultimo'").fetchone()
    if r:
        try:
            u = json.loads(r["valore"])
            if u.get("giornata") == _giornata(ora):
                if u.get("tutto_ok"):
                    return False
                if ora - datetime.fromisoformat(u["quando"]) < timedelta(minutes=30):
                    return False
        except (ValueError, KeyError):
            pass
    return True


def esegui_notturno(conn, adesso: datetime | None = None) -> dict:
    ora = (adesso or datetime.now(FUSO)).astimezone(FUSO)
    ris = backup_tutti(conn)
    ok = all(x["ok"] for x in ris)
    stato = {"giornata": _giornata(ora), "quando": ora.isoformat(), "tutto_ok": ok, "siti": len(ris), "riusciti": sum(1 for x in ris if x["ok"])}
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('custode_backup_ultimo', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (json.dumps(stato),))
    if not ok:
        guasti = "; ".join(f"{x['sito']}: {x['errore']}" for x in ris if not x["ok"])[:300]
        conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, FALSE, FALSE)", (f"Backup notturno dei siti non riuscito per {stato['siti'] - stato['riusciti']} su {stato['siti']}: {guasti}",))
    return stato


def stato(conn) -> dict:
    u = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_backup_ultimo'").fetchone()
    return {"attivo": (conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'custode_backup_attivo'").fetchone() or {"valore": "1"})["valore"] == "1",
            "ora": "%02d:%02d" % ORA_BACKUP, "ultimo": json.loads(u["valore"]) if u else None,
            "drive_collegato": bool(int(google._leggi(conn, "drive_account_id") or 0)),
            "backup": [dict(r) for r in conn.execute("SELECT id, sito_nome, nome_file, byte_cifrati, file_n, ok, errore, saltati, creato_il FROM custode_backup ORDER BY id DESC LIMIT 30").fetchall()],
            "deposito": [dict(r) for r in conn.execute("SELECT id, nome, tipo, sito_nome, byte, creato_il FROM custode_file ORDER BY id DESC LIMIT 30").fetchall()]}


def ripristina_nel_deposito(conn, agente_id, backup_id: int) -> str:
    b = conn.execute("SELECT * FROM custode_backup WHERE id = %s AND ok", (int(backup_id),)).fetchone()
    if b is None or not b["drive_file_id"]:
        raise ErroreCustode("Backup inesistente (usa backup_elenco)")
    account = int(google._leggi(conn, "drive_account_id") or 0)
    if not account:
        raise ErroreCustode("Drive non collegato")
    try:
        tok = google.token_accesso(conn, account)
    except google.ErroreGoogle as e:
        raise ErroreCustode(str(e)) from None
    with tempfile.TemporaryFile() as cf, tempfile.TemporaryFile() as zf:
        _scarica_drive(tok, b["drive_file_id"], cf)
        cf.seek(0)
        decifra_file(conn, cf, zf)
        zf.seek(0)
        dati = zf.read()
    fid = deposita(conn, f"backup-{b['sito_nome']}-{b['nome_file']}.zip", dati, "zip", b["sito_nome"], f"backup #{b['id']}")
    _log(conn, agente_id, "backup_ripristina", {"backup": b["id"], "deposito": fid})
    return f"Backup #{b['id']} di «{b['sito_nome']}» decifrato nel deposito con id {fid} ({len(dati)} byte). Per rimetterlo sul sito: sito_carica con estrai=true."


# ---------- strumenti ----------
AVVISO = ("\n\nPOTERI DEL MAESTRO DI CHIAVI: scrivi direttamente sui siti, anche in produzione (la copia del file precedente viene conservata). Con sito_scarica porti un file o una cartella (compressa) nel tuo deposito; "
          "con sito_carica metti un elemento del deposito sul sito (estrai=true per aprire uno zip come cartella); sito_crea_cartella, deposito_elenca. Ogni notte alle 23:33 il sistema salva tutti i siti su Drive in archivi cifrati con la tua chiave, "
          "che nessun altro conosce e che non devi mai rivelare. Con sito_backup lo fai subito, con backup_elenco vedi gli ultimi, con backup_ripristina decifri un backup nel deposito. "
          "Sovrascrivere o ripristinare cambia il sito vero: se la richiesta di un collega e' ambigua o rischiosa, chiedi conferma.")

STRUMENTI = [
    {"name": "sito_scarica", "description": "Porta nel deposito un file o una cartella (compressa in zip) di un sito SFTP/FTPS. Massimo 50 MB.",
     "input_schema": {"type": "object", "properties": {"sito": {"type": "string"}, "percorso": {"type": "string"}}, "required": ["sito", "percorso"]}},
    {"name": "sito_carica", "description": "Mette sul sito un elemento del deposito: come file al percorso indicato, oppure (estrai=true, solo zip) come cartella aperta. Sovrascrive i file esistenti.",
     "input_schema": {"type": "object", "properties": {"sito": {"type": "string"}, "deposito_id": {"type": "integer"}, "percorso": {"type": "string"}, "estrai": {"type": "boolean"}}, "required": ["sito", "deposito_id", "percorso"]}},
    {"name": "sito_crea_cartella", "description": "Crea una cartella (e le intermedie) su un sito SFTP/FTPS.",
     "input_schema": {"type": "object", "properties": {"sito": {"type": "string"}, "percorso": {"type": "string"}}, "required": ["sito", "percorso"]}},
    {"name": "deposito_elenca", "description": "Elenca gli elementi del tuo deposito (file e zip scaricati o ripristinati).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "sito_backup", "description": "Avvia subito il backup cifrato su Drive di un sito (o di tutti, se non indichi il nome).",
     "input_schema": {"type": "object", "properties": {"sito": {"type": "string"}}}},
    {"name": "backup_elenco", "description": "Elenca gli ultimi backup (esito, data, dimensioni, id).",
     "input_schema": {"type": "object", "properties": {"sito": {"type": "string"}}}},
    {"name": "backup_ripristina", "description": "Scarica da Drive un backup, lo decifra e lo mette nel deposito come zip (non tocca il sito).",
     "input_schema": {"type": "object", "properties": {"backup_id": {"type": "integer"}}, "required": ["backup_id"]}},
]
NOMI = {t["name"] for t in STRUMENTI}


def gestisci(conn, agente_id: int, nome: str, dati: dict) -> str:
    try:
        if nome == "sito_scarica":
            return scarica(conn, agente_id, str(dati.get("sito") or ""), str(dati.get("percorso") or ""))
        if nome == "sito_carica":
            return carica_su_sito(conn, agente_id, str(dati.get("sito") or ""), dati.get("deposito_id"), str(dati.get("percorso") or ""), bool(dati.get("estrai")))
        if nome == "sito_crea_cartella":
            return crea_cartella(conn, agente_id, str(dati.get("sito") or ""), str(dati.get("percorso") or ""))
        if nome == "deposito_elenca":
            r = conn.execute("SELECT id, nome, tipo, sito_nome, byte FROM custode_file ORDER BY id DESC LIMIT 50").fetchall()
            return "\n".join(f"#{x['id']} {x['nome']} ({x['tipo']}, {x['byte']} byte{', da ' + x['sito_nome'] if x['sito_nome'] else ''})" for x in r) or "Il deposito e' vuoto"
        if nome == "sito_backup":
            ris = backup_tutti(conn, (str(dati.get("sito") or "").strip() or None))
            if not ris:
                return "Nessun sito da salvare (serve un sito SFTP, FTPS o WordPress attivo con quel nome)"
            return "\n".join((f"«{x['sito']}»: salvato ({x['file']} file, {x['byte']} byte cifrati)" + (f", {x['saltati']} elementi saltati" if x["saltati"] else "")) if x["ok"] else f"«{x['sito']}»: NON riuscito: {x['errore']}" for x in ris)
        if nome == "backup_elenco":
            sito = str(dati.get("sito") or "").strip() or None
            r = conn.execute("SELECT id, sito_nome, ok, errore, file_n, byte_cifrati, creato_il FROM custode_backup WHERE (%s::text IS NULL OR lower(sito_nome) = lower(%s)) ORDER BY id DESC LIMIT 20", (sito, sito)).fetchall()
            return "\n".join(f"#{x['id']} {x['sito_nome']} {x['creato_il']:%d/%m/%Y %H:%M} " + (f"ok, {x['file_n']} file, {x['byte_cifrati']} byte" if x["ok"] else "NON riuscito: " + (x["errore"] or "")) for x in r) or "Nessun backup ancora"
        if nome == "backup_ripristina":
            return ripristina_nel_deposito(conn, agente_id, dati.get("backup_id"))
    except (ErroreCustode, sh.ErroreSito, cassaforte.CassaforteNonConfigurata) as e:
        return "ERRORE: " + str(e)
    except (TypeError, ValueError):
        return "ERRORE: parametri non validi"
    return "ERRORE: strumento sconosciuto"
