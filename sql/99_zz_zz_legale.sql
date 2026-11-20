-- 2.68: il nuovo legale. Consiglia e non blocca; non inventa (ogni fonte citata e' verificata); i fascicoli riservati li legge solo il modello locale.
ALTER TABLE agenti DROP CONSTRAINT IF EXISTS agenti_ruolo_speciale_check;
ALTER TABLE agenti ADD CONSTRAINT agenti_ruolo_speciale_check CHECK (ruolo_speciale IS NULL OR ruolo_speciale IN ('formatore', 'cerimoniere', 'custode', 'legale', 'ricercatore_legale'));

-- fascicoli: una pratica (una causa, un rapporto, una verifica) con i suoi documenti
CREATE TABLE IF NOT EXISTS legale_fascicoli (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL CHECK (char_length(titolo) BETWEEN 2 AND 160),
  tipo TEXT NOT NULL DEFAULT 'pratica' CHECK (tipo IN ('causa', 'contratto', 'pratica', 'verifica')),
  descrizione_cifrata TEXT,            -- i fatti come li racconta Lorenzo
  parti_cifrate TEXT,                  -- nomi delle parti: servono a togliere i nomi dalle ricerche online
  riservato BOOLEAN NOT NULL DEFAULT TRUE,     -- i documenti li legge solo il modello locale
  claude_ammesso BOOLEAN NOT NULL DEFAULT FALSE,   -- Lorenzo puo' permettere Claude per questo fascicolo (qualita' migliore)
  stato TEXT NOT NULL DEFAULT 'aperto' CHECK (stato IN ('aperto', 'chiuso')),
  drive_id TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- documenti letti dal legale: dal Drive «Legale» o caricati a mano
CREATE TABLE IF NOT EXISTS legale_documenti (
  id SERIAL PRIMARY KEY,
  fascicolo_id INTEGER REFERENCES legale_fascicoli(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  categoria TEXT NOT NULL DEFAULT 'altro' CHECK (categoria IN ('causa', 'rapporto', 'polizza', 'ente_pubblico', 'privato', 'fornitore', 'collaboratore', 'altro')),
  origine TEXT NOT NULL DEFAULT 'caricato' CHECK (origine IN ('drive', 'caricato')),
  drive_id TEXT UNIQUE,
  drive_modificato TEXT,
  da_archiviare BOOLEAN NOT NULL DEFAULT FALSE,   -- caricato a mano: va copiato nella sottocartella giusta del Drive
  contenuto_cifrato TEXT,             -- il file originale (solo per l'archiviazione su Drive), poi svuotato
  testo_cifrato TEXT,
  pezzi INTEGER NOT NULL DEFAULT 0,
  pezzi_letti INTEGER NOT NULL DEFAULT 0,
  appunti_cifrati TEXT,               -- JSON degli appunti raccolti pezzo per pezzo
  scheda_cifrata TEXT,                -- JSON: sintesi, parti, controparte, obblighi, scadenze, penali, riservatezza, importi
  controparte TEXT NOT NULL DEFAULT '',   -- per mostrare la scheda agli agenti che lavorano con quel cliente o fornitore (solo fuori dai fascicoli riservati)
  stato TEXT NOT NULL DEFAULT 'da_leggere' CHECK (stato IN ('da_leggere', 'in_lettura', 'letto', 'errore')),
  errore TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  letto_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS legale_documenti_stato ON legale_documenti (stato, id);

-- scadenze di contratti e pratiche: rinnovi, disdette, termini
CREATE TABLE IF NOT EXISTS legale_scadenze (
  id SERIAL PRIMARY KEY,
  documento_id INTEGER REFERENCES legale_documenti(id) ON DELETE CASCADE,
  fascicolo_id INTEGER REFERENCES legale_fascicoli(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  data DATE NOT NULL,
  avvisi TEXT NOT NULL DEFAULT '',     -- quali avvisi sono partiti: 30,7,1
  fatta BOOLEAN NOT NULL DEFAULT FALSE,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (documento_id, titolo, data)
);

-- incarichi di Lorenzo su un fascicolo («studia e imposta la difesa», «trovami una via d'uscita»)
CREATE TABLE IF NOT EXISTS legale_incarichi (
  id SERIAL PRIMARY KEY,
  fascicolo_id INTEGER NOT NULL REFERENCES legale_fascicoli(id) ON DELETE CASCADE,
  ordine TEXT NOT NULL CHECK (char_length(ordine) BETWEEN 3 AND 4000),
  stato TEXT NOT NULL DEFAULT 'in_coda' CHECK (stato IN ('in_coda', 'studio', 'ricerca', 'relazione', 'consegnato', 'errore')),
  fase TEXT NOT NULL DEFAULT '',
  studio_cifrato TEXT,                -- JSON dello studio: fatti, questioni, ricerche, domande, strategia, mosse
  ricerche_fatte INTEGER NOT NULL DEFAULT 0,
  risultato_cifrato TEXT,             -- la relazione consegnata a Lorenzo
  errore TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  consegnato_il TIMESTAMPTZ
);

-- consigli: chiesti dagli agenti, nati dalla vigilanza o dagli incarichi
CREATE TABLE IF NOT EXISTS legale_pareri (
  id SERIAL PRIMARY KEY,
  origine TEXT NOT NULL DEFAULT 'richiesta' CHECK (origine IN ('richiesta', 'vigilanza', 'lorenzo')),
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  domanda TEXT NOT NULL,
  ambito TEXT NOT NULL DEFAULT '',    -- impresa, progetto o attivita' a cui si riferisce
  consiglio TEXT NOT NULL DEFAULT '',
  perche TEXT NOT NULL DEFAULT '',
  prossimo_passo TEXT NOT NULL DEFAULT '',
  rischio TEXT NOT NULL DEFAULT 'basso' CHECK (rischio IN ('basso', 'medio', 'alto')),
  ricerche JSONB NOT NULL DEFAULT '[]',   -- domande anonime per il ricercatore, ancora da fare
  stato TEXT NOT NULL DEFAULT 'pronto' CHECK (stato IN ('in_coda', 'pronto', 'errore')),
  visto BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS legale_pareri_recenti ON legale_pareri (id DESC);

-- la biblioteca: norme, sentenze, regolamenti trovati dal ricercatore. Si cita solo cio' che e' verificato.
CREATE TABLE IF NOT EXISTS legale_fonti (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL DEFAULT 'norma' CHECK (tipo IN ('norma', 'sentenza', 'regolamento', 'prassi')),
  estremi TEXT NOT NULL,              -- «Cass. civ., sez. lav., 12/03/2021, n. 6893», «D.Lgs. 81/2015, art. 2»
  numero TEXT NOT NULL DEFAULT '',
  data_atto TEXT NOT NULL DEFAULT '',
  ente TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  ufficiale BOOLEAN NOT NULL DEFAULT FALSE,
  verificata BOOLEAN NOT NULL DEFAULT FALSE,
  verifica TEXT NOT NULL DEFAULT '',  -- com'e' andata la verifica
  fatti TEXT NOT NULL DEFAULT '',
  decisione TEXT NOT NULL DEFAULT '',
  perche_serve TEXT NOT NULL DEFAULT '',
  luogo TEXT NOT NULL DEFAULT '',     -- per i regolamenti: comune, provincia, regione
  domanda TEXT NOT NULL DEFAULT '',   -- la domanda anonima che l'ha trovata
  incarico_id INTEGER REFERENCES legale_incarichi(id) ON DELETE SET NULL,
  parere_id INTEGER REFERENCES legale_pareri(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  verificata_il TIMESTAMPTZ,
  UNIQUE (url, estremi)
);

-- le domande per Lorenzo: restano in elenco, il lavoro non si ferma
CREATE TABLE IF NOT EXISTS legale_domande (
  id SERIAL PRIMARY KEY,
  fascicolo_id INTEGER REFERENCES legale_fascicoli(id) ON DELETE CASCADE,
  incarico_id INTEGER REFERENCES legale_incarichi(id) ON DELETE SET NULL,
  domanda TEXT NOT NULL,
  risposta_cifrata TEXT,
  stato TEXT NOT NULL DEFAULT 'aperta' CHECK (stato IN ('aperta', 'risposta', 'superata')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  risposta_il TIMESTAMPTZ
);

-- cosa ha fatto il legale (per «Cosa sta facendo»)
CREATE TABLE IF NOT EXISTS legale_registro (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,
  testo TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
