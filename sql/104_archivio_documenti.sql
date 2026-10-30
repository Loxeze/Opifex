-- 1.84.0: l'archivio NAS indicizza anche i documenti scritti (PDF, Word, Excel, PowerPoint, testo)
ALTER TABLE archivio_file DROP CONSTRAINT IF EXISTS archivio_file_tipo_check;
ALTER TABLE archivio_file ADD CONSTRAINT archivio_file_tipo_check CHECK (tipo IN ('foto', 'video', 'audio', 'documento'));
ALTER TABLE archivio_file ADD COLUMN IF NOT EXISTS contenuto TEXT;
CREATE OR REPLACE FUNCTION archivio_indicizza() RETURNS trigger AS $$
BEGIN
  NEW.ricerca := to_tsvector('italian', replace(replace(coalesce(NEW.rel, ''), '/', ' '), '_', ' ') || ' ' || coalesce(NEW.descrizione, '') || ' ' ||
                 coalesce(array_to_string(NEW.etichette, ' '), '') || ' ' || left(coalesce(NEW.trascrizione, ''), 200000) || ' ' || left(coalesce(NEW.contenuto, ''), 200000));
  RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_archivio_indicizza ON archivio_file;
CREATE TRIGGER trg_archivio_indicizza BEFORE INSERT OR UPDATE OF rel, descrizione, etichette, trascrizione, contenuto ON archivio_file FOR EACH ROW EXECUTE FUNCTION archivio_indicizza();
-- In riunione tutti i manager usano il modello scelto per le riunioni (Opus): niente modello da riunione particolare per Aurora ed Elena
UPDATE agenti SET modello_riunione = NULL WHERE lower(nome) IN ('aurora', 'elena') AND modello_riunione = 'claude-sonnet-5-5';
