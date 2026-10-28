-- 1.62.0: ciclo di miglioramento - Padre Casati propone nuove istruzioni per gli agenti che ricevono molti «giu»; Lorenzo approva o respinge
CREATE TABLE IF NOT EXISTS miglioramenti (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  istruzioni_base TEXT NOT NULL,            -- le istruzioni al momento della proposta (per accorgersi se nel frattempo sono cambiate)
  proposta TEXT NOT NULL,                   -- le nuove istruzioni complete
  sintesi TEXT NOT NULL,                    -- che cosa cambia e perche'
  evidenze TEXT,                            -- i voti e le note che l'hanno originata
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta','applicata','respinta','superata')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ,
  decisa_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS miglioramenti_agente ON miglioramenti (agente_id, id DESC);
