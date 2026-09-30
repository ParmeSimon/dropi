# ✦ Assistant Island — ton assistant IA 100 % local

Une goutte d'eau façon Dynamic Island collée au bord de ton écran, au style Windows 11,
avec **Plop** dedans : une petite mascotte blanche et violette animée en 3D qui réagit à ce que tu fais.
C'est aussi le logo de l'appli (`logo.png`, `logo.ico`).
Tout tourne sur ton PC : rien n'est envoyé sur internet, sauf pour lire tes mails et quand il se renseigne
(il n'envoie alors que ta question à DuckDuckGo / Wikipédia).

## Installation (une seule fois)

1. Installe **Python 3.11 ou plus** depuis python.org (coche « Add Python to PATH »).
2. Installe **Ollama** depuis ollama.com.
3. Double-clique sur **installer.bat** (télécharge les dépendances et le modèle IA, quelques Go).
4. Ouvre **config.yaml** et adapte : tes dossiers de rangement, tes streamers, tes applis, ton mail.

## L'appli Assistant.exe

Double-clique sur **construire_exe.bat** : il fabrique **Assistant.exe** (avec Plop en icône),
l'installe dans `%LOCALAPPDATA%\Programs\Assistant Island`, crée un raccourci sur le Bureau et dans
le menu Démarrer, et le lance **au démarrage de Windows** (clic droit sur la goutte pour couper).
Sa config est `config.yaml` à côté de Assistant.exe. Relance construire_exe.bat après une mise à jour :
ta config, ta mémoire et ton journal sont gardés.

Une seule goutte à la fois : relancer l'appli ouvre simplement celle qui tourne.
Si quelque chose plante, le détail est dans `%APPDATA%\AssistantIle\erreurs.log`.

## Lancement (version script)

Double-clique sur **lancer.bat** (ou sur le raccourci **Assistant** du Bureau). La goutte apparaît là où tu l'avais laissée.

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
Pour refaire le logo après avoir modifié Plop : `python logo.py` (ajoute `--raccourci` pour le raccourci du Bureau).

## Ajouter une capacité

Dans **tools.py** : écris une fonction, ajoute-la dans `FONCTIONS` et décris-la dans `schemas()`.
L'IA saura l'utiliser toute seule.

## Mails (Gmail)

1. Active la validation en 2 étapes sur ton compte Google.
2. Crée un mot de passe d'application sur myaccount.google.com/apppasswords.
3. Colle ton adresse et ce mot de passe dans la section `email` de config.yaml.

## Si ça ne marche pas

- « Ollama est bien lancé ? » → ouvre l'appli Ollama, ou tape `ollama serve` dans un terminal.
- L'IA est lente → prends un modèle plus petit dans config.yaml (`qwen3:4b`).
- Le micro ne marche pas → vérifie que Windows autorise l'accès au micro pour les applications de bureau.
