# ✦ Dropi — ton assistant IA 100 % local

Une goutte d'eau façon Dynamic Island collée au bord de ton écran, au style Windows 11,
avec **Plop** dedans : une petite mascotte blanche et violette animée en 3D qui réagit à ce que tu fais.
C'est aussi le logo de l'appli (`logo.png`, `logo.ico`).
Tout tourne sur ton PC : rien n'est envoyé sur internet, sauf pour lire tes mails et quand il se renseigne
(il n'envoie alors que ta question à DuckDuckGo / Wikipédia).

## Installation

**Le plus simple** : télécharge **Dropi-Setup.exe** dans les *Releases* et double-clique. Rien d'autre à
installer (ni Python, ni Ollama), pas besoin d'être administrateur. L'installateur met l'appli dans
`%LOCALAPPDATA%\Programs\Dropi`, crée un raccourci sur le Bureau et dans le menu Démarrer, et la lance
au démarrage de Windows (clic droit sur la goutte pour couper). Au **premier lancement**, le modèle d'IA (~5 Go)
se télécharge une seule fois, la progression s'affiche sur la goutte. Ensuite, tout est local et hors ligne.
Une mise à jour = relancer le nouvel installateur : ta config, ta mémoire et ton journal sont gardés.

Config : `config.yaml` à côté de Dropi.exe (tes dossiers de rangement, streamers, applis, mail…).

## Place et ressources

| | |
|---|---|
| Disque | installateur ~200 Mo, installé ~350 Mo, + modèle IA ~5 Go (réutilise celui d'Ollama s'il existe) |
| RAM, IA déchargée | ~200 Mo |
| RAM, IA chargée | ~6 Go ; rendue au PC après `garder_en_memoire` (15 min par défaut) sans demande |
| Carte graphique | utilisée si elle est libre (Nvidia, AMD, Intel via Vulkan). Occupée par un jeu ou une vidéo (> 50 %) : l'IA reste sur le processeur. Mémoire vidéo juste : seules les couches qui rentrent y vont, avec 1,5 Go de marge pour le reste. `ia_gpu: non` pour ne jamais l'utiliser |
| Processeur | un cœur laissé libre, priorité basse : le PC reste fluide |

## Mises à jour automatiques

Dropi regarde la dernière release GitHub 30 secondes après son lancement, puis toutes les 6 heures. S'il y en a une
plus récente, la goutte affiche « Dropi 1.2.0 est disponible · clique pour installer » (et une ligne dans la
discussion). Un clic télécharge le nouveau `Dropi-Setup.exe`, vérifie sa taille et son empreinte SHA-256, ferme Dropi,
installe par-dessus (ta config, ta mémoire et ton modèle sont gardés) et relance Dropi. Rien n'est installé sans ton clic.
Clic droit sur la goutte → « Vérifier les mises à jour » pour demander tout de suite. Pour couper : `mise_a_jour: non`
dans config.yaml.

### Publier une mise à jour (pour toi qui développes)

1. Augmente le numéro dans `version.py` (ex. `"1.1.0"`).
2. `python construire_exe.py` → `construction/Dropi-Setup.exe`.
3. Commit et push du code.
4. Sur GitHub : **Releases → Draft a new release**, tag **`v1.1.0`** (le même numéro que `version.py`, avec un « v »),
   un titre, puis glisse **`Dropi-Setup.exe`** dans les fichiers joints (le nom doit être exactement celui-là), **Publish release**.

Les gens qui ont déjà Dropi 1.0.0 ou plus reçoivent la proposition dans les 6 heures (ou tout de suite via le menu).
Ne marque pas la release « pre-release » : elle serait ignorée.

## Construire l'installateur (pour les développeurs)

Il faut Python 3.11+ et Inno Setup 6 (`winget install JRSoftware.InnoSetup`). Double-clique sur **construire_exe.bat** :
il fabrique `construction/Dropi-Setup.exe` (Dropi.exe + moteur llama.cpp), à joindre à la release GitHub.
`python construire_exe.py --local` installe directement sur ton PC sans passer par l'installateur.

Une seule goutte à la fois : relancer l'appli ouvre simplement celle qui tourne.
Si quelque chose plante, le détail est dans `%APPDATA%\AssistantIle\erreurs.log`.

## Version script (sans installateur)

1. Installe **Python 3.11 ou plus** (coche « Add Python to PATH »).
2. Double-clique sur **installer.bat** (dépendances, logo, raccourci). Le moteur et le modèle se téléchargent au premier lancement.

### Lancement

Double-clique sur **lancer.bat** (ou sur le raccourci **Dropi** du Bureau). La goutte apparaît là où tu l'avais laissée.

Pour qu'elle démarre avec Windows : `Win + R`, tape `shell:startup`,
et place un raccourci vers `lancer.bat` dans ce dossier.

## Utilisation

| Geste | Effet |
|---|---|
| Survol de la goutte | Plop te sourit, la goutte s'étire |
| Clic sur la goutte | Elle s'ouvre (discussion) |
| Attraper la goutte et tirer | Le col liquide s'étire puis casse ; lâche-la, elle se colle au bord le plus proche (haut, bas, gauche, droite) |
| Attraper un panneau ouvert par son en-tête | Pareil : il redevient goutte, puis se rouvre à sa nouvelle place |
| Glisser des fichiers dessus | Elle grossit, Plop ouvre la bouche, puis te demande quoi en faire |
| Maintenir 🎤 | Tu parles, relâche pour envoyer |
| Échap / clic ailleurs | Elle se referme |
| Clic droit | Nouvelle conversation / Replacer en haut / Quitter |

### Plop, la mascotte

Plop suit ta souris des yeux, cligne, respire. Il réfléchit quand l'IA travaille, t'écoute quand
tu parles, regarde ce que tu tapes, a faim quand tu approches un fichier, saute de joie quand
c'est réussi, fait la moue en cas d'erreur, et s'endort si tu ne touches plus la souris.
Ses expressions sont dans `mascotte.py` (`EXPRESSIONS`).

Il vit aussi sa vie :

- **Il se creuse les méninges** quand l'IA travaille : un sourcil froncé, l'autre levé, des engrenages qui
  tournent, et une goutte de sueur si ça dure. Quand elle a trouvé, **une ampoule s'allume**.
- **Promène la goutte** : lancé contre un bord de l'écran, il se cogne (yeux en `> <`, il rebondit) ;
  très fort, ou secoué de gauche à droite, il finit **étourdi**, les yeux en spirale et des étoiles autour de la tête.
- **Chatouille-le** en agitant la souris sur lui : il rit, des cœurs s'envolent.
- Il **bâille** avant de s'endormir, fait un **clin d'œil** ou un petit saut de temps en temps,
  tend l'oreille (des ondes) quand tu parles, et sursaute avec un « ! » quand un rappel sonne.

### Musique

Quand tu écoutes quelque chose sur Apple Music (ou Spotify, iTunes), la goutte affiche la cover à gauche,
le titre avec l'artiste en petit dessous, et le temps à droite. Clique sur la cover pour mettre en pause.
Tu peux aussi dire « mets en pause », « musique suivante », « c'est quoi cette musique ? ».
Réglages dans `config.yaml`, section `musique` (ajoute `brave` ou `chrome` pour YouTube).

### En plein écran

En jeu ou devant une vidéo en plein écran, la goutte se cache toute seule et revient après
(`masquer_en_plein_ecran` dans `config.yaml`).

### Il apprend

L'IA locale ne change pas elle-même (ce serait un entraînement très lourd), mais l'assistant se construit
une **mémoire** : ce que tu lui apprends (« retiens que… »), tes préférences et corrections, ce qu'il a
trouvé en se renseignant sur internet, et ce que tu lances souvent. Il relit les souvenirs utiles avant
chaque réponse : plus tu t'en sers, plus il est précis. Clic droit : « Ce que j'ai appris » /
« Oublier ce que j'ai appris ». Tout reste dans `%APPDATA%\AssistantIle\memoire.json`.

Pour une question sur un sujet qu'il ne connaît pas (un jeu récent, un film, une actu…), il se renseigne
sur DuckDuckGo et Wikipédia (seule ta question part sur internet), répond, et retient la réponse.

### Tes jeux

« Mes jeux » (ou « quels jeux j'ai ? ») affiche ta bibliothèque avec les vraies jaquettes
(prises dans le cache de Steam, rien n'est téléchargé) et les icônes Riot. Un clic sur une
jaquette lance le jeu.

Quand tu donnes un ordre (« ouvre Discord »), l'assistant le fait et confirme juste
dans la bulle (✓ vert). Il ne fait de vraies phrases que si tu lui poses une question.

### Le rangement méthodique

Chaque fichier va dans le dossier de son **type**, puis de sa **source** (le site ou l'appli d'où il vient) :

```
Documents\Classement\PDF\Gmail\facture_edf.pdf
Documents\Classement\Word\Origine inconnue\rapport.docx
Documents\Classement\Bloc-notes\Impôts\avis.txt
Images\Classement\Discord\meme.png
Images\Classement\Captures d'écran\Capture d'écran 2026-09-30.png
Téléchargements\Classement\Installateurs\JetBrains\idea-setup.exe
```

La source vient de l'étiquette que Windows colle aux fichiers téléchargés (adresse du site),
ou du nom du fichier (captures d'écran, WhatsApp, photos de téléphone). Sinon : « Origine inconnue ».
Les dossiers, noms de sites et sous-dossiers par année se règlent dans `config.yaml` (section `classement`).

Tout déplacement est noté dans `journal_rangement.json` : si tu parles d'un fichier qu'il a rangé,
l'assistant sait où il est maintenant. « Annule » remet le dernier fichier à sa place.

### Téléchargements

Quand un téléchargement se termine, la goutte affiche « Nouveau : facture.pdf → PDF › Gmail ».
Clique dessus : elle te montre le fichier et te propose l'endroit (**Ranger ici**), ou le **Bureau**,
un autre dossier, l'ouvrir, le supprimer. Dans `config.yaml`, `telechargements: mode: auto` le range
tout seul (20 secondes après, le temps de l'ouvrir si besoin).

### Ordres directs (instantanés)

Les demandes simples sont comprises et faites tout de suite, sans passer par l'IA : « ouvre Excel »,
« pause », « volume à 30 », « quelle heure il est », « range mon bureau », « minuteur 5 minutes »…
L'IA ne sert plus qu'aux vraies questions et aux demandes à plusieurs étapes (« ouvre Excel et lance Teams »,
« résume mes mails »). Les tournures reconnues sont dans **ordres.py** (`MOTIFS`) : ajoute les tiennes.

Les applications sont celles vraiment installées sur le PC (menu Démarrer, Microsoft Store) : l'assistant
ne lance jamais autre chose à la place, il dit « introuvable sur ce PC ».

### Rappels et minuteurs

- « Rappelle-moi dans 20 min d'appeler Paul », « rappelle-moi à 15h30 de sortir le linge »,
  « rappelle-moi demain à 9h la réunion », « fais-moi penser à… dans 1h30 ».
- « Minuteur 5 minutes », « timer 45 secondes » : le compte à rebours s'affiche sur la goutte.
- « Mes rappels », « combien de temps il reste », « annule le minuteur », « annule les rappels ».

À l'heure dite, la goutte sonne et affiche le rappel (clique dessus pour le faire disparaître), même en plein
écran. Les rappels survivent à un redémarrage (`%APPDATA%\AssistantIle\rappels.json`).

### Réglages du PC

« Volume à 30 », « monte le son », « coupe le son », « luminosité à 50 », « baisse la luminosité »,
« verrouille le PC », « éteins l'écran ». Pour le Wi-Fi, le Bluetooth, les notifications… l'assistant ouvre
la bonne page des Paramètres (« ouvre les réglages du wifi ») : Windows ne laisse pas un programme les
basculer sans droits administrateur. La luminosité ne marche que sur l'écran d'un portable.

### Lire du texte à l'écran

« Lis l'écran » (ou clic droit sur la goutte › **Lire du texte à l'écran**) : l'écran se fige, trace un cadre
autour du texte. Il est lu sur ton PC par la reconnaissance de Windows, copié dans le presse-papiers et
affiché dans la discussion ; tu peux ensuite demander « résume-le » ou « traduis-le ». Échap pour annuler.

### Mots de passe

Clique dans un champ « mot de passe » de Chrome, Brave ou Edge : la goutte s'allonge.

- **Site inconnu** : « Mot de passe pour exemple.fr ? Clique ». Le panneau te propose un mot de passe robuste
  (le bouton à côté en tire un autre ; tape le tien à la place si tu as déjà un compte) et reprend l'identifiant déjà saisi
  dans la page. **Enregistrer et remplir** le retient et remplit la page.
- **Site connu** : « Clique pour remplir simon@… ». Un clic et l'identifiant et le mot de passe sont remplis.
  Plusieurs comptes sur le même site : le panneau te laisse choisir.
- Clic droit sur la goutte : « Mot de passe pour … » (autre compte, nouveau mot de passe) et
  « Mes mots de passe » (ouvre le Gestionnaire d'identifiants de Windows, entrées « Dropi/… » :
  tu peux les voir et les supprimer là).

**Les retenir tout seul (extension).** Sans rien faire de plus, l'assistant peut retenir l'identifiant et le
mot de passe au moment où tu te connectes à un site. Il faut installer une fois la petite extension du
dossier `extension`, dans chaque navigateur :

1. Ouvre `chrome://extensions` (ou `brave://extensions`, `edge://extensions`).
2. Active **Mode développeur** (en haut à droite).
3. **Charger l'extension non empaquetée** → choisis le dossier `extension` de l'assistant.

Ensuite, à chaque connexion, la goutte affiche « Mot de passe enregistré pour exemple.fr · clique pour
annuler ». Un mot de passe déjà connu n'est pas réenregistré ; un mot de passe changé est mis à jour.
L'extension ne parle qu'à l'assistant de ce PC (le navigateur n'autorise qu'elle), rien ne part sur internet.
Pour couper : `capture: false` dans `config.yaml`. Marche avec la version script (lancer.bat), pas encore
avec Dropi.exe.

Les mots de passe sont chiffrés par Windows avec ta session, jamais écrits dans un fichier de l'assistant,
jamais montrés à l'IA. La goutte ne remplit que si l'adresse de la page est **exactement** celle du site
enregistré (un faux site qui imite le vrai n'obtient rien). Ils restent sur ce PC : pas de synchronisation,
pense à ce que tu perdrais si le PC est réinitialisé.

Limites : sur les sites en deux étapes (identifiant, puis mot de passe sur une autre page), seul le mot de
passe est rempli. Le guetteur lit ce que Windows décrit de la page (l'« accessibilité ») : certains
formulaires exotiques ne sont pas reconnus. Réglages dans `config.yaml`, section `mots_de_passe`.

### Faire de la place

« Fais-moi de la place » analyse ton disque et affiche une carte : fichiers temporaires,
vieux installateurs, doublons, gros fichiers oubliés, avec la place que chacun prend.
Tu coches ce que tu veux supprimer. Rien ne part sans ton clic ; tes fichiers vont à la corbeille
(récupérables), seuls les fichiers temporaires sont supprimés pour de bon. « Vider la corbeille »
libère vraiment la place (deux clics, c'est définitif).

### Déposer des fichiers

Glisse un ou plusieurs fichiers sur la goutte : elle s'agrandit, affiche les fichiers
(aperçu pour les images) avec l'endroit où chacun ira, et te propose :

- **Ranger ici** : à sa place dans le classement (instantané, sans l'IA)
- **Ouvrir**, **Déplacer…** (tu choisis le dossier), **Bureau**, **Supprimer** (2 clics, part à la corbeille),
  **Afficher dans l'explorateur**
- ou tape / dis ce que tu veux : « renomme-le facture_mars », « résume-le »…

## Jouer avec Dropi

Des mini-jeux en 1 contre 1, Dropi est l'adversaire (aucune IA ni internet : il répond tout de suite).
Pour ouvrir le panneau : **clique sur Dropi** dans l'écran d'accueil, sur la manette en haut de la discussion,
ou écris « on joue ? », « je m'ennuie », « une partie de morpion », « pierre feuille ciseaux », « puissance 4 », « mémoire », « devine le nombre », « duel de réflexes ».

| Jeu | Règle |
|---|---|
| Morpion | Tu es les croix. Dropi calcule le meilleur coup mais se trompe une fois sur cinq : tu peux le battre. Il commence une partie sur deux. |
| Pierre-feuille-ciseaux | Premier à 3 points. Dropi retient ce que tu joues le plus souvent et essaie de le contrer : varie ! |
| Puissance 4 | Tu joues les pions de ta couleur, Dropi voit 4 coups d'avance mais rate un coup sur dix. Les pions tombent. |
| Mémoire | 8 paires d'emojis. Une paire trouvée = tu rejoues. Dropi ne retient que 6 cartes vues sur 10 : sa mémoire n'est pas parfaite. |
| Devine le nombre | Dropi pense à un nombre de 1 à 100 et tu le cherches ; puis tu en choisis un et c'est lui qui cherche (plus grand / plus petit / trouvé). Le moins d'essais gagne. |
| Réflexe | Premier à 2 manches. Clique dès que la zone passe au vert (avant : Dropi gagne la manche). Dropi réagit en ~340 ms. |

Dropi réagit à chaque manche (content, vexé, surpris).

## Convertir un fichier

Dépose un fichier sur Dropi, puis **Convertir** (ou écris « convertis en jpg », « mets ça en pdf », « réduis l'image »).
Tout se fait sur le PC, sans IA ; le fichier converti est créé à côté de l'original, qui n'est jamais touché
(« photo (2).jpg » si le nom existe déjà).

| Tu déposes | Dropi propose |
|---|---|
| Une image (PNG, JPG, WebP, BMP, GIF, TIFF) | En PNG / JPG / WebP / PDF, ou « Image réduite » (1280 px max) |
| Plusieurs images | Idem, et **Un seul PDF** avec toutes les images |
| Un PDF | **Images** (une par page, dans un dossier, 60 pages max) ou **Texte** (.txt) |
| Un texte (txt, md, csv, json, html, code…) | En PDF |
| Word, Excel, PowerPoint | En PDF (Word/Excel/PowerPoint doit être installé ; pour un .docx sans Word : PDF du texte seul, mise en forme simplifiée) |

Pas de vidéo ni d'audio (il faudrait ffmpeg, +80 Mo), ni de HEIC (photos d'iPhone).

## Exemples de demandes

- « Ouvre le stream de Kameto »
- « Lance Elden Ring » (les jeux Steam sont détectés tout seuls)
- « Range mes téléchargements », « Range mon bureau », « Où est ma facture EDF ? », « Annule »
- « Fais-moi de la place »
- « C'est quoi RoadCraft ? » (il se renseigne), « Retiens que ma carte graphique est une RTX 4070 »
- « Mets en pause », « Musique suivante »
- « Supprime le fichier setup.exe du bureau » (il part à la corbeille, récupérable)
- « Résume mes 5 derniers mails »
- « Ouvre Discord », « Cherche le fichier CV », « Quelle heure il est ? »
- Sur un fichier déposé : « Résume-le » (texte et PDF), « Renomme-le cours_maths_chap3 »

## Personnaliser l'apparence

En haut de **island.py** : taille de la goutte (`CERCLE`), de la fenêtre de discussion
(`DISCUSSION`), arrondi des coins (`RAYON_MAX`). Les couleurs et icônes sont dans **composants.py**,
l'effet goutte d'eau (col liquide, rebonds) dans **goutte.py**, Plop dans **mascotte.py**.
Les tuiles de l'accueil (sections « Rapide », « Mon PC ») sont en haut de **island.py** : `ACCUEIL_RAPIDE`,
`ACCUEIL_PC`. La section « Mes applis » se remplit seule avec ce qui est installé (`USAGES_ACCUEIL`).
Pour refaire le logo après avoir modifié Plop : `python logo.py` (ajoute `--raccourci` pour le raccourci du Bureau).

## Ajouter une capacité

Dans **tools.py** : écris une fonction, ajoute-la dans `FONCTIONS` et décris-la dans `schemas()`.
L'IA saura l'utiliser toute seule.

## Mails

Rien à écrire dans un fichier : sur l'accueil, tuile **Connecter mes mails** (ou clic droit sur la goutte ›
**Messagerie…**, ou « connecte ma messagerie »). Tape ton adresse et ton mot de passe, **Tester et connecter**.

- Le serveur est reconnu tout seul pour Orange / Wanadoo, Gmail, Free, SFR, La Poste, Bouygues, Yahoo, iCloud,
  GMX, AOL ; pour une autre adresse, il est cherché dans l'annuaire public de Thunderbird (tu peux aussi le taper).
- Le panneau te dit ce que ton fournisseur demande. **Gmail, Yahoo, iCloud** : un « mot de passe d'application »
  (lien donné), pas ton mot de passe habituel. **Orange, Free, SFR…** : ton mot de passe habituel.
- **Outlook / Hotmail / Live** : Microsoft n'accepte plus la connexion par mot de passe, ces boîtes ne peuvent
  pas être connectées pour l'instant.
- Le mot de passe est rangé dans le coffre de Windows (chiffré avec ta session), jamais dans un fichier.
  La lecture ne modifie rien : aucun mail n'est marqué comme lu ni supprimé.
- Ensuite : « mes mails » (liste immédiate), « résume mes derniers mails » (résumé par l'IA).
- Sur un réseau d'entreprise ou d'école, les mails personnels sont souvent bloqués : la connexion échouera.

## Si ça ne marche pas

- « Le moteur d'IA a un souci » → réessaie : il redémarre tout seul. Le premier lancement télécharge 5 Go : vérifie ta connexion (le proxy de Windows est utilisé), le téléchargement reprend où il s'était arrêté.
- L'IA est lente → sans carte graphique dédiée, compte 10 à 40 secondes par demande (la réponse s'écrit au fur et à
  mesure, et le carré arrête une demande trop longue). Les demandes simples passent par les ordres directs,
  instantanés. Laisse `reflexion: false` et `prechauffer_ia: true` dans config.yaml. Un modèle plus petit n'est
  pas forcément plus rapide : `qwen3:4b` s'est révélé dix fois plus lent ici, il réfléchit à voix haute.
- Le micro ne marche pas → vérifie que Windows autorise l'accès au micro pour les applications de bureau.
