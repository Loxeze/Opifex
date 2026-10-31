"""Stile unico dei documenti e dei fogli prodotti dagli agenti.
- documento: testo in Markdown semplice -> HTML con stile inline (Google lo importa mantenendo titoli, tabelle, colori);
- foglio: richieste di formattazione per l'API Sheets (intestazione verde, righe alternate, riga bloccata, colonne adattate).
Nessuna dipendenza esterna. Il testo dell'agente e' sempre escapato: non puo' inserire HTML."""
import html
import re

VERDE = "#1F4D43"
OTTONE = "#B07A10"
INCHIOSTRO = "#1B2421"
GRIGIO = "#5B6560"
AVORIO = "#F5F2EB"
FONT = "Georgia, 'Times New Roman', serif"
FONT_TESTO = "Arial, Helvetica, sans-serif"

REGOLE_STILE = (
    "STILE DEI FILE CHE PRODUCI (vale per ogni documento e foglio): "
    "1) Scrivi in Markdown: '# Titolo' una sola volta in alto, '## Sezione', '### Sottosezione', elenchi con '- ', tabelle con '| a | b |', **grassetto**. "
    "2) Apri con una riga di contesto (per chi, data, scopo) e poi '## In sintesi': 3-5 punti con le conclusioni e i numeri chiave, prima di tutto il resto. "
    "3) Poi sezioni brevi con titolo; i confronti e i numeri vanno in tabella, mai in paragrafi lunghi. "
    "4) Ogni dato ha unita', periodo e fonte; distingui FATTO (verificato), STIMA (calcolata, con il metodo) e IPOTESI (da verificare). "
    "5) Chiudi con '## Prossimi passi' (chi fa cosa, entro quando) e '## Fonti'. "
    "6) Frasi corte, voce attiva, niente riempitivi ne' preamboli; italiano corretto, numeri in formato italiano (1.234,50). "
    "7) Fogli: prima riga = intestazioni chiare con l'unita' di misura, una sola tabella per foglio, niente righe vuote, nessun dato fuso nella stessa cella; "
    "numeri come numeri, mai come testo con simboli. Evita file senza titolo, senza sintesi o con testo non strutturato."
)

_INL = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)"), r"<i>\1</i>"),
    (re.compile(r"`([^`]+)`"), r"<span style=\"font-family:Courier New,monospace;background:#EFEBE0\">\1</span>"),
]


