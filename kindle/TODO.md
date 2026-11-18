# Type 0 / Kindle : à faire

État au 15/11/2026 : 0.8.56 publiée, Kindle 4 NT sur `http://192.168.1.10:8099/tab3.png?view=0`,
arrêt par n'importe quelle touche.

## 1. Deux colonnes (paysage)
- Aujourd'hui `eink.py` empile les sections, chacune sur toute la largeur.
- Placer les sections côte à côte comme HA, d'après « Nombre maximal de colonnes » de la vue
  (`max_columns`) : en 800 × 600 (`rotate=90`), 2 colonnes d'environ 390 px.
- Les vues en une colonne ne changent pas.

## 2. Réglages depuis Home Assistant (plus d'édition de `slimdash.conf`)
- Le Kindle demande une adresse fixe (ex. `http://192.168.1.10:8099/kindle.png`), réglée une
  seule fois à l'installation.
- Dashboard choisi par les options de SlimDash (dashboard publié sous le nom `kindle`), vue = vue
  par défaut de ce dashboard.
- Orientation déduite de la vue (2 colonnes ou plus → paysage), sans `rotate` dans l'adresse.
- Éventuellement, menu KUAL Portrait / Paysage (KUAL sur K4 NT : menus seulement, pas de saisie).

## 3. Commandes par les touches du Kindle
- Lire le code de la touche sans `od` (absent) : extraire les octets avec `dd` et comparer
  (`cmp` ou `awk`, à vérifier sur le Kindle). Codes à relever dans le journal.
- Le script appelle SlimDash (ex. `/<dashboard>/key?k=…`) ; SlimDash agit comme pour les boutons
  des tablettes (mêmes droits, même clé d'accès).
- Pavé : cadre épais qui passe d'un bouton / tuile à l'autre ; centre : active le bouton encadré ;
  touches de page : vue précédente / suivante ; Accueil : arrêt.
- Envisager une confirmation pour les commandes sensibles (portail).
- Essais d'actions uniquement sur le faux HA.
