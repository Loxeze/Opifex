-- Fase 4: misure d'uso senza contenuti. Sessione anonima casuale (non collegata alla persona), classe di dispositivo, id dell'elemento cliccato
-- (mai il testo), componente che ha dato errore (percorso senza identificativi), agente in attesa, esito. Riepilogo giornaliero conservato a lungo.
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS sessione TEXT;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS dispositivo TEXT;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS elemento TEXT;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS componente TEXT;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS agente_id INTEGER;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS esito TEXT;
CREATE INDEX IF NOT EXISTS idx_uso_eventi_tempo ON uso_eventi (creato_il);
CREATE TABLE IF NOT EXISTS uso_giorno (
  giorno DATE NOT NULL,
  vista TEXT NOT NULL,
  azione TEXT NOT NULL,
  categoria TEXT NOT NULL DEFAULT '',
  dispositivo TEXT NOT NULL DEFAULT '',
  componente TEXT NOT NULL DEFAULT '',
  elemento TEXT NOT NULL DEFAULT '',
  esito TEXT NOT NULL DEFAULT '',
  eventi INTEGER NOT NULL,
  sessioni INTEGER NOT NULL DEFAULT 0,
  durata_totale_ms BIGINT NOT NULL DEFAULT 0,
  durata_mediana_ms INTEGER,
  PRIMARY KEY (giorno, vista, azione, categoria, dispositivo, componente, elemento, esito)
);
