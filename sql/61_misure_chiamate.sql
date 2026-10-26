-- Misure per capire dove vanno i token: una riga per ogni risposta di un agente (o dialogo tra colleghi).
-- I "car_*" sono caratteri (circa 3,5 per token) di cio' che e' stato mandato al modello, per componente.
CREATE TABLE IF NOT EXISTS misure_chiamate (
 id BIGSERIAL PRIMARY KEY,
 creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
 modello TEXT,
 origine TEXT NOT NULL DEFAULT 'altro',
 token_input INTEGER NOT NULL DEFAULT 0,
 token_output INTEGER NOT NULL DEFAULT 0,
 costo NUMERIC(10, 5) NOT NULL DEFAULT 0,
 passi INTEGER NOT NULL DEFAULT 1,
 secondi NUMERIC(8, 2),
 n_strumenti INTEGER NOT NULL DEFAULT 0,
 web BOOLEAN NOT NULL DEFAULT FALSE,
 car_istruzioni INTEGER NOT NULL DEFAULT 0,
 car_strumenti INTEGER NOT NULL DEFAULT 0,
 car_richiesta INTEGER NOT NULL DEFAULT 0,
 car_blocchi JSONB NOT NULL DEFAULT '{}'::jsonb,
 cache_letti INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS misure_chiamate_creato ON misure_chiamate (creato_il);
CREATE INDEX IF NOT EXISTS misure_chiamate_agente ON misure_chiamate (agente_id, creato_il);
