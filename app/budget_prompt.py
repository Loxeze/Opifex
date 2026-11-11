"""Prompt a budget per il modello locale: il testo deve stare nella finestra di contesto, altrimenti Ollama ne taglia l'inizio in silenzio.
Qui si decide che cosa entra, per importanza, e si dice all'agente che cosa e' rimasto fuori: nessun taglio alla cieca."""

CAR_PER_TOKEN = 3.0      # stima prudente per l'italiano (meglio contare troppi token che troppo pochi)
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
