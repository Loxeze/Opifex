-- 1.67.2: in fase di prova gli agenti dei reparti Casa editrice, Social e Ricerca e Sviluppo passano a Haiku (i revisori restano come sono)
UPDATE agenti SET modello = 'claude-haiku-5-5'
WHERE divisione_id IN (SELECT id FROM divisioni WHERE nome IN ('Casa editrice','Social','Ricerca e Sviluppo'))
  AND tipo = 'divisione' AND nome NOT ILIKE '%revisore%' AND nome NOT LIKE '%(GPT)' AND modello LIKE 'claude-%' AND modello NOT LIKE 'claude-haiku%';
