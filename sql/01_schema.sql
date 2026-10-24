-- Schema del database: Piattaforma agenti AI (Fase 1)
-- Database: PostgreSQL

-- Divisioni (le piramidi parallele: Bandi, Marketing, CRM, R&S...)
CREATE TABLE divisioni (
 id SERIAL PRIMARY KEY,
 nome TEXT NOT NULL,
 descrizione TEXT,
 attiva BOOLEAN DEFAULT TRUE,
 creata_il TIMESTAMPTZ DEFAULT NOW()
);

-- Agenti: ogni agente ha un ruolo, un livello e un modello AI
-- livello: 'referente' | 'manager' | 'operativo'
CREATE TABLE agenti (
 id SERIAL PRIMARY KEY,
 divisione_id INTEGER REFERENCES divisioni(id),
 superiore_id INTEGER REFERENCES agenti(id),
 nome TEXT NOT NULL,
 ruolo TEXT NOT NULL,
 livello TEXT NOT NULL CHECK (livello IN ('referente', 'manager', 'operativo')),
 istruzioni TEXT NOT NULL,
 modello TEXT NOT NULL DEFAULT 'claude',
 permessi JSONB DEFAULT '[]',
 attivo BOOLEAN DEFAULT TRUE,
 creato_il TIMESTAMPTZ DEFAULT NOW()
);

-- Aziende di Lorenzo: profilo e criteri di interesse per i bandi
CREATE TABLE aziende (
 id SERIAL PRIMARY KEY,
 nome TEXT NOT NULL,
 territorio TEXT,
 profilo TEXT,
 criteri_interesse TEXT,
 creata_il TIMESTAMPTZ DEFAULT NOW()
);

-- Bacheca condivisa dei compiti
-- stato: 'da_fare' | 'in_corso' | 'da_approvare' | 'approvato' | 'respinto' | 'completato'
CREATE TABLE compiti (
 id SERIAL PRIMARY KEY,
 titolo TEXT NOT NULL,
 descrizione TEXT,
 divisione_id INTEGER REFERENCES divisioni(id),
 azienda_id INTEGER REFERENCES aziende(id),
 creato_da INTEGER REFERENCES agenti(id),
 assegnato_a INTEGER REFERENCES agenti(id),
 stato TEXT NOT NULL DEFAULT 'da_fare',
 risultato TEXT,
 richiede_approvazione BOOLEAN DEFAULT FALSE,
 creato_il TIMESTAMPTZ DEFAULT NOW(),
 aggiornato_il TIMESTAMPTZ DEFAULT NOW()
);

-- Coda di approvazione: tutto cio' che aspetta il via di Lorenzo
CREATE TABLE approvazioni (
 id SERIAL PRIMARY KEY,
 compito_id INTEGER REFERENCES compiti(id),
 sintesi TEXT NOT NULL,
 decisione TEXT CHECK (decisione IN ('approvato', 'respinto', 'modifiche')),
 note_lorenzo TEXT,
 richiesta_il TIMESTAMPTZ DEFAULT NOW(),
 decisa_il TIMESTAMPTZ
);

-- Memoria degli agenti: apprendimento dalle decisioni e dalle situazioni
CREATE TABLE memoria (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 azienda_id INTEGER REFERENCES aziende(id),
 contenuto TEXT NOT NULL,
 creata_il TIMESTAMPTZ DEFAULT NOW()
);

-- Briefing del mattino e della sera
CREATE TABLE briefing (
 id SERIAL PRIMARY KEY,
 tipo TEXT CHECK (tipo IN ('mattina', 'sera')),
 contenuto TEXT NOT NULL,
 creato_il TIMESTAMPTZ DEFAULT NOW(),
 letto BOOLEAN DEFAULT FALSE
);

-- Registro di tutte le azioni degli agenti (controllo e trasparenza)
CREATE TABLE registro_azioni (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 azione TEXT NOT NULL,
 dettagli JSONB,
 creata_il TIMESTAMPTZ DEFAULT NOW()
);

-- Controllo dei costi delle API
CREATE TABLE costi_api (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 modello TEXT,
 token_input INTEGER,
 token_output INTEGER,
 costo_stimato NUMERIC(10, 4),
 creato_il TIMESTAMPTZ DEFAULT NOW()
);
