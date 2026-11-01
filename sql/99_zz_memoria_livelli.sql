-- Memoria a quattro livelli: 1 Lorenzo (persona), 2 azienda/reparto, 3 progetto, 4 task (lavoro specifico di durata).
ALTER TABLE memorie_lavoro ADD COLUMN IF NOT EXISTS persona BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE memorie_lavoro ADD COLUMN IF NOT EXISTS task_id INTEGER REFERENCES task(id) ON DELETE CASCADE;
ALTER TABLE memorie_lavoro DROP CONSTRAINT IF EXISTS memorie_lavoro_livello_check;
ALTER TABLE memorie_lavoro ADD CONSTRAINT memorie_lavoro_livello_check
  CHECK (NOT persona OR (azienda_id IS NULL AND progetto_id IS NULL AND divisione_id IS NULL AND task_id IS NULL AND agente_id IS NULL));
CREATE INDEX IF NOT EXISTS idx_memorie_livello ON memorie_lavoro (persona, task_id) WHERE stato = 'approvata';

-- Voci iniziali sul titolare: nascono come PROPOSTE (le approva o corregge lui); non si reinseriscono se gia' decise o cancellate dall'elenco.
INSERT INTO memorie_lavoro (testo, tipo, stato, fascia_dati, fonte, origine, persona, tema)
SELECT v.t, 'fatto', 'proposta', 'interno', 'profilo iniziale (chat precedenti e memoria di Claude)', 'profilo iniziale', TRUE, v.tema
FROM (VALUES
 ('Lorenzo Zeppa e'' imprenditore e progettista, con base a Masone (GE), Liguria. Lavora su tre assi: valorizzazione del patrimonio culturale, deeptech/AI, europrogettazione e finanza agevolata.', 'chi sono'),
 ('Titolare di Logos di Lorenzo Zeppa, ditta individuale per servizi digitali e project management.', 'organizzazione'),
 ('Presidente dell''Associazione Renovatio ETS/ODV (fondata nel 2016), associazione culturale con partenariati internazionali.', 'organizzazione'),
 ('Partecipa a Evidens (startup deeptech: container intelligenti IoT) e ad Aquilia (startup che commercializza FARO, piattaforma AI per finanziamenti a cultura e turismo); ha fondato con Nadiaclara Trigari e Nicola Urbino la societa'' Arete'' Hub S.r.l.', 'organizzazione'),
 ('Collaborazioni universitarie: Sapienza, Vanvitelli, Universita'' di Genova (DITEN), Florida International University (FIU).', 'organizzazione'),
 ('Progetti in corso o ricorrenti: Castello di Montarrenti (Sovicille, in gestione a Renovatio), Simposia culturali, Fuori (dai) Rolli a Genova, Valle Stura Digital Tales, BORGHI (PNRR), Immaginare i Saperi (video per la Sapienza), podcast culturali e ricerca di sponsor, Lithos (idea di startup per archivi analogici).', 'progetti'),
 ('Contatti: da completare da Lorenzo (email, telefono, sito, orari e modo preferito per essere raggiunto).', 'contatti'),
 ('Conferenze, eventi e interventi pubblici: da completare da Lorenzo (date, luoghi, temi).', 'conferenze'),
 ('Preferenze di lavoro: per i video servono sempre consegne in 4K (va bene anche il file di progetto XML per Premiere Pro al posto del render). Italiano come lingua di lavoro, risposte concise e dirette, azione senza troppe domande preliminari.', 'preferenze')
) AS v(t, tema)
WHERE NOT EXISTS (SELECT 1 FROM memorie_lavoro m WHERE m.persona AND m.testo = v.t);
