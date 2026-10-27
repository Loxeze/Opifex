-- Ginnasio: libreria di competenze a 5 livelli, assegnazione agli agenti, coda di formazione con graduatoria.
CREATE TABLE IF NOT EXISTS competenze (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  descrizione TEXT NOT NULL DEFAULT '',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_competenze_nome ON competenze (lower(nome));

CREATE TABLE IF NOT EXISTS competenze_livelli (
  id SERIAL PRIMARY KEY,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  livello INTEGER NOT NULL CHECK (livello BETWEEN 1 AND 5),
  corpo TEXT NOT NULL,
  descrizione TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'bozza' CHECK (stato IN ('bozza', 'approvata', 'ritirata')),
  versione INTEGER NOT NULL DEFAULT 1,
  token_usati INTEGER NOT NULL DEFAULT 0,
  verifica_il DATE,
  approvata_il TIMESTAMPTZ,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comp_livelli_attivo ON competenze_livelli (competenza_id, livello, stato) WHERE stato IN ('bozza', 'approvata');

CREATE TABLE IF NOT EXISTS agenti_competenze (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  livello INTEGER NOT NULL CHECK (livello BETWEEN 1 AND 5),
  assegnata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (agente_id, competenza_id)
);

CREATE TABLE IF NOT EXISTS richieste_formazione (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,          -- chi deve essere formato (vuoto: solo la libreria)
  competenza_id INTEGER REFERENCES competenze(id) ON DELETE SET NULL,
  competenza_nome TEXT NOT NULL,
  livello INTEGER NOT NULL CHECK (livello BETWEEN 1 AND 5),
  motivo TEXT NOT NULL DEFAULT '',
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
  origine TEXT NOT NULL DEFAULT 'manuale' CHECK (origine IN ('manuale', 'manager', 'pm', 'lacuna', 'cerimoniere')),
  richiesta_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  richiesta_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  urgenza INTEGER NOT NULL DEFAULT 2 CHECK (urgenza BETWEEN 1 AND 3),
  peso INTEGER NOT NULL DEFAULT 1,
  stato TEXT NOT NULL DEFAULT 'in_coda' CHECK (stato IN ('in_coda', 'in_corso', 'da_approvare', 'conclusa', 'annullata', 'errore')),
  ordine_manuale INTEGER,
  via_libera BOOLEAN NOT NULL DEFAULT FALSE,
  tentativi INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  token_usati INTEGER NOT NULL DEFAULT 0,
  livello_id INTEGER REFERENCES competenze_livelli(id) ON DELETE SET NULL,
  errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  avviata_il TIMESTAMPTZ,
  conclusa_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_rich_form_stato ON richieste_formazione (stato, creata_il);

-- la formazione parte in pausa: Lorenzo la attiva dopo aver misurato i costi con una prova manuale
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_attivo', '0'), ('ginnasio_budget_giornaliero', '30000')
ON CONFLICT (chiave) DO NOTHING;
