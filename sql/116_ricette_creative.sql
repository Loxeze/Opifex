-- Ricette di buona pratica per grafica, foto, social e copy (modificabili da Progetti → Buone pratiche condivise).
INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Grafiche e creativita'' per social e stampa', 'grafica',
$$Quando si crea o si consegna una grafica (post, copertina, locandina, brochure, miniatura) o si adatta un'immagine a un formato.$$,
$$- Partire dal brief in una riga: obiettivo, pubblico, messaggio unico, dove verra' usata.
- Un solo messaggio e una sola gerarchia: titolo, immagine, invito all'azione.
- Usare la palette e i caratteri del marchio del cliente; testo grande e contrastato, leggibile da telefono.
- Esportare nei formati giusti con immagine_adatta (post 4:5, story 9:16, LinkedIn 1,91:1, stampa 300 dpi) e non ridimensionare a mano.
- Guardare il risultato con immagine_analizza e una domanda precisa (testo leggibile? soggetto tagliato? coerente col brief?).$$,
$$- Troppi font, troppi colori, testo piccolo su fondo mosso.
- Ingrandire un'immagine piccola (si vede la perdita di qualita').
- Consegnare senza averla guardata: tagli e testi sbordati si vedono solo cosi'.
- Usare immagini o font senza licenza; loghi deformati.$$,
$$- Brief in una riga (obiettivo, pubblico, messaggio, canale).
- Palette e font del marchio rispettati (codici esadecimali indicati).
- Formato esportato corretto con immagine_adatta; nessun ingrandimento oltre 1,5x senza dichiararlo.
- Testo leggibile a dimensione telefono e contrasto sufficiente (verificato con immagine_analizza).
- Soggetto e testo non tagliati nei ritagli.
- Fonti e licenze di immagini e font indicate.
- Controllo finale registrato con consegna_verifica.$$,
'grafica grafiche creativita locandina brochure post copertina miniatura stampa palette logo canva design immagine formato', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Grafiche e creativita'' per social e stampa');

INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Selezione e consegna di fotografie', 'foto',
$$Quando si scelgono, si controllano o si preparano fotografie (archivio NAS, Drive, shooting) per social, sito, stampa o mostre.$$,
$$- Prima l'inventario: quante foto, formati, risoluzioni, doppioni; poi la selezione.
- Ogni foto analizzata con immagine_analizza: nitidezza, luminosita', contrasto; scartare le sfocate e le sottoesposte.
- Scegliere per storia, non per quantita': una foto forte per messaggio, coerenza di luce e colore nella serie.
- Preparare le versioni con immagine_adatta ai formati d'uso; originali mai sovrascritti.
- Didascalia e credito (autore, luogo, data, permessi) per ogni foto che esce.$$,
$$- Foto con persone riconoscibili senza liberatoria o senza sapere se serve.
- Ritagli che tagliano teste, mani o il soggetto; filtri diversi in una stessa serie.
- Consegnare cartelle non ordinate o senza nomi file chiari.
- Dichiarare «alta risoluzione» senza averlo misurato.$$,
$$- Inventario con formato, dimensioni, doppioni.
- Scartate le foto sfocate o troppo scure (misurate, non a occhio).
- Selezione motivata: perche' queste e non le altre.
- Versioni per ogni formato d'uso con immagine_adatta; originali intatti.
- Credito, luogo, data e liberatorie per ogni foto con persone.
- Nomi file chiari e cartella ordinata.
- Controllo finale registrato con consegna_verifica.$$,
'foto fotografie fotografia shooting archivio nas selezione scatti immagini risoluzione liberatoria credito didascalia mostra', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Selezione e consegna di fotografie');

INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Contenuti per i social media', 'social',
$$Quando si pianificano e si scrivono post, caroselli, reel e storie per Instagram, Facebook, LinkedIn, TikTok, YouTube o X.$$,
$$- Un obiettivo per post (far conoscere, far iscrivere, far prenotare) e un solo invito all'azione.
- Il gancio sta nella prima riga: e' quello che si vede prima di «altro».
- Testo scritto per la piattaforma: lunghezze, hashtag e tono diversi da LinkedIn a TikTok.
- Calendario con data, canale, formato, testo, immagine e responsabile; coerenza di rubrica e di voce.
- Ogni testo passa da copy_controlla e ogni immagine da immagine_adatta/immagine_analizza prima di essere proposto.$$,
$$- Lo stesso testo copiato su tutti i canali.
- Hashtag a pioggia o ripetuti; link non cliccabili in didascalia su Instagram.
- Promesse o superlativi senza prova («il migliore», «garantito»).
- Pubblicare o programmare senza l'approvazione di Lorenzo.$$,
$$- Obiettivo e pubblico del post indicati.
- Testo controllato con copy_controlla per la piattaforma giusta (nessun KO).
- Invito all'azione unico e chiaro.
- Immagine nel formato giusto e leggibile da telefono.
- Hashtag pertinenti nel numero consigliato.
- Calendario con data, canale, responsabile.
- Nessuna promessa non documentata; fonti per i dati citati.
- Approvazione di Lorenzo prima della pubblicazione.
- Controllo finale registrato con consegna_verifica.$$,
'social media post carosello reel storie instagram facebook linkedin tiktok youtube calendario editoriale hashtag didascalia contenuti', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Contenuti per i social media');

INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Scrittura del copy', 'copy',
$$Quando si scrivono testi che devono convincere o informare: didascalie, pagine web, newsletter, schede prodotto, presentazioni, testi di bando brevi.$$,
$$- Partire dal lettore: chi e', cosa vuole sapere, cosa deve fare dopo.
- Una frase di promessa onesta, poi prove (numeri, fonti, esempi), poi invito all'azione.
- Frasi corte, voce attiva, parole concrete; leggibilita' Gulpease almeno 60.
- Tono coerente con il Vademecum di scrittura e con la voce del cliente.
- Passare il testo da copy_controlla e correggere i KO prima di consegnare; due versioni se serve un confronto.$$,
$$- Aggettivi vuoti e superlativi senza prova.
- Frasi oltre 30 parole; paragrafi senza respiro.
- Dati senza fonte o senza data.
- Riscrivere da capo quando basta correggere: chiedere cosa non va.$$,
$$- Lettore, obiettivo e azione desiderata dichiarati.
- Promessa e prove (numero, fonte, periodo) presenti.
- Un solo invito all'azione.
- copy_controlla senza KO e con gli avvisi valutati.
- Tono e termini coerenti con il Vademecum di scrittura.
- Controllo ortografico e dei nomi propri.
- Controllo finale registrato con consegna_verifica.$$,
'copy testo testi scrittura newsletter pagina sito scheda prodotto presentazione promessa tono leggibilita invito azione comunicazione', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Scrittura del copy');
