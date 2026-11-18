# SlimDash sur Kindle 4 (sans tactile) : guide d'installation

Le Kindle affiche en plein écran une **image** de votre vue SlimDash (le « type 0 »),
mise à jour toutes les minutes, sans mise en veille. Son navigateur n'est pas utilisé.

Comment ça marche : SlimDash dessine la vue en image PNG 600 × 800 en niveaux de gris
(`http://<IP>:8099/<dashboard>.png?view=<n°>`). Un petit script sur le Kindle télécharge
l'image et l'affiche. L'image ne change que si une valeur affichée a changé. Le Kindle ne
rafraîchit l'écran qu'à ce moment-là.

> Le Kindle n'est qu'un écran : on ne peut pas toucher les boutons de l'image.

---

## 0. Avant de commencer

- **Kindle 4 sans tactile** (5 boutons et pavé directionnel). Firmware **4.1.x** :
  `Menu` › `Paramètres` › `Menu` › `Informations sur l'appareil`.
- **Wi-Fi du Kindle déjà configuré** sur votre réseau (le même que Home Assistant).
- **Alimentation par un chargeur secteur USB** (chargeur de téléphone).
  ⚠️ **Pas sur un port USB d'ordinateur** : branché à un PC, le Kindle passe en « mode clé USB »
  et coupe l'affichage et le Wi-Fi.
- Un ordinateur et le câble USB, pour copier les fichiers.

Le jailbreak se défait (fichier de désinstallation fourni avec), et ne touche pas à vos livres.
Il se fait toutefois à vos risques : suivez les étapes dans l'ordre.

---

## 1. Préparer la vue dans Home Assistant

1. Créez une vue dédiée (dans un dashboard publié par SlimDash, par exemple `tab3`), de type
   **Sections**, avec **une seule colonne** (réglage « Nombre maximal de colonnes » : 1).
