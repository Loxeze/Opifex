-- 1.77.0: reparto Contenuti; schede di stile di montaggio ricavate dai montaggi di Lorenzo, da esempi incollati e da video di riferimento
CREATE TABLE IF NOT EXISTS stili_montaggio (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'riferimento' CHECK (tipo IN ('mio', 'riferimento')),
  note TEXT NOT NULL DEFAULT '',
  fonti JSONB NOT NULL DEFAULT '[]',
  materiale TEXT NOT NULL DEFAULT '',
  scheda TEXT,
  stato TEXT NOT NULL DEFAULT 'in_analisi' CHECK (stato IN ('in_analisi', 'pronto', 'errore')),
  errore TEXT,
  documento_id INTEGER REFERENCES documenti(id) ON DELETE SET NULL,
  creato_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
