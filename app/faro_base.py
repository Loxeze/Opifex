"""FARO: dotazione di partenza. Le fonti vengono dal censimento gia' usato nei flussi n8n di FARO (portali nazionali, ministeri e agenzie, regioni);
i profili dai criteri dettati da Lorenzo il 12 novembre 2026. Tutto si modifica dalla pagina Bandi: qui c'e' solo cio' che serve per partire."""

CATEGORIE = ["Cultura e Patrimonio", "Turismo", "Digitale e IoT", "Terzo Settore e Inclusione Sociale", "Ricerca e Innovazione",
             "Cooperazione Internazionale ed Europrogettazione", "Formazione", "Creazione Impresa", "Acquisto Macchinari e Strumenti", "Incentivi"]

# (nome, url, categoria della fonte, regione o None)
FONTI = [
    # portali nazionali ed europei
    ("Incentivi.gov.it", "https://www.incentivi.gov.it/", "Portali nazionali", None),
    ("OpenCoesione – Opportunità 2021-2027", "https://opencoesione.gov.it/it/opportunita_2021_2027/", "Portali nazionali", None),
    ("Italia Domani – Bandi e avvisi dei titolari", "https://www.italiadomani.gov.it/content/sogei-ng/it/it/opportunita/bandi-amministrazioni-titolari.html", "Portali nazionali", None),
    ("Italia Domani – Bandi dei soggetti attuatori", "https://www.italiadomani.gov.it/content/sogei-ng/it/it/opportunita/bandi-soggetti-attuatori.html", "Portali nazionali", None),
    ("Funding & Tenders Portal (Commissione europea)", "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home", "Programmi europei", None),
    ("Dipartimento Politiche di Coesione – Avvisi", "https://politichecoesione.governo.it/it/bandi-e-avvisi/", "Portali nazionali", None),
    ("Rete PAC – Bandi LEADER", "https://www.reterurale.it/leader20142020/leaderitalia/bandi", "Portali nazionali", None),
    ("Europa Creativa – Cultura", "https://www.europacreativa-cultura.it/", "Programmi europei", None),
    ("Interreg Italia-Francia Marittimo", "https://interreg-maritime.eu/", "Programmi europei", None),
    # ministeri e agenzie
    ("Ministero della Cultura – Bandi e concorsi", "https://cultura.gov.it/comunicati/bandi-e-concorsi", "Ministeri e agenzie", None),
    ("PNRR Cultura – Bandi e avvisi", "https://pnrr.cultura.gov.it/bandi-e-avvisi/", "Ministeri e agenzie", None),
    ("MiC – Istituti culturali", "https://istituticulturali.cultura.gov.it/", "Ministeri e agenzie", None),
    ("Direzione Generale Cinema e Audiovisivo", "https://cinema.cultura.gov.it/comunicazione/bandi-aperti-e-prossime-scadenze/", "Ministeri e agenzie", None),
    ("Ministero del Turismo – Avvisi pubblici", "https://www.ministeroturismo.gov.it/avvisi-pubblici/", "Ministeri e agenzie", None),
    ("MIMIT – Incentivi", "https://www.mimit.gov.it/it/incentivi", "Ministeri e agenzie", None),
    ("MASE – Bandi e avvisi", "https://www.mase.gov.it/portale/bandi-e-avvisi", "Ministeri e agenzie", None),
    ("MUR – Concorsi e avvisi", "https://www.mur.gov.it/it/ministero/concorsi-e-avvisi", "Ministeri e agenzie", None),
    ("MUR – Bandi a cascata PNRR", "https://www.mur.gov.it/it/pnrr/attuazione-misure-pnrr/bandi-cascata", "Ministeri e agenzie", None),
    ("Ministero del Lavoro – Terzo settore, avvisi e bandi", "https://www.lavoro.gov.it/temi-e-priorita/terzo-settore-e-responsabilita-sociale-imprese/focus-on/avvisi-pubblici-e-bandi/pagine/default", "Ministeri e agenzie", None),
    ("Ministero dell'Istruzione e del Merito – Avvisi PN 2021-2027", "https://pn20212027.istruzione.it/avvisi/", "Ministeri e agenzie", None),
    ("AICS – Cooperazione allo sviluppo, bandi", "https://www.aics.gov.it/home-ita/opportunita/bandi/", "Ministeri e agenzie", None),
    ("Invitalia", "https://www.invitalia.it/cosa-facciamo/rafforziamo-le-imprese", "Ministeri e agenzie", None),
    ("SIMEST – Finanziamenti agevolati", "https://www.simest.it/per-le-imprese/finanziamenti-agevolati-pnrr/", "Ministeri e agenzie", None),
    ("ICE – Eventi e opportunità", "https://www.ice.it/it/settori/eventi-opportunita", "Ministeri e agenzie", None),
    ("GSE – Servizi e incentivi", "https://www.gse.it/servizi-per-te", "Ministeri e agenzie", None),
    ("Agenzia Nazionale per i Giovani – Bandi", "https://agenziagioventu.gov.it/bandi/", "Ministeri e agenzie", None),
    ("ENEA – Bandi e gare", "https://www.enea.it/it/opportunita/bandi-e-gare", "Ministeri e agenzie", None),
    ("ANCI – Bandi", "https://www.anci.it/category/bandi/", "Ministeri e agenzie", None),
    # fondazioni
    ("Fondazione CON IL SUD – Bandi e iniziative", "https://www.fondazioneconilsud.it/bandi-e-iniziative/", "Fondazioni", None),
    ("Fondazione Compagnia di San Paolo", "https://www.compagniadisanpaolo.it/", "Fondazioni", None),
    ("Infobandi CSVnet", "https://infobandi.csvnet.it/", "Fondazioni", None),
    ("Fondazione CHANGES", "https://www.fondazionechanges.org", "Fondazioni", None),
    # regioni e province autonome
    ("Regione Liguria – Bandi e avvisi", "https://www.regione.liguria.it/homepage-bandi-e-avvisi/publiccompetitions.html", "Regioni", "Liguria"),
    ("FILSE – Bandi online", "https://filseonline.regione.liguria.it/", "Regioni", "Liguria"),
    ("Regione Toscana – Bandi aperti", "https://www.regione.toscana.it/bandi-aperti", "Regioni", "Toscana"),
    ("Regione Campania – PR FESR", "https://prfesr2127.regione.campania.it/opportunita/bandi-e-avvisi/", "Regioni", "Campania"),
    ("Regione Lombardia – Bandi e Servizi", "https://www.bandi.regione.lombardia.it/servizi/servizio/bandi", "Regioni", "Lombardia"),
    ("Regione Piemonte – Contributi e finanziamenti", "https://bandi.regione.piemonte.it/contributi-finanziamenti", "Regioni", "Piemonte"),
    ("Regione Emilia-Romagna – PR FESR", "https://fesr.regione.emilia-romagna.it/opportunita/bandi", "Regioni", "Emilia-Romagna"),
    ("Regione Veneto – Bandi e finanziamenti", "https://bandi.regione.veneto.it/Public/Elenco?Tipo=1", "Regioni", "Veneto"),
    ("Lazio Europa – Ricerca bandi", "https://www.lazioeuropa.it/bandi/", "Regioni", "Lazio"),
    ("Regione Abruzzo – Avvisi pubblici", "https://www.regione.abruzzo.it/content/avvisi-pubblici", "Regioni", "Abruzzo"),
    ("Regione Basilicata – Portale bandi", "https://portalebandi.regione.basilicata.it/", "Regioni", "Basilicata"),
    ("Regione Calabria – Calabria Europa", "https://calabriaeuropa.regione.calabria.it/bandi/", "Regioni", "Calabria"),
    ("Regione Friuli Venezia Giulia – Bandi e avvisi", "https://www.regione.fvg.it/rafvg/cms/RAFVG/MODULI/bandi_avvisi/", "Regioni", "Friuli Venezia Giulia"),
    ("Regione Marche – Fondi europei, bandi", "https://www.regione.marche.it/Entra-in-Regione/Fondi-Europei/Bandi", "Regioni", "Marche"),
    ("Molise in Europa – Avvisi e bandi", "https://moliseineuropa.regione.molise.it/avvisi", "Regioni", "Molise"),
    ("Regione Puglia – Catalogo bandi", "https://sistema.regione.puglia.it/catalogo-bandi", "Regioni", "Puglia"),
    ("Regione Sardegna – Bandi", "https://www.regione.sardegna.it/atti-bandi-archivi/atti-amministrativi/bandi", "Regioni", "Sardegna"),
    ("Regione Siciliana – Bandi", "https://www.regione.sicilia.it/istituzioni/servizi-informativi/bandi", "Regioni", "Sicilia"),
    ("Regione Umbria – Bandi", "https://www.regione.umbria.it/la-regione/bandi", "Regioni", "Umbria"),
    ("Regione Valle d'Aosta – Portale imprese, bandi", "https://imprese.regione.vda.it/bandi", "Regioni", "Valle d'Aosta"),
    ("Provincia autonoma di Trento – Aiuti alle imprese", "https://www.provincia.tn.it/Argomenti/Focus/Aiuti-alle-imprese", "Regioni", "Trentino-Alto Adige"),
    ("Europa Bolzano – Bandi e avvisi", "https://europa.provincia.bz.it/it/bandi-e-avvisi", "Regioni", "Trentino-Alto Adige"),
]