2. Gardez-la **courte** : l'écran fait 600 × 800. Si elle est trop haute, l'image est réduite
   (jusqu'à 60 %), puis coupée en bas.
3. Cartes bien dessinées : horloge (`digital-clock`), météo, graphiques (`statistics-graph-chart-card`,
   historique), jauges, boutons, tuiles, entités, glance, markdown, titres, bubble-card, mushroom,
   piles et grilles. Les autres cartes s'affichent en liste « nom : état ».
4. Vérifiez l'image sur le PC, dans le navigateur :
   `http://192.168.1.10:8099/tab3.png?view=0`
   (remplacez `tab3` par le nom du dashboard dans SlimDash et `0` par le numéro de la vue,
   en partant de 0, ou par son chemin d'URL).

---

## 2. Jailbreaker le Kindle

Fichier : **« Kindle 4 (non-touch) jailbreak »**, sur le forum MobileRead
(section *Kindle Developer's Corner*). Prenez la dernière version, qui accepte les firmwares 4.1.x.

1. Branchez le Kindle au PC. Il apparaît comme une clé USB.
2. Décompressez l'archive du jailbreak. Copiez à la **racine** du Kindle les éléments indiqués
   dans son fichier lisez-moi : en général `data.tar.gz`, `ENABLE_DIAGS` et le dossier `diagnostic_logs`.
3. Éjectez proprement le Kindle, puis débranchez-le.
4. Redémarrez-le : `Menu` › `Paramètres` › `Menu` › `Redémarrer`.
5. Le Kindle s'ouvre en **mode diagnostic** (écran texte). Avec le pavé, choisissez
   **Exit, Reboot or Disable Diags**, puis **Reboot System**, et confirmez.
6. Au redémarrage, l'écran du jailbreak s'affiche brièvement, puis un livre
   « You are Jailbroken » apparaît dans la bibliothèque. C'est fait.

---

## 3. Installer KUAL (le lanceur d'extensions)

Sur le Kindle 4, KUAL demande d'abord la clé « MKK ». Les deux se trouvent sur MobileRead
(fils **« KUAL »** et **« Mobileread Kindlet Kit (MKK) »**).

1. Dans l'archive MKK, prenez le fichier `Update_mkk-…-k4-ALL_install.bin`. Copiez-le à la
   **racine** du Kindle, éjectez, puis lancez `Menu` › `Paramètres` › `Menu` ›
   `Mettre à jour votre Kindle`. Le Kindle redémarre.
2. Dans l'archive KUAL, prenez **`KUAL-KDK-1.0.azw2`** (version pour Kindle sans tactile).
   Copiez-le dans le dossier **`documents`** du Kindle.
3. Éjectez. « Kindle Launcher » (KUAL) apparaît dans la bibliothèque.

---

## 4. Installer SlimDash sur le Kindle

1. Branchez le Kindle au PC.
2. À la racine du Kindle, créez le dossier **`extensions`** s'il n'existe pas.
3. Copiez-y le dossier **`slimdash`** fourni (`kindle/extensions/slimdash`). Vous devez avoir
   `extensions/slimdash/config.xml`, `menu.json`, `slimdash.conf` et `bin/`.
4. Ouvrez `extensions/slimdash/slimdash.conf` avec le Bloc-notes et réglez l'adresse :
   ```
   URL="http://192.168.1.10:8099/tab3.png?view=0"
   NTP="192.168.1.10"
   INTERVAL=60
   FULL_EVERY=10
   ```
   - `URL` : l'adresse testée à l'étape 1 (ajoutez `&k=<clé>` si SlimDash a une clé d'accès) ;
   - `NTP` : serveur de temps du réseau local (par exemple Home Assistant, s'il en fait office),
     pour garder le Kindle à l'heure ; laissez vide si vous n'en avez pas ;
   - `INTERVAL` : secondes entre deux mises à jour (10 au minimum), calées sur l'horloge
     (60 = pile à chaque minute) ;
   - `FULL_EVERY` : écran entièrement effacé puis redessiné toutes les N images (enlève les traces).
5. Enregistrez, éjectez, débranchez du PC et branchez le **chargeur secteur**.

---

## 5. Démarrer, arrêter

- **Démarrer** : ouvrez « Kindle Launcher » › **SlimDash** › **Démarrer l'affichage**.
  L'interface du Kindle s'arrête. « SlimDash : connexion... » s'affiche, puis l'image
  arrive en moins d'une minute.
- **Arrêter** : touche **Accueil** (les autres touches sont ignorées, pour éviter les arrêts par
  erreur). L'interface du Kindle revient au bout de quelques secondes.
  Si rien ne se passe, maintenez le **bouton marche 20 secondes** : le Kindle redémarre
  normalement.
- Après un redémarrage du Kindle, relancez SlimDash depuis KUAL (pas de démarrage automatique).

---

## 6. En cas de problème

| Symptôme | Que faire |
|---|---|
| « adresse absente » | `URL` est vide dans `slimdash.conf`. |
| « SlimDash injoignable » en bas de l'écran | Vérifiez l'adresse dans le navigateur du PC et le Wi-Fi du Kindle. Le script relance le Wi-Fi et réessaie tout seul. |
| Bandeau noir « Home Assistant injoignable » sur l'image | SlimDash tourne mais ne joint plus Home Assistant. |
| Image trop petite ou coupée | Vue trop haute : retirez des cartes, ou réduisez la hauteur des cartes (rangées). |
| Rien ne s'affiche après « Démarrer » | Branchez au PC et lisez `extensions/slimdash/slimdash.log`. |
| Le Kindle passe en mode clé USB | Il est branché sur un PC : utilisez un chargeur secteur. |

Le journal `extensions/slimdash/slimdash.log` note le démarrage, l'état du Wi-Fi, les touches et
les échecs de téléchargement.

---

## Réglages côté SlimDash (adresse de l'image)

| Paramètre | Rôle | Défaut |
|---|---|---|
| `view` | numéro de la vue (à partir de 0) ou son chemin d'URL | 1re vue du dashboard |
| `w`, `h` | taille de l'écran en pixels | 600 × 800 |
| `rotate` | `90` ou `270` pour un Kindle couché (paysage) | 0 |
| `k` | clé d'accès, si réglée dans SlimDash | — |

`http://<IP>:8099/<dashboard>?type=0` renvoie aussi vers l'image.
