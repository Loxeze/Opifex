"""Estrazione del testo dai file caricati, divisione in pezzi e ricerca dei pezzi pertinenti."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader

MAX_BYTE = 15 * 1024 * 1024
MAX_CARATTERI = 2_000_000
DIMENSIONE_PEZZO = 1200
ESTENSIONI = (".pdf", ".txt", ".md", ".csv", ".docx")


class FileNonLeggibile(Exception):
    pass


def estrai_testo(nome_file: str, contenuto: bytes) -> str:
    n = nome_file.lower()
    if n.endswith(".pdf"):
        try:
            lettore = PdfReader(io.BytesIO(contenuto))
            if lettore.is_encrypted:
                raise FileNonLeggibile("Il PDF e' protetto da password")
            testo = "\n\n".join((p.extract_text() or "") for p in lettore.pages)
        except FileNonLeggibile:
            raise
        except Exception:
            raise FileNonLeggibile("PDF non leggibile")
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
    elif n.endswith((".txt", ".md", ".csv")):
        try:
            testo = contenuto.decode("utf-8")
        except UnicodeDecodeError:
            testo = contenuto.decode("latin-1")
    else:
        raise FileNonLeggibile("Formato non supportato: usa PDF, Word (.docx), TXT, MD o CSV")
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
        return []
    return conn.execute(
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
                      AND da.agente_id IN (SELECT id FROM sotto)))
           ORDER BY punteggio DESC LIMIT %(l)s""",
        {"q": q, "a": agente_id, "l": limite},
    ).fetchall()
