-- 1.23.7: il web e' accessibile a tutti gli agenti; si blocca caso per caso dalla scheda dell'agente.
-- La conversione dei vecchi agenti avviene una volta sola (marcatore): i blocchi messi dopo restano.
ALTER TABLE agenti ALTER COLUMN accesso_web SET DEFAULT TRUE;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_web_per_tutti') THEN
    UPDATE agenti SET accesso_web = TRUE WHERE ruolo_speciale IS DISTINCT FROM 'cerimoniere';   -- il Cerimoniere indica solo a chi rivolgersi: non cerca in rete
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_web_per_tutti', '1');
  END IF;
END $$;