def _inline(t: str) -> str:
    t = html.escape(t.strip())
    for rx, sost in _INL:
        t = rx.sub(sost, t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", lambda m: f'<a href="{m.group(2)}" style="color:{VERDE}">{m.group(1)}</a>', t)
    return t


def _cella_tabella(riga: str) -> list[str]:
    r = riga.strip()
    if r.startswith("|"):
        r = r[1:]
    if r.endswith("|"):
        r = r[:-1]
    return [c.strip() for c in r.split("|")]


def _tabella(righe: list[str]) -> str:
    celle = [_cella_tabella(r) for r in righe if not re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", r)]
    if not celle:
        return ""
    n = max(len(r) for r in celle)
    out = [f'<table style="border-collapse:collapse;width:100%;margin:8px 0 14px;font-family:{FONT_TESTO};font-size:10pt">']
    for i, r in enumerate(celle):
        r = r + [""] * (n - len(r))
        out.append("<tr>")
        for c in r:
            if i == 0:
                out.append(f'<td style="background:{VERDE};color:#FFFFFF;font-weight:bold;padding:6px 8px;border:1px solid {VERDE}">{_inline(c)}</td>')
            else:
                fondo = AVORIO if i % 2 == 0 else "#FFFFFF"
                allinea = "right" if re.fullmatch(r"[-+€$%\d.,\s]+[%€]?", c or "x") else "left"
                out.append(f'<td style="background:{fondo};padding:5px 8px;border:1px solid #D9D3C3;text-align:{allinea}">{_inline(c)}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def markdown_a_html(testo: str, titolo: str = "") -> str:
    """Converte Markdown semplice in HTML con stile inline."""
    righe = str(testo or "").replace("\r\n", "\n").split("\n")
    out, i, primo_titolo = [], 0, False
    while i < len(righe):
        r = righe[i]
        s = r.strip()
        if not s:
            i += 1
            continue
        if s.startswith("|"):
            blocco = []
            while i < len(righe) and righe[i].strip().startswith("|"):
                blocco.append(righe[i])
                i += 1
            out.append(_tabella(blocco))
            continue
        m = re.match(r"(#{1,3})\s+(.*)", s)
        if m:
            liv, t = len(m.group(1)), m.group(2)
            if liv == 1:
                primo_titolo = True
                out.append(f'<h1 style="font-family:{FONT};font-size:24pt;color:{VERDE};margin:0 0 4px">{_inline(t)}</h1>'
                           f'<div style="border-bottom:3px solid {OTTONE};margin:0 0 12px"></div>')
            elif liv == 2:
                out.append(f'<h2 style="font-family:{FONT};font-size:15pt;color:{VERDE};margin:18px 0 4px;border-bottom:1px solid #D9D3C3">{_inline(t)}</h2>')
            else:
                out.append(f'<h3 style="font-family:{FONT};font-size:12pt;color:{OTTONE};margin:12px 0 2px">{_inline(t)}</h3>')
            i += 1
            continue
        if re.match(r"[-*•]\s+", s) or re.match(r"\d+[.)]\s+", s):
            ordinato = bool(re.match(r"\d+[.)]\s+", s))
            voci = []
            while i < len(righe) and (re.match(r"\s*[-*•]\s+", righe[i]) or re.match(r"\s*\d+[.)]\s+", righe[i])):
                voci.append(re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", righe[i]))
                i += 1
            tag = "ol" if ordinato else "ul"
            out.append(f'<{tag} style="font-family:{FONT_TESTO};font-size:11pt;color:{INCHIOSTRO};margin:4px 0 10px">'
                       + "".join(f"<li style=\"margin:2px 0\">{_inline(v)}</li>" for v in voci) + f"</{tag}>")
            continue
        if s.startswith(">"):
            q = []
            while i < len(righe) and righe[i].strip().startswith(">"):
                q.append(righe[i].strip().lstrip(">").strip())
                i += 1
            out.append(f'<p style="font-family:{FONT_TESTO};font-size:11pt;background:{AVORIO};border-left:4px solid {OTTONE};padding:8px 12px;margin:8px 0">'
                       + _inline(" ".join(q)) + "</p>")
            continue
        par = [s]
        i += 1
        while i < len(righe) and righe[i].strip() and not re.match(r"\s*(#{1,3}\s|[-*•]\s|\d+[.)]\s|\||>)", righe[i]):
            par.append(righe[i].strip())
            i += 1
        out.append(f'<p style="font-family:{FONT_TESTO};font-size:11pt;line-height:1.5;color:{INCHIOSTRO};margin:0 0 8px">{_inline(" ".join(par))}</p>')
    if not primo_titolo and titolo:
        out.insert(0, f'<h1 style="font-family:{FONT};font-size:24pt;color:{VERDE};margin:0 0 4px">{html.escape(titolo)}</h1>'
                      f'<div style="border-bottom:3px solid {OTTONE};margin:0 0 12px"></div>')
    return f"<html><body>{''.join(out)}</body></html>"


def _rgb(h: str) -> dict:
    return {"red": int(h[1:3], 16) / 255, "green": int(h[3:5], 16) / 255, "blue": int(h[5:7], 16) / 255}


def richieste_foglio(sheet_id: int, n_righe: int, n_colonne: int) -> list[dict]:
    """batchUpdate per rendere leggibile un foglio: intestazione verde, riga bloccata, righe alternate, colonne adattate, bordi leggeri."""
    n_righe, n_colonne = max(n_righe, 1), max(n_colonne, 1)
    tutto = {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": n_righe, "startColumnIndex": 0, "endColumnIndex": n_colonne}
    testa = {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": n_colonne}
    r = [
        {"repeatCell": {"range": tutto, "cell": {"userEnteredFormat": {
            "textFormat": {"fontFamily": "Arial", "fontSize": 10, "foregroundColor": _rgb(INCHIOSTRO)}, "verticalAlignment": "MIDDLE", "wrapStrategy": "CLIP"}},
            "fields": "userEnteredFormat(textFormat,verticalAlignment,wrapStrategy)"}},
        {"repeatCell": {"range": testa, "cell": {"userEnteredFormat": {
            "backgroundColor": _rgb(VERDE), "horizontalAlignment": "CENTER", "wrapStrategy": "WRAP",
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": _rgb("#FFFFFF")}}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,wrapStrategy,textFormat)"}},
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                                       "properties": {"pixelSize": 34}, "fields": "pixelSize"}},
        {"updateBorders": {"range": tutto, "innerHorizontal": {"style": "SOLID", "color": _rgb("#D9D3C3")},
                           "bottom": {"style": "SOLID", "color": _rgb("#D9D3C3")}}},
        {"autoResizeDimensions": {"dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": n_colonne}}},
    ]
    if n_righe > 2:
        r.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": n_righe, "startColumnIndex": 0, "endColumnIndex": n_colonne}],
            "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]},
                            "format": {"backgroundColor": _rgb("#F5F2EB")}}}}})
    return r
