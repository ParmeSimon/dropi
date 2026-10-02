"""L'inventaire : ce qu'il y a vraiment sur le PC, vu par thème, SANS rien déplacer.

Le tableau de bord ne doit pas afficher « vide » sous prétexte que rien n'a encore été rangé dans Documents/Dropi.
On regarde donc tes dossiers habituels (Documents, Bureau, Téléchargements, Images, Vidéos, Musique, y compris s'ils
sont redirigés vers OneDrive) et on dit, pour chaque fichier, dans quel thème il irait.

Deux sortes de fichiers :
- « en vrac » : posés directement dans un de ces dossiers, ou dans l'ancien classement de Dropi (Classement/PDF/Gmail…).
  Ceux-là, Dropi peut les ranger d'un coup ;
- « dans un de tes dossiers » (ecole, Hackaton, Screenshots…) : tu les as organisés toi-même, Dropi les montre mais ne
  les sort jamais de leur dossier tout seul. Tu peux déplacer le dossier entier dans un thème.

Les dossiers de code (ceux qui contiennent .git, package.json…) et les dossiers techniques sont ignorés.
"""
import os
import time
from pathlib import Path

import classement
import themes

PROFONDEUR = 4                      # jusqu'où on descend dans tes dossiers
LIMITE = 30000                      # fichiers au plus (au-delà on s'arrête : le tableau de bord doit rester vif)
IGNORES = {"node_modules", "__pycache__", "venv", ".venv", "env", "appdata", "$recycle.bin", "system volume information",
           "modèles office personnalisés", "office scripts", "fichiers outlook", "ultravnc", "adobe", "dist", "build",
           "target", "vendor", "cache", "caches", "temp", "tmp", "lib", "bin", "obj",
           "ma musique", "mes images", "mes vidéos", "my music", "my pictures", "my videos"}     # raccourcis hérités de Windows
MARQUEURS_PROJET = {".git", "package.json", "pyproject.toml", "composer.json", "pubspec.yaml", "cargo.toml", "pom.xml",
                    "build.gradle", "requirements.txt", "makefile", "cmakelists.txt", ".sln", "symfony.lock"}


def lieux():
    """Tes dossiers habituels : [(nom, chemin)]. Windows peut les avoir déplacés (OneDrive) : on lui demande les vrais."""
    trouves, vus = [], set()
    try:
        from PySide6.QtCore import QStandardPaths as S
        connus = [("Téléchargements", S.DownloadLocation), ("Bureau", S.DesktopLocation), ("Documents", S.DocumentsLocation),
                  ("Images", S.PicturesLocation), ("Vidéos", S.MoviesLocation), ("Musique", S.MusicLocation)]
        candidats = [(nom, Path(S.writableLocation(lieu))) for nom, lieu in connus]
    except Exception:
        candidats = []
    candidats += [(nom, Path.home() / d) for nom, d in (("Téléchargements", "Downloads"), ("Bureau", "Desktop"),
                                                       ("Documents", "Documents"), ("Images", "Pictures"),
                                                       ("Vidéos", "Videos"), ("Musique", "Music"))]
    for nom, chemin in candidats:
        cle = str(chemin).lower()
        if cle not in vus and chemin.is_dir():
            vus.add(cle)
            trouves.append((nom, chemin))
    return trouves


def _est_projet(noms):
    return any(n.lower() in MARQUEURS_PROJET or n.lower().endswith(".sln") for n in noms)


def _classer(chemin, contexte, vrac):
    """Le thème d'un fichier, d'après son nom, sa source (pour les fichiers en vrac) et le nom de ses dossiers."""
    p = Path(chemin)
    try:
        source = classement.source_de(p)               # le site d'origine, ou ce que dit le nom (capture d'écran, photo de téléphone…)
    except OSError:
        source = ""
    if vrac and source == classement.INCONNUE and contexte:
        source = contexte[-1]                          # ancien classement : le dossier s'appelait comme la source (Ameli, Gmail…)
    return themes.classer(p, source, " ".join(contexte))


def faire():
    """L'inventaire complet. {"fichiers": [{"chemin", "theme", "sous", "vrac", "lieu"}], "dossiers": [...], "date", "coupe"}"""
    racine = classement.racine()
    fichiers, dossiers_perso, coupe = [], [], False

    def visiter(dossier, nom_lieu, contexte, niveau, vrac):
        nonlocal coupe
        if coupe:
            return
        try:
            with os.scandir(dossier) as contenu:
                entrees = list(contenu)
        except OSError:
            return
        noms = [e.name for e in entrees]
        if niveau > 0 and _est_projet(noms):
            return                                     # un dossier de code : on n'y touche pas, on ne le liste pas
        for e in entrees:
            nom = e.name
            if nom.startswith((".", "~$", "$")) or nom.lower() in ("desktop.ini", "thumbs.db"):
                continue
            try:
                est_dossier = e.is_dir()
            except OSError:
                continue
            chemin = Path(e.path)
            if est_dossier:
                if nom.lower() in IGNORES or chemin == racine or racine in chemin.parents:
                    continue
                if niveau < PROFONDEUR:
                    visiter(chemin, nom_lieu, contexte + [nom], niveau + 1, vrac)
                continue
            if classement.est_partiel(chemin) or nom.lower().endswith(".lnk"):
                continue
            if len(fichiers) >= LIMITE:
                coupe = True
                return
            resultat = _classer(chemin, contexte, vrac)
            fichiers.append({"chemin": str(chemin), "theme": resultat["theme"], "sous": resultat["sous"],
                             "vrac": vrac, "lieu": nom_lieu})

    for nom_lieu, chemin in lieux():
        # à la racine d'un lieu, les fichiers sont « en vrac » ; les sous-dossiers ne le sont que s'ils viennent de l'ancien classement
        try:
            with os.scandir(chemin) as contenu:
                entrees = list(contenu)
        except OSError:
            continue
        for e in entrees:
            nom = e.name
            if nom.startswith((".", "~$", "$")) or nom.lower() in ("desktop.ini", "thumbs.db"):
                continue
            p = Path(e.path)
            try:
                est_dossier = e.is_dir()
            except OSError:
                continue
            if not est_dossier:
                if classement.est_partiel(p) or nom.lower().endswith(".lnk") or len(fichiers) >= LIMITE:
                    continue
                resultat = _classer(p, [], True)
                fichiers.append({"chemin": str(p), "theme": resultat["theme"], "sous": resultat["sous"], "vrac": True, "lieu": nom_lieu})
            elif nom.lower() == "classement":
                visiter(p, nom_lieu, [], 1, True)                       # l'ancien classement de Dropi : tout est à ranger
            elif nom.lower() not in IGNORES and p != racine and racine not in p.parents:
                dossiers_perso.append({"chemin": str(p), "lieu": nom_lieu})
                visiter(p, nom_lieu, [nom], 1, False)                   # tes dossiers : on montre, on ne déplace pas
    return {"fichiers": fichiers, "dossiers": dossiers_perso, "date": time.time(), "coupe": coupe}


def comptes(inventaire):
    """{thème: (nombre en vrac, nombre dans tes dossiers)}"""
    resultat = {d: [0, 0] for d, _ in themes.ARBORESCENCE}
    for f in inventaire.get("fichiers", []):
        if f["theme"] in resultat:
            resultat[f["theme"]][0 if f["vrac"] else 1] += 1
    return {k: tuple(v) for k, v in resultat.items()}
