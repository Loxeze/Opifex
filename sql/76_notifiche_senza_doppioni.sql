-- 1.46.0: la stessa notifica ordinaria non si ripete entro 6 ore (gli allarmi critici hanno gia' una loro attesa)
CREATE OR REPLACE FUNCTION notifiche_senza_doppioni() RETURNS trigger AS $$
BEGIN
  IF NOT COALESCE(NEW.critica, FALSE) AND EXISTS (SELECT 1 FROM notifiche WHERE testo = NEW.testo AND creata_il > NOW() - INTERVAL '6 hours') THEN
    RETURN NULL;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_notifiche_senza_doppioni ON notifiche;
CREATE TRIGGER trg_notifiche_senza_doppioni BEFORE INSERT ON notifiche FOR EACH ROW EXECUTE FUNCTION notifiche_senza_doppioni();
