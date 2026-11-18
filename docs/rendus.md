# SlimDash – rendus par classe d'appareil

But : afficher un dashboard Home Assistant sur des appareils trop vieux pour l'interface
d'origine, en restant le plus fidèle possible à sa mise en page (positions, tailles, hauteurs),
avec une page de quelques kilo-octets.

## Les trois classes

La classe est déduite du navigateur (`/diag` montre ce que l'appareil annonce) ou forcée par
l'option `device` du dashboard. `?type=1` (ancien), `2` (intermédiaire) ou `3` (moderne) dans l'adresse permet d'essayer ; le type est gardé en changeant d'onglet.

| | **Ancien** | **Intermédiaire** | **Moderne** |
|---|---|---|---|
| Navigateurs | Chromium < 50, iOS < 10, Firefox < 52, inconnus | Chromium 50–79, iOS 10–12, Firefox 52–74 | Chromium ≥ 80, iOS ≥ 13, Firefox ≥ 75 |
| Feuilles de style | `s.css` | `s.css` + `c-t2.css` | + `c-t3.css` |
| Mise en page | blocs en ligne, flottants, tableaux | flexbox | grille CSS (plusieurs sections côte à côte si la largeur le permet) |
| Couleurs du thème | règles explicites, couleurs opaques calculées par le serveur | variables CSS | variables CSS |
| Icônes | SVG en sprite | idem | idem |
| Graphiques | 48 points, trait seul, redessinés toutes les 30 min | 48 points, remplissage | 96 points, min/max sous les grandes courbes |
| Caméras | image 480 px toutes les 30 s | 640 px toutes les 10 s | 800 px toutes les 3 s |
| Animations | aucune | aucune | transitions courtes |

Règles à respecter en classe Ancien (`s.css`) : pas de flexbox, pas de variables CSS, `calc`
avec son préfixe `-webkit-`, et **jamais de marge négative sur un bloc voisin d'un flottant**
(Android 4.4 le fait passer par-dessus le flottant). En classe Moderne : pas de `gap` sur les
rangées flexbox (absent de Chrome 80–83 et Safari 13–14.0).

## Fidélité à l'original

- **Gabarit** : hauteurs en unités comme les vues « sections » de HA (1U = 56 px, +8 px par unité
  en plus), largeurs sur 12 colonnes (`grid_options`), 8 px entre les cartes. Colonnes de 500 px
  au plus ; deux colonnes (32 px d'écart) dès 684 px de large, par exemple tablette en paysage,
  si la vue a au moins deux sections ; une colonne unique reste centrée. Une section sur
  plusieurs colonnes (`column_span` 2 à 4) occupe toute la largeur disponible, même seule dans
  la vue (plusieurs colonnes seulement dès 684 px, comme dans HA).
- **Image de fond de la vue** (type 3 seulement) : réglages de HA (opacité, taille, alignement,
  répétition, fixe / défilante) ; l'image est réduite par le serveur (Pillow) à 960, 1600 ou
  2048 px selon la largeur de l'écran, jamais agrandie, puis gardée en cache. Types 1 et 2 : fond
  du thème, sans image.
- **Thème** : celui choisi dans chaque vue du dashboard (Modifier la vue > Thème) ; sans
  thème, le thème par défaut de HA. Option `theme` du dashboard : `view` (par défaut),
  `ha light` ou `ha dark` (thème par défaut de HA pour toutes les vues ; anciennes valeurs `vue`, `ha clair`, `ha sombre` acceptées). Fond, cartes, textes, arrondis et couleurs
  d'état en sont repris (`theme.py`). Les transparences sont calculées côté serveur ; ni image de
  fond, ni flou.
- **Libellés d'état** : ceux de Home Assistant, dans sa langue (« Activé », « Non détecté »…).
- **Textes** : 14 px (nom) et 12 px (état), titres de carte 24 px, comme l'original.

## Cartes prises en charge

Natives : `tile` (fonctions : courbe de tendance, en bas ou en ligne ; boutons de volet ; lampes :
couleurs favorites, curseurs de luminosité et de température), `button`,
`entity` / `sensor` (avec courbe), `gauge`, `energy-self-sufficiency-gauge`, `entities`, `glance`, `markdown` (templates), `heading`,
badges, `weather-forecast`, `thermostat`, `history-graph`, `statistics-graph`, `picture` (fichier, image envoyée dans HA en 512 px sauf type 3, ou entité image), `picture-glance`,
`picture-entity` (caméras), `horizontal-stack`, `vertical-stack`, `grid`, `conditional`.

Personnalisées :

| Carte | Rendu |
|---|---|
| `button-card` | bouton (nom, état, action) ; hauteur imposée ≤ 80 px → bouton compact 1U. Les templates JavaScript `[[[ ]]]` sont ignorés. |
| `bubble-card` | `button` → tuile (état sous le nom si `show_state`) ; sous-boutons : icône, nom, valeurs de `state_content` (état, « Il y a 44 minutes », attribut) ou `show_state` ; `separator` → titre ; `pop-up` ignoré. |
| `mushroom-entity-card`, `mushroom-template-card` | tuile ; textes et couleur d'icône calculés par HA (templates Jinja). |
| `mushroom-chips-card` | pastilles ; chip météo en icône seule sauf `show_conditions` / `show_temperature`. |
| `stack-in-card` | une seule carte ; les chips alignés à droite après une tuile se posent sur la ligne de la tuile. |
| `statistics-graph-chart-card` | une entité : grande valeur + courbe ou barres. Plusieurs, noms masqués : chaque valeur à sa taille (`state_size`), sa couleur (`state_adaptive_color`, seuils), sa place (`align_state`, décalages des `styles`). Noms affichés : liste « nom valeur ». Barres et courbes dans le même graphique. |
| `digital-clock` | formats (`HH:mm`, `cccc d LLLL yyyy`…), tailles, graisses et marges des deux lignes. |
| `meteofrance-weather-card` | carte météo. |
| `advanced-camera-card`, `webrtc-camera` | image de la caméra. |

Toute autre carte : liste lisible des entités qu'elle contient.

## Limites volontaires

Non pris en charge : cartes `map`, `iframe`, lecteurs multimédias, calendriers, énergie, pop-ups,
`auto-entities`, curseurs autres que ceux des lampes (volume…), vidéo en direct, flèches de
tendance, styles `card_mod` (sauf fond et hauteur d'une carte), image de fond et effets du thème.
Actions possibles : basculer, appuyer, lancer un service, régler une lampe (couleur, luminosité,
température), naviguer entre les vues publiées. L'icône d'une lampe allumée prend sa couleur réelle.

## Charge

Une seule connexion WebSocket à Home Assistant, limitée aux entités affichées. Un rendu par
classe n'est préparé que lorsqu'un appareil de cette classe le demande. L'historique n'est
demandé que s'il est affiché (toutes les 5 minutes). Une vue pèse environ 3 Ko compressée ;
les feuilles de style et le script sont mis en cache 24 h.

## Vérifier un changement

`python dev/snapshot.py check` compare le rendu de toutes les vues de test, dans les trois
classes, à la référence enregistrée (`dev/snapshots/`) : position, taille, police et couleurs de
chaque élément. Après un changement voulu : `python dev/snapshot.py save`.
Pour mesurer une carte d'origine, coller `dev/mesure_ha.js` dans la console du navigateur, sur la
vue Home Assistant ouverte à 600 px de large. Le relevé de novembre 2026 est dans `revue-2026-11.md`.
