-- Registro delle decisioni: chi ha approvato, respinto o autorizzato cosa e quando. Solo aggiunte: nessuna modifica o cancellazione.
CREATE TABLE IF NOT EXISTS registro_decisioni (
  id BIGSERIAL PRIMARY KEY,
  quando TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  utente_nome TEXT NOT NULL,
  utente_email TEXT,
  tipo TEXT NOT NULL,
  esito TEXT NOT NULL,
  oggetto_tipo TEXT,
  oggetto_id TEXT,
  oggetto TEXT NOT NULL DEFAULT '',
  nota TEXT NOT NULL DEFAULT '',
  dettagli JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS registro_decisioni_quando ON registro_decisioni (quando DESC);
CREATE INDEX IF NOT EXISTS registro_decisioni_utente ON registro_decisioni (utente_id, quando DESC);
CREATE INDEX IF NOT EXISTS registro_decisioni_tipo ON registro_decisioni (tipo, quando DESC);

CREATE OR REPLACE FUNCTION registro_decisioni_immutabile() RETURNS trigger AS $$
BEGIN
  -- l'unica modifica ammessa e' l'azzeramento del riferimento all'utente quando l'utente viene eliminato (il nome resta scritto)
  IF TG_OP = 'UPDATE' AND NEW.utente_id IS NULL AND OLD.utente_id IS NOT NULL
     AND NEW.id = OLD.id AND NEW.quando = OLD.quando AND NEW.utente_nome = OLD.utente_nome AND NEW.tipo = OLD.tipo
     AND NEW.esito = OLD.esito AND NEW.oggetto = OLD.oggetto AND NEW.nota = OLD.nota AND NEW.dettagli = OLD.dettagli THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Il registro delle decisioni non si modifica';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS registro_decisioni_blocco ON registro_decisioni;
CREATE TRIGGER registro_decisioni_blocco BEFORE UPDATE OR DELETE ON registro_decisioni
  FOR EACH ROW EXECUTE FUNCTION registro_decisioni_immutabile();
