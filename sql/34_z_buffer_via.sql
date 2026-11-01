-- Buffer non c'e' piu': le assegnazioni dei suoi canali non servono (restano quelle dei canali diretti, id «n:...»)
DELETE FROM canali_social_assegnazioni WHERE canale_id NOT LIKE 'n:%';
