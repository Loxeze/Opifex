-- Verifiche di consegna degli agenti e prima ricetta di buona pratica per i video.
CREATE TABLE IF NOT EXISTS verifiche_consegna (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER,
  progetto_id INTEGER,
  lavoro TEXT NOT NULL DEFAULT '',
  esito TEXT NOT NULL CHECK (esito IN ('ok', 'bloccata')),
  voci JSONB NOT NULL DEFAULT '[]'::jsonb,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS verifiche_consegna_progetto ON verifiche_consegna (progetto_id);

INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Reel e montaggi da riprese grezze', 'video',
$$Quando si ricavano reel o brevi video da riprese grezze (parlato, interviste, eventi) a partire da una cartella su Drive.$$,
$$- Prima l'inventario: per ogni file durata, risoluzione, fps, audio presente, duplicati (stessa impronta o stessa durata).
- Trascrizione con i tempi di tutto il parlato PRIMA di scegliere i tagli (google_trascrivi).
- Montaggio guidato dal parlato: i tagli stanno nelle pause (silenzi), mai a meta' frase; stacchi di copertura sui difetti.
- Guardare i fotogrammi del risultato (inizio, tagli, fine) e confrontarli con il piano: gli errori sul punto di partenza si vedono cosi'.
- Dichiarare quanto materiale utile c'e' davvero: con poco parlato utile si fanno meno reel, non reel vuoti.
- Consegna in 4K oppure con un file XML/progetto per Premiere Pro: e' una preferenza di Lorenzo.$$,
$$- Piani di montaggio fatti solo con i tempi in secondi, senza contenuto.
- Promettere 4K nativo da riprese 1080p: dichiarare che e' ingrandito.
- Consegnare senza aver riguardato il risultato.
- Chiedere a Lorenzo accessi o formati che si possono controllare in cartella.$$,
$$- Inventario di tutti i file con durata, risoluzione, fps, duplicati.
- Trascrizione con tempi di ogni file con parlato.
- Elenco delle clip scelte con tempo di inizio e fine e motivo.
- Tagli verificati sulle pause del parlato.
- Fotogrammi di inizio, di ogni taglio e di fine rivisti.
- Formato di uscita (4K o XML per Premiere) rispettato e dichiarato se ingrandito.
- Limiti dichiarati: materiale utile, cosa non e' stato verificato.
- Controllo finale registrato con consegna_verifica.$$,
'reel montaggio video riprese grezze verticale trascrizione parlato taglio tagli pause sottotitoli premiere davinci instagram intervista', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Reel e montaggi da riprese grezze');