REGOLE = ("Regole di Lorenzo: si scartano i bandi con contributo sotto la soglia minima; se il contributo copre meno della percentuale minima dei costi il bando e' «da valutare» caso per caso.")

# (nome del profilo, tipo, nome dell'impresa a cui legarlo o None, descrizione, regioni, importo minimo, copertura minima, attivo)
MENSILI = ("Nuove imprese",)   # sezione a parte, da guardare una volta al mese

PROFILI = [
    ("Renovatio", "impresa", "Renovatio",
     "Associazione Renovatio ETS/ODV: ente del terzo settore che fa promozione culturale e valorizzazione del patrimonio, con collaborazioni internazionali e universitarie. "
     "Tre sedi: Genova (Liguria), Castello di Montarrenti a Sovicille (Toscana), Sessa Aurunca (Campania). Qualsiasi finanziamento per la promozione culturale e' pertinente. "
     "Il Castello di Montarrenti e' della Provincia di Siena, in gestione al Comune di Sovicille che lo ha affidato a Renovatio: per questo Renovatio puo' entrare come partner "
     "anche in bandi riservati a comuni o province.",
     "Liguria, Toscana, Campania, nazionale, europeo", 5000, 50, True),
    ("Logos", "impresa", "Logos",
     "Logos di Lorenzo Zeppa: ditta artigiana individuale con sede in Liguria (Genova) che produce video di alta qualita' e comunicazione per musei, enti e imprese. "
     "Interessano i bandi per promozione, video, azioni di marketing e soprattutto digitalizzazione dell'impresa.",
     "Liguria, nazionale", 5000, 50, True),
    ("Aquilia", "impresa", "Aquilia",
     "Aquilia S.r.l.: startup innovativa con sede a Laigueglia (Liguria), digitalizzazione e produzione di software e hardware digitale, anche in ambito culturale. "
     "Presenta anche il progetto Evidens (container intelligenti con IoT, produzione di energia e accumulo in batterie). Interessano: bandi per startup, sviluppo di prototipi, "
     "progetti pilota, progetti europei, call di incubatori e acceleratori, anche con equity. Vanno bene tutte le regioni italiane purche' il bando ammetta di aprire "
     "una sede operativa dopo l'aggiudicazione.",
     "tutte le regioni (con sede operativa da aprire dopo l'aggiudicazione), nazionale, europeo", 5000, 50, True),
    ("Filigrana", "impresa", "Filigrana",
     "Filigrana S.r.l.: startup innovativa di Campo Ligure (Liguria), e-commerce di gioielli artigianali in filigrana che valorizza il territorio legando il prodotto al luogo. "
     "La socia e' una donna sotto i 35 anni: valgono i bandi per imprenditoria femminile e giovanile, oltre a quelli per startup, artigianato, e-commerce e digitalizzazione.",
     "Liguria, nazionale", 5000, 50, True),
    ("Nuove imprese", "impresa", None,
     "Sezione separata, da guardare una volta al mese: bandi e fondi per COSTITUIRE nuove startup o nuove imprese (non per quelle gia' esistenti). "
     "Lorenzo e' disposto a costituire una nuova societa' se ci sono fondi per farlo, in ambito culturale, digitale, deeptech o turistico. Non mescolarli con gli altri profili.",
     "tutte le regioni, nazionale, europeo", 5000, 50, True),
    ("Piccolo museo locale", "esterno", None,
     "Profilo tipo per il bollettino ai piccoli musei: museo civico, locale o ecclesiastico, o associazione che lo gestisce, con poco personale e bilancio ridotto. "
     "Interessano contributi per funzionamento, allestimenti, digitalizzazione, catalogazione, accessibilita', didattica, eventi e promozione, restauri, efficienza energetica; "
     "anche bandi in cui il museo entra come partner di un comune o di un'associazione.",
     "tutte le regioni, nazionale", 2000, 50, False),
]
