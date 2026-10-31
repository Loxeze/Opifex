-- 2.2.0: chi entra in un progetto riceve subito gli strumenti Drive (la fascia dati resta una scelta di Lorenzo)
CREATE OR REPLACE FUNCTION progetto_agente_drive() RETURNS trigger AS $$
BEGIN
    UPDATE agenti SET drive_attivo = TRUE WHERE id = NEW.agente_id AND NOT drive_attivo;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DO $$ BEGIN
    IF to_regclass('progetti_agenti') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS progetti_agenti_drive ON progetti_agenti;
        CREATE TRIGGER progetti_agenti_drive AFTER INSERT ON progetti_agenti FOR EACH ROW EXECUTE FUNCTION progetto_agente_drive();
        UPDATE agenti SET drive_attivo = TRUE WHERE NOT drive_attivo AND id IN (SELECT agente_id FROM progetti_agenti);
    END IF;
END $$;
