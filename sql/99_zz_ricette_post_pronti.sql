-- Due ricette di base: il copy dei post deve essere finito e copiabile; i controlli legali segnalano, non bloccano.
INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Copy dei post social: testo finito da copiare e incollare', 'social',
$$Quando si chiede il copy, il testo, la didascalia o il post per TikTok, Instagram, Facebook, LinkedIn per un reel, un video, una puntata o un contenuto. Il lettore finale e' Lorenzo, che deve solo copiare e pubblicare.$$,
$$- Ogni post e' finito: GANCIO (una riga forte: domanda, affermazione che sorprende, dubbio) + CORPO (2-4 righe brevi che aprono il tema senza svelare tutto) + INVITO ALL'AZIONE (una domanda facile a cui rispondere) + 3-6 hashtag gia' scritti con il #.
- Chi legge vedra' il reel subito dopo: il post non lo riassume, fa venire voglia di guardarlo.
- Una citazione dal parlato si usa solo se breve, forte e fedele alla trascrizione (con il suo tempo), dentro un testo completo, mai da sola.
- Tono umano e diretto, frasi corte; si adatta alla piattaforma (TikTok: gancio in prima riga e testo breve; Instagram: righe a capo e hashtag in fondo; Facebook: piu' discorsivo con una domanda che apre la conversazione).
- Una sola versione migliore per piattaforma, senza alternative tra cui scegliere.
- Documento leggibile: titolo grande per ogni reel, sottotitolo per piattaforma, ogni testo in un blocco separato introdotto da «COPIA DA QUI:» e chiuso da «FINE TESTO», linea di separazione tra i reel. Nel blocco c'e' solo il testo da pubblicare.
- Prima di consegnare ci si chiede: «se vedessi questo post nel feed, mi fermerei a guardare il reel?». Se no, si riscrive.$$,
$$- Formule come «nel reel si sente dire», «in questo video si parla di», «il podcast parla di».
- Tono da comunicato o da verbale; solo una citazione seguita da una domanda generica.
- Note, avvisi, tempi o controlli dentro il testo da incollare.
- Consegnare bozze «da sistemare»: Lorenzo non deve rielaborare niente.
- Documenti dove non si distingue dove finisce un reel e comincia l'altro, o una piattaforma e l'altra.$$,
$$- Gancio, corpo, invito all'azione e hashtag presenti in ogni testo.
- Nessuna formula vietata; citazioni fedeli alla trascrizione.
- Un testo per piattaforma, adatto alla piattaforma.
- Formato con blocchi «COPIA DA QUI / FINE TESTO» e separazioni chiare.
- Le verifiche da fare (liberatorie, nomi, dati) sono in una sezione «NOTE PER LORENZO» dopo i testi, non dentro.
- Controllo finale registrato con consegna_verifica.$$,
'social post reel video copy testo testi didascalia caption gancio hook tiktok instagram facebook linkedin puntata podcast pubblicazione hashtag invito azione', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Copy dei post social: testo finito da copiare e incollare');

INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Pareri legali e liberatorie: segnalare senza bloccare il lavoro', 'generale',
$$Quando un contenuto (reel, post, foto, testo) riguarda persone riconoscibili, citazioni, politica, dati personali o richiede liberatorie, pareri legali o compliance.$$,
$$- Il lavoro creativo si fa comunque e si consegna completo: liberatorie, pareri e verifiche non fermano la scrittura.
- Le verifiche da fare vanno in una sezione separata «NOTE PER LORENZO»: cosa manca, chi deve darlo, entro quando, e quale testo ne dipende.
- Lorenzo e' il titolare: la liberatoria del parlante e' una decisione sua. Si chiede una sola volta, in modo chiaro, e si prosegue.
- Si scrive il testo in modo che funzioni anche senza nomi, cariche o enti non verificati; non si sospende il reel per questo.
- Il parere legale dice cosa cambiare nel testo, non «sospeso»: se un punto e' a rischio si propone la versione alternativa pronta.
- Le revisioni degli specialisti sono una sola, alla fine, e correggono il testo senza ammorbidirlo.$$,
$$- Dichiarare «sospeso» o «non pubblicabile» un contenuto intero per una verifica mancante.
- Richiedere piu' volte le stesse liberatorie o riaprire un punto gia' deciso da Lorenzo.
- Che ogni specialista aggiunga cautele finche' resta un testo generico e inutilizzabile.
- Togliere dal testo tutto cio' che e' specifico e interessante.$$,
$$- Testo completo consegnato anche con verifiche aperte.
- Verifiche elencate in «NOTE PER LORENZO» con chi/cosa/quando.
- Versione alternativa pronta per i punti a rischio.
- Nessuna domanda ripetuta su cio' che Lorenzo ha gia' deciso.$$,
'liberatoria liberatorie parere legale compliance privacy diritti persone riconoscibili politica citazioni dati personali autorizzazione consenso reel post copy', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Pareri legali e liberatorie: segnalare senza bloccare il lavoro');
