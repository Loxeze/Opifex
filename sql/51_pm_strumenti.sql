-- 1.23.10: i project manager creano e aggiornano task e milestone del proprio progetto
UPDATE agenti SET istruzioni = replace(istruzioni, 'Proponi le milestone e segnali',
  'Crei e aggiorni tu task e milestone del progetto con i tuoi strumenti (crea_task, aggiorna_task, crea_milestone): se Lorenzo ti chiede una task o un promemoria, creala subito. Segnali')
WHERE id IN (SELECT pm_agente_id FROM progetti WHERE pm_agente_id IS NOT NULL);
