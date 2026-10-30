"""Estrazione del testo dai file caricati, divisione in pezzi e ricerca dei pezzi pertinenti."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from pypdf import PdfReader

MAX_BYTE = 15 * 1024 * 1024
MAX_CARATTERI = 2_000_000
DIMENSIONE_PEZZO = 1200
IMMAGINI = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
ESTENSIONI = (".pdf", ".txt", ".md", ".csv", ".tsv", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".rtf",
              ".html", ".htm", ".json", ".xml", ".eml", ".fcpxml", ".edl", ".srt", ".vtt") + tuple(IMMAGINI)
ELENCO_FORMATI = "PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), OpenDocument, RTF, HTML, JSON, XML, montaggi (xmeml, fcpxml, EDL), sottotitoli (SRT, VTT), e-mail (.eml), TXT, MD, CSV e immagini (PNG, JPG, WEBP, GIF)"


class FileNonLeggibile(Exception):
    pass


def _zip(contenuto: bytes, errore: str) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(contenuto))
    except Exception:
        raise FileNonLeggibile(errore)
    if sum(i.file_size for i in z.infolist()) > 150 * 1024 * 1024:
        raise FileNonLeggibile("File troppo grande una volta aperto")
    return z


def _tag(e) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _testi(e) -> str:
    return "".join(t.text or "" for t in e.iter() if _tag(t) == "t")


def _xlsx(contenuto: bytes) -> str:
    z = _zip(contenuto, "Foglio Excel non leggibile")
    try:
        cond = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                cond.append(_testi(si))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rel = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        fogli = []
        for sh in wb.iter():
            if _tag(sh) == "sheet":
                rid = [v for k, v in sh.attrib.items() if k.endswith("}id")]
                t = rel.get(rid[0]) if rid else None
                if t:
                    fogli.append((sh.get("name", "Foglio"), t.lstrip("/") if t.startswith("/") else "xl/" + t))
        out = []
        for nome, percorso in fogli:
            out.append(f"### Foglio «{nome}»")
            righe = 0
            for riga in ET.fromstring(z.read(percorso)).iter():
                if _tag(riga) != "row":
                    continue
                celle = []
                for c in riga:
                    if _tag(c) != "c":
                        continue
                    t = c.get("t")
                    v = next((x for x in c if _tag(x) == "v"), None)
                    if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(cond):
                        val = cond[int(v.text)]
                    elif t == "inlineStr":
                        val = _testi(c)
                    elif v is not None:
                        val = v.text or ""
                        if t == "b":
                            val = "VERO" if val == "1" else "FALSO"
                    else:
                        val = ""
                    celle.append(val.replace("\t", " ").replace("\n", " "))
                if any(celle):
                    out.append(" | ".join(celle).rstrip(" |"))
                    righe += 1
                if righe >= 20000:
                    out.append("[...foglio troncato a 20000 righe]")
                    break
        return "\n".join(out)
    except FileNonLeggibile:
        raise
    except Exception:
        raise FileNonLeggibile("Foglio Excel non leggibile")


def _pptx(contenuto: bytes) -> str:
    z = _zip(contenuto, "Presentazione non leggibile")
    try:
        def num(n):
            return int(re.sub(r"\D", "", n.rsplit("/", 1)[-1]) or 0)
        diap = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=num)
        out = []
        for i, n in enumerate(diap, 1):
            radice = ET.fromstring(z.read(n))
            par = ["".join(t.text or "" for t in p.iter() if _tag(t) == "t") for p in radice.iter() if _tag(p) == "p"]
            blocco = [f"### Diapositiva {i}"] + [x for x in par if x.strip()]
            nota = f"ppt/notesSlides/notesSlide{num(n)}.xml"
            if nota in z.namelist():
                tn = [_testi(p) for p in ET.fromstring(z.read(nota)).iter() if _tag(p) == "p"]
                tn = [x for x in tn if x.strip() and not x.strip().isdigit()]
                if tn:
                    blocco.append("Note: " + " ".join(tn))
            out.append("\n".join(blocco))
        return "\n\n".join(out)
    except FileNonLeggibile:
        raise
    except Exception:
        raise FileNonLeggibile("Presentazione non leggibile")


def _odf(contenuto: bytes) -> str:
    z = _zip(contenuto, "Documento OpenDocument non leggibile")
    try:
        radice = ET.fromstring(z.read("content.xml"))
        par = ["".join(x.itertext()) for x in radice.iter() if _tag(x) in ("p", "h")]
        return "\n".join(p for p in par if p.strip())
    except Exception:
        raise FileNonLeggibile("Documento OpenDocument non leggibile")


class _DaHtml(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parti, self.salta = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.salta += 1
        elif tag in ("p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"):
            self.parti.append("\n")
        elif tag in ("td", "th"):
            self.parti.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.salta:
            self.salta -= 1

    def handle_data(self, d):
        if not self.salta:
            self.parti.append(d)


def _decodifica(contenuto: bytes) -> str:
    try:
        return contenuto.decode("utf-8")
    except UnicodeDecodeError:
        return contenuto.decode("latin-1")


def _eml(contenuto: bytes) -> str:
    from email import message_from_bytes, policy
    try:
        m = message_from_bytes(contenuto, policy=policy.default)
        corpo = m.get_body(preferencelist=("plain", "html"))
        t = corpo.get_content() if corpo else ""
        if corpo is not None and corpo.get_content_type() == "text/html":
            p = _DaHtml(); p.feed(t); t = "".join(p.parti)
        return f"Da: {m['from']}\nA: {m['to']}\nOggetto: {m['subject']}\nData: {m['date']}\n\n{t}"
    except Exception:
        raise FileNonLeggibile("E-mail non leggibile")


def estrai_testo(nome_file: str, contenuto: bytes, visione=None) -> str:
    """visione: funzione facoltativa fn([(mime, byte)]) -> testo, per immagini e PDF scansionati."""
    n = nome_file.lower()
    estensione = n[n.rfind("."):] if "." in n else ""
    if estensione in IMMAGINI:
        if visione is None:
            raise FileNonLeggibile("Per leggere le immagini serve il lettore visivo (chiave Anthropic)")
        try:
            testo = visione([(IMMAGINI[estensione], contenuto)])
        except Exception as e:
            raise FileNonLeggibile(str(e) or "Immagine non leggibile")
    elif n.endswith(".pdf"):
        try:
            lettore = PdfReader(io.BytesIO(contenuto))
            if lettore.is_encrypted:
                raise FileNonLeggibile("Il PDF e' protetto da password")
            testo = "\n\n".join((p.extract_text() or "") for p in lettore.pages)
            if len(testo.strip()) < 20 and visione is not None:
                # scansione: leggo le immagini delle prime pagine
                imm = []
                for p in lettore.pages[:8]:
                    for im in p.images:
                        mime = "image/png" if im.name.lower().endswith(".png") else "image/jpeg"
                        imm.append((mime, im.data))
                        break
                if imm:
                    try:
                        testo = visione(imm)
                    except Exception as e:
                        raise FileNonLeggibile(str(e) or "Scansione non leggibile")
        except FileNonLeggibile:
            raise
        except Exception:
            raise FileNonLeggibile("PDF non leggibile")
    elif n.endswith(".xlsx"):
        testo = _xlsx(contenuto)
    elif n.endswith(".pptx"):
        testo = _pptx(contenuto)
    elif n.endswith((".odt", ".ods", ".odp")):
        testo = _odf(contenuto)
    elif n.endswith(".rtf"):
        t = _decodifica(contenuto)
        t = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), t)
        t = re.sub(r"\\par[d]?", "\n", t)
        t = re.sub(r"\{\\\*[^{}]*\}|\\[a-z]+-?\d* ?|[{}]", "", t)
        testo = t
    elif n.endswith((".html", ".htm")):
        p = _DaHtml(); p.feed(_decodifica(contenuto)); testo = "".join(p.parti)
    elif n.endswith(".eml"):
        testo = _eml(contenuto)
    elif n.endswith((".json", ".xml", ".fcpxml", ".edl", ".srt", ".vtt")):
        from . import montaggio_xml
        try:
            testo = montaggio_xml.analizza(nome_file, contenuto) or _decodifica(contenuto)
        except montaggio_xml.MontaggioNonLeggibile as e:
            raise FileNonLeggibile(str(e)) from None
    elif n.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(contenuto)) as z:
                if sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024:
                    raise FileNonLeggibile("File troppo grande una volta aperto")
                radice = ET.fromstring(z.read("word/document.xml"))
        except FileNonLeggibile:
            raise
        except Exception:
            raise FileNonLeggibile("Documento Word non leggibile")
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragrafi = ["".join(t.text or "" for t in p.iter(ns + "t")) for p in radice.iter(ns + "p")]
        testo = "\n\n".join(paragrafi)
    elif n.endswith((".txt", ".md", ".csv", ".tsv")):
        try:
            testo = contenuto.decode("utf-8")
        except UnicodeDecodeError:
            testo = contenuto.decode("latin-1")
    else:
        raise FileNonLeggibile("Formato non supportato: usa " + ELENCO_FORMATI)
    testo = testo.replace("\x00", "")
    testo = re.sub(r"[ \t]+", " ", testo)
    testo = re.sub(r"\n{3,}", "\n\n", testo).strip()
    if len(testo) < 20:
        raise FileNonLeggibile("Nessun testo estraibile (se e' una scansione serve prima il riconoscimento del testo)")
    if len(testo) > MAX_CARATTERI:
        raise FileNonLeggibile("Documento troppo lungo (oltre 2 milioni di caratteri)")
    return testo


def dividi_in_pezzi(testo: str) -> list[str]:
    pezzi, corrente = [], ""
    for par in re.split(r"\n\s*\n", testo):
        while len(par) > DIMENSIONE_PEZZO:  # paragrafi enormi: taglio per lunghezza
            taglio = par.rfind(" ", 0, DIMENSIONE_PEZZO)
            taglio = taglio if taglio > 200 else DIMENSIONE_PEZZO
            if corrente:
                pezzi.append(corrente); corrente = ""
            pezzi.append(par[:taglio].strip()); par = par[taglio:].strip()
        if len(corrente) + len(par) + 2 > DIMENSIONE_PEZZO and corrente:
            pezzi.append(corrente); corrente = par
        else:
            corrente = (corrente + "\n\n" + par).strip()
    if corrente:
        pezzi.append(corrente)
    return [p for p in pezzi if p]


def query_ricerca(messaggio: str) -> str | None:
    """Trasforma il messaggio in una ricerca 'una qualsiasi di queste parole' (solo lettere e cifre, nessun operatore)."""
    parole = []
    for p in re.findall(r"[^\W_]{4,}", messaggio.lower()):
        if p not in parole:
            parole.append(p)
    return " | ".join(parole[:15]) or None


def pezzi_pertinenti(conn, agente_id: int, messaggio: str, limite: int = 4) -> list[dict]:
    q = query_ricerca(messaggio)
    if q is None:
        return _con_significato(conn, agente_id, messaggio, [], limite)
    righe = conn.execute(
        """WITH RECURSIVE sotto(id) AS (
               -- l'agente stesso e tutti quelli sotto di lui nella gerarchia (UNION evita cicli infiniti):
               -- un documento assegnato a un agente e' consultabile anche da tutti i suoi superiori
               SELECT %(a)s::int
               UNION
               SELECT a.id FROM agenti a JOIN sotto s ON a.superiore_id = s.id)
           SELECT d.id AS documento_id, d.nome, d.fascia_dati, p.testo,
                  ts_rank_cd(p.ricerca, to_tsquery('italian', %(q)s)) AS punteggio
           FROM pezzi_documenti p JOIN documenti d ON d.id = p.documento_id
           WHERE p.ricerca @@ to_tsquery('italian', %(q)s)
             AND (d.per_tutti OR EXISTS (
                    SELECT 1 FROM documenti_agenti da
                    WHERE da.documento_id = d.id
                      AND da.agente_id IN (SELECT id FROM sotto))
                 OR EXISTS (
                    SELECT 1 FROM progetti_documenti pd JOIN progetti_agenti pa ON pa.progetto_id = pd.progetto_id
                    JOIN progetti pr ON pr.id = pd.progetto_id AND NOT pr.archiviato AND pr.eliminato_il IS NULL
                    WHERE pd.documento_id = d.id AND pa.agente_id IN (SELECT id FROM sotto)))
           ORDER BY punteggio DESC LIMIT %(l)s""",
        {"q": q, "a": agente_id, "l": limite},
    ).fetchall()
    return _con_significato(conn, agente_id, messaggio, righe, limite)


def _con_significato(conn, agente_id: int, messaggio: str, per_parole: list[dict], limite: int) -> list[dict]:
    """Aggiunge la ricerca per significato (vettori) a quella per parole; se non e' disponibile resta quella per parole."""
    try:
        from . import memoria_vettoriale as mv
        sig = mv.cerca(conn, agente_id, messaggio, limite + 2)
        return mv.unisci(per_parole, sig, limite) if sig else per_parole
    except Exception:  # noqa: BLE001 - la memoria vettoriale non deve mai bloccare un agente
        return per_parole


def lettore_visivo(fascia: str = "interno"):
    """Funzione da passare a estrai_testo per leggere immagini e scansioni (usa il modello con la vista)."""
    def _l(immagini):
        from . import visione
        try:
            return visione.leggi(immagini, fascia)
        except visione.VisioneNonDisponibile as e:
            raise FileNonLeggibile(str(e))
    return _l
