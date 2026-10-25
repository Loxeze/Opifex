-- Studi di Padre Casati: ogni studio nasce da un motivo (bando letto, argomento discusso, lacuna, iniziativa sua o di Lorenzo)
CREATE TABLE IF NOT EXISTS studi (
    id SERIAL PRIMARY KEY,
    tema TEXT NOT NULL CHECK (char_length(tema) BETWEEN 5 AND 200),
    motivo TEXT CHECK (motivo IS NULL OR char_length(motivo) <= 1500),
    origine TEXT NOT NULL CHECK (origine IN ('bando','discussione','lacuna','iniziativa','manuale')),
    riferimento TEXT,
    documento_id INT REFERENCES documenti(id) ON DELETE SET NULL,
    divisione_id INT REFERENCES divisioni(id) ON DELETE SET NULL,
    agente_richiedente_id INT REFERENCES agenti(id) ON DELETE SET NULL,
    stato TEXT NOT NULL DEFAULT 'proposto' CHECK (stato IN ('proposto','approvato','in_corso','completato','scartato','errore')),
    scheda TEXT,
    errore TEXT,
    token_usati INT NOT NULL DEFAULT 0,
    memoria_id INT REFERENCES memorie_lavoro(id) ON DELETE SET NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deciso_il TIMESTAMPTZ,
    concluso_il TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS studi_tema_aperto ON studi (lower(tema)) WHERE stato IN ('proposto','approvato','in_corso');
CREATE INDEX IF NOT EXISTS studi_stato ON studi (stato, id DESC);
