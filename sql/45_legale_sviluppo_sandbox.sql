-- 1.20.0: reparti Legale e Sviluppo software, sandbox per provare il codice, doppio controllo Claude/ChatGPT
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS usa_biblioteca BOOLEAN NOT NULL DEFAULT FALSE;   -- consulta la biblioteca (testi di legge)
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS sandbox_attivo BOOLEAN NOT NULL DEFAULT FALSE;   -- puo' provare il codice nella sandbox
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS controllore_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL;   -- l'agente ChatGPT che critica le sue bozze complesse

CREATE TABLE IF NOT EXISTS sandbox_esecuzioni (
    id SERIAL PRIMARY KEY,
    agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
    linguaggio TEXT NOT NULL CHECK (linguaggio IN ('python', 'node', 'bash')),
    codice TEXT NOT NULL,
    rete BOOLEAN NOT NULL DEFAULT FALSE,
    motivo_rete TEXT,
    stato TEXT NOT NULL DEFAULT 'ok' CHECK (stato IN ('in_attesa', 'ok', 'errore', 'timeout', 'rifiutata', 'non_disponibile')),
    uscita TEXT,
    codice_uscita INTEGER,
    durata_ms INTEGER,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sandbox_esecuzioni_recenti ON sandbox_esecuzioni (id DESC);

CREATE TABLE IF NOT EXISTS revisioni_incrociate (
    id SERIAL PRIMARY KEY,
    agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
    controllore_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
    esito TEXT NOT NULL CHECK (esito IN ('ok', 'errore', 'non_disponibile')),
    token INTEGER NOT NULL DEFAULT 0,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('sandbox_attiva', 'false'), ('sandbox_immagine_python', 'python:3.12-slim'),
  ('sandbox_immagine_node', 'node:22-slim'), ('sandbox_immagine_bash', 'python:3.12-slim') ON CONFLICT (chiave) DO NOTHING;
