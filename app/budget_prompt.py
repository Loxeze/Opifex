"""Prompt a budget per il modello locale: il testo deve stare nella finestra di contesto, altrimenti Ollama ne taglia l'inizio in silenzio.
Qui si decide che cosa entra, per importanza, e si dice all'agente che cosa e' rimasto fuori: nessun taglio alla cieca."""

CAR_PER_TOKEN = 3.3      # stima prudente per l'italiano (meglio contare troppi token che troppo pochi)
MINIMO_UTILE = 500       # sotto questa misura un blocco accorciato non serve a nulla
# dal piu' importante al meno importante: cio' che riguarda QUESTA richiesta viene prima del contesto generale
PRIORITA = ["avvisi", "allegati", "elenco_agenti", "uso", "storia", "memoria", "documenti", "scheda_progetto", "competenze", "decisioni",
            "fatti_condivisi", "panoramica", "colleghi", "best_practice", "scheda_impresa", "attivita_agenti", "kpi", "allineamento"]
DALLA_CODA = {"storia"}  # della conversazione contano gli ultimi scambi, non i primi
NOMI = {"avvisi": "avvisi di sistema", "allegati": "allegati", "elenco_agenti": "elenco degli agenti", "uso": "dati d'uso", "storia": "conversazione precedente",
        "memoria": "memoria di lavoro", "documenti": "documenti", "scheda_progetto": "scheda del progetto", "competenze": "competenze del Ginnasio",
        "decisioni": "decisioni note", "fatti_condivisi": "fatti condivisi", "panoramica": "panoramica generale", "colleghi": "scambi con i colleghi",
        "best_practice": "buone pratiche", "scheda_impresa": "scheda dell'impresa", "attivita_agenti": "attivita' degli agenti", "kpi": "indicatori", "allineamento": "allineamento"}


def stima_token(testo: str) -> int:
    return int(len(testo or "") / CAR_PER_TOKEN) + 1


def componi(blocchi: list[tuple[str, str]], caratteri: int) -> tuple[list[str], list[str], list[str]]:
    """Sceglie i blocchi che stanno nel budget. Restituisce (testi nell'ordine originale, nomi omessi, nomi accorciati)."""
    ordine = sorted(range(len(blocchi)), key=lambda i: PRIORITA.index(blocchi[i][0]) if blocchi[i][0] in PRIORITA else len(PRIORITA))
    scelti: dict[int, str] = {}
    omessi, accorciati, resto = [], [], max(0, caratteri)
    for i in ordine:
        nome, testo = blocchi[i]
        if len(testo) <= resto:
            scelti[i] = testo
            resto -= len(testo)
        elif resto >= MINIMO_UTILE:
            taglio = resto - 80
            scelti[i] = ("[…inizio omesso…]\n" + testo[-taglio:]) if nome in DALLA_CODA else (testo[:taglio] + "\n[…il resto e' stato omesso…]")
            accorciati.append(nome)
            resto = 0
        else:
            omessi.append(nome)
    return [scelti[i] for i in sorted(scelti)], omessi, accorciati


def nota(omessi: list[str], accorciati: list[str]) -> str:
    if not omessi and not accorciati:
        return ""
    parti = []
    if omessi:
        parti.append("NON hai davanti: " + ", ".join(NOMI.get(n, n) for n in omessi))
    if accorciati:
        parti.append("hai solo in parte: " + ", ".join(NOMI.get(n, n) for n in accorciati))
    return ("NOTA DI SISTEMA (finestra del modello): per farti stare tutto in memoria, " + "; ".join(parti) + ". Se ti serve qualcosa che non vedi, cercalo con gli strumenti "
            "(documenti, memoria, colleghi) o dillo: NON inventare e non dare per scontato cio' che non hai letto.")


# --- strumenti a budget: un modello locale con venti strumenti e i loro avvisi non ha piu' spazio per pensare. Si offrono quelli che servono a QUESTA richiesta.
SEMPRE = {"chiedi_a_agente", "leggi_documento", "memoria_proponi", "cerca_online", "comunica_esterno", "passa_a"}


class Avvisi:
    """Raccoglie gli avvisi degli strumenti ricordando a quali strumenti si riferiscono (quelli aggiunti a «extra» subito prima)."""

    def __init__(self, extra: list):
        self.extra, self.pezzi = extra, []

    def __iadd__(self, testo: str):
        self.pezzi.append((len(self.extra), testo))
        return self

    def __str__(self) -> str:
        return "".join(t for _, t in self.pezzi)

    def __len__(self) -> int:
        return sum(len(t) for _, t in self.pezzi)

    def gruppi(self) -> list[tuple[list, str]]:
        out, prima = [], 0
        for indice, testo in self.pezzi:
            out.append((self.extra[prima:indice], testo))
            prima = indice
        if prima < len(self.extra):
            out.append((self.extra[prima:], ""))
        return out


def _radici(testo: str) -> set:
    import re
    return {p[:6] for p in re.findall(r"[a-zàèéìòù]{5,}", (testo or "").lower())}


def scegli_strumenti(gruppi: list[tuple[list, str]], richiesta: str, caratteri: int) -> tuple[list, str, list[str]]:
    """Tiene i gruppi di strumenti che stanno nel budget: prima quelli di base, poi i piu' pertinenti alla richiesta (parole in comune con nomi, descrizioni e avvisi).
    Restituisce (strumenti, avvisi, nomi degli strumenti lasciati fuori)."""
    import json
    parole = _radici(richiesta)

    def peso(g):
        return len(json.dumps(g[0], ensure_ascii=False)) + len(g[1])

    def punteggio(g):
        if any(t.get("name") in SEMPRE for t in g[0]):
            return 10_000
        testo = " ".join((t.get("name") or "").replace("_", " ") + " " + (t.get("description") or "") for t in g[0])
        nomi = _radici(" ".join((t.get("name") or "").replace("_", " ") for t in g[0]))
        return 3 * len(parole & nomi) + len(parole & _radici(testo)) + (0.5 if not g[0] else 0)   # gli avvisi senza strumenti (contesto del ruolo) pesano poco ma contano

    ordine = sorted(range(len(gruppi)), key=lambda i: (-punteggio(gruppi[i]), peso(gruppi[i])))
    tenuti, resto = set(), max(0, caratteri)
    for i in ordine:
        if peso(gruppi[i]) <= resto:
            tenuti.add(i)
            resto -= peso(gruppi[i])
    strumenti = [t for i in sorted(tenuti) for t in gruppi[i][0]]
    avvisi = "".join(gruppi[i][1] for i in sorted(tenuti))
    fuori = [t.get("name") for i in range(len(gruppi)) if i not in tenuti for t in gruppi[i][0]]
    if fuori:
        avvisi += ("\n\nSTRUMENTI NON CARICATI ORA (per lasciarti spazio di lavoro): " + ", ".join(fuori) + ". Se per questo compito ti serve uno di questi, "
                   "scrivilo chiaramente nella risposta invece di arrangiarti o inventare.")
    return strumenti, avvisi, fuori
