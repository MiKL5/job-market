SELECT COUNT(*) AS nb_offres FROM offres; -- Requetes de controle

SELECT c.departement, c.code_departement, COUNT(*) AS nb_offres
FROM offres o JOIN communes c ON c.commune_id = o.commune_id
GROUP BY c.departement, c.code_departement
ORDER BY nb_offres DESC, c.departement;

SELECT UPPER(COALESCE(entreprise, '(non renseignee)')) AS entreprise, COUNT(*) AS nb_offres
FROM offres
GROUP BY UPPER(COALESCE(entreprise, '(non renseignee)'))
ORDER BY nb_offres DESC, entreprise LIMIT 15;

SELECT source, statut_enrichissement, COUNT(*) AS nb
FROM offres GROUP BY source, statut_enrichissement ORDER BY source, statut_enrichissement;

-- Lignes non appariees ou ambigues
SELECT offre_id, localisation_brute, statut, detail FROM offres_non_appariees ORDER BY statut, offre_id;

-- Doublons de contenu restants (doit renvoyer 0 ligne)
SELECT LOWER(titre) AS titre, LOWER(COALESCE(entreprise, '')) AS entreprise, ville_normalisee, COUNT(*) AS nb
FROM offres GROUP BY LOWER(titre), LOWER(COALESCE(entreprise, '')), ville_normalisee HAVING COUNT(*) > 1;
