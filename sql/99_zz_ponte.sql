-- 2.19.0: ponte tra Opifex e l'app Archivio sul computer di Lorenzo
CREATE TABLE IF NOT EXISTS ponte_lavori (
  id BIGSERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,
  parametri JSONB NOT NULL DEFAULT '{}',
  stato TEXT NOT NULL DEFAULT 'coda' CHECK (stato IN ('coda','preso','finito','errore')),
  risultato JSONB,
  errore TEXT,
  creato TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finito TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ponte_lavori_coda ON ponte_lavori (stato, id);
CREATE TABLE IF NOT EXISTS ponte_pc (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  visto TIMESTAMPTZ,
  capacita JSONB NOT NULL DEFAULT '{}',
  destinazione TEXT NOT NULL DEFAULT 'server' CHECK (destinazione IN ('server','pc'))
);
INSERT INTO ponte_pc (id) VALUES (1) ON CONFLICT DO NOTHING;
