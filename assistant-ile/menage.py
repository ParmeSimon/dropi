"""Le ménage du disque : trouve ce qui prend de la place pour rien.

Rien n'est supprimé sans ton accord (la carte « Faire de la place » te laisse choisir) :
- fichiers temporaires de Windows et des applis : supprimés pour de bon (ils ne servent plus) ;
- tes fichiers (vieux installateurs, doublons, gros fichiers oubliés) : envoyés à la corbeille,
  donc récupérables. La place n'est vraiment libérée qu'en vidant la corbeille.
"""
import os
import time
import ctypes
import hashlib
import shutil
from pathlib import Path

from send2trash import send2trash

import classement

DOSSIERS_PERSO = ["~/Downloads", "~/Desktop", "~/Documents", "~/Pictures", "~/Videos", "~/Music"]
IGNORES = {"node_modules", ".git", "__pycache__", ".venv", "venv", "$recycle.bin", "appdata", ".gradle",
           ".idea", ".vs", "site-packages", "onedrive", "my games", "saved games", "steamlibrary"}
# Doublons et gros fichiers : seulement tes fichiers « de contenu » (jamais les sauvegardes de jeux,
# projets, bases de données… qui ont d'autres extensions)
CONTENU = {e for _, exts in classement.TYPES_PAR_DEFAUT.values() for e in exts} | {".iso", ".img"}
INSTALLATEURS = {".exe", ".msi", ".msix", ".msixbundle", ".appx"}
MIN_DOUBLON = 1_000_000            # on ne cherche pas les doublons de moins de 1 Mo
MIN_GROS = 300_000_000             # « gros » fichier : 300 Mo et plus
JOURS_GROS = 180                   # pas ouvert ni modifié depuis 6 mois
JOURS_INSTALLATEUR = 7
LIMITE_FICHIERS = 300_000
LIMITE_SECONDES = 60

derniere_analyse = None


class Categorie:
    def __init__(self, cle, titre, description, icone, definitif=False, coche=True):
        self.cle, self.titre, self.description, self.icone = cle, titre, description, icone
        self.definitif = definitif
        self.coche = coche
        self.fichiers = []                 # (chemin, taille)

    @property
    def total(self):
        return sum(t for _, t in self.fichiers)


def taille_lisible(octets):
    for unite in ("o", "Ko", "Mo", "Go", "To"):
        if octets < 1024 or unite == "To":
            return f"{octets:.0f} {unite}" if unite in ("o", "Ko") else f"{octets:.1f} {unite}".replace(".", ",")
        octets /= 1024


def _parcourir(racine, fin):
    """Tous les fichiers sous racine (sans les dossiers techniques)."""
    pile = [racine]
    while pile and time.monotonic() < fin:
        dossier = pile.pop()
        try:
            with os.scandir(dossier) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name.lower() not in IGNORES:
                                pile.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            yield e
                    except OSError:
                        continue
        except OSError:
            continue


def _empreinte(chemin, taille):
    h = hashlib.blake2b(digest_size=16)
    with open(chemin, "rb") as f:
        if taille <= 300_000_000:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        else:                                 # très gros fichier : début + fin suffisent
            h.update(f.read(4 << 20))
            f.seek(-(4 << 20), os.SEEK_END)
            h.update(f.read(4 << 20))
    return h.hexdigest()


def corbeille():
    """(taille, nombre) de la corbeille."""
    class Info(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]
    info = Info()
    info.cbSize = ctypes.sizeof(Info)
    try:
        ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        return info.i64Size, info.i64NumItems
    except (AttributeError, OSError):
        return 0, 0


def vider_corbeille():
    taille, _ = corbeille()
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)   # sans confirmation, sans barre, sans son
    return taille


def disque():
    """(total, utilisé, libre) du disque de ton dossier perso."""
    return shutil.disk_usage(Path.home().anchor)


def analyser():
    """Cherche ce qui peut partir. Peut prendre quelques secondes."""
    global derniere_analyse
    fin = time.monotonic() + LIMITE_SECONDES
    maintenant = time.time()
    temp = Categorie("temp", "Fichiers temporaires", "Laissés par Windows et les applis, ils ne servent plus.",
                     "reglage", definitif=True)
    installeurs = Categorie("installateurs", "Vieux installateurs",
                            f"Programmes d'installation téléchargés il y a plus de {JOURS_INSTALLATEUR} jours.", "paquet")
    doublons = Categorie("doublons", "Doublons", "Le même fichier en plusieurs exemplaires : j'en garde un.", "doublon")
    gros = Categorie("gros", "Gros fichiers oubliés",
                     f"Plus de 300 Mo, pas ouverts depuis {JOURS_GROS // 30} mois. À vérifier.", "horloge", coche=False)

    # fichiers temporaires (plus vieux qu'un jour, pour ne pas gêner une appli en cours)
    for racine in {os.environ.get("TEMP", ""), os.path.expandvars(r"%LOCALAPPDATA%\Temp")} - {""}:
        for e in _parcourir(racine, fin):
            try:
                st = e.stat()
                if maintenant - st.st_mtime > 86400:
                    temp.fichiers.append((e.path, st.st_size))
            except OSError:
                pass

    # tes dossiers : installateurs, gros fichiers, candidats doublons
    par_taille, vus = {}, 0
    for dossier in DOSSIERS_PERSO:
        for e in _parcourir(str(classement._chemin(dossier)), fin):
            vus += 1
            if vus > LIMITE_FICHIERS:
                break
            try:
                st = e.stat()
            except OSError:
                continue
            ext = os.path.splitext(e.name)[1].lower()
            age = maintenant - max(st.st_mtime, st.st_atime)
            dans_telechargements = "downloads" in e.path.lower()
            if ext in INSTALLATEURS and dans_telechargements and maintenant - st.st_mtime > JOURS_INSTALLATEUR * 86400:
                installeurs.fichiers.append((e.path, st.st_size))
            elif ext in CONTENU and st.st_size >= MIN_GROS and age > JOURS_GROS * 86400:
                gros.fichiers.append((e.path, st.st_size))
            if ext in CONTENU and st.st_size >= MIN_DOUBLON:
                par_taille.setdefault(st.st_size, []).append((e.path, st.st_mtime))

    deja = {c for c, _ in installeurs.fichiers} | {c for c, _ in gros.fichiers}
    for taille, liste in par_taille.items():
        if len(liste) < 2 or time.monotonic() > fin:
            continue
        par_empreinte = {}
        for chemin, date in liste:
            try:
                par_empreinte.setdefault(_empreinte(chemin, taille), []).append((chemin, date))
            except OSError:
                pass
        for groupe in par_empreinte.values():
            if len(groupe) < 2:
                continue
            # on garde celui qui est dans le classement, sinon le plus ancien
            groupe.sort(key=lambda x: ("classement" not in x[0].lower(), x[1]))
            for chemin, _ in groupe[1:]:
                if chemin not in deja:
                    doublons.fichiers.append((chemin, taille))

    for c in (installeurs, doublons, gros):
        c.fichiers.sort(key=lambda x: -x[1])
    derniere_analyse = {
        "categories": [c for c in (temp, installeurs, doublons, gros) if c.fichiers],
        "disque": disque(),
        "corbeille": corbeille(),
        "incomplet": time.monotonic() > fin,
    }
    return derniere_analyse


def nettoyer(categories):
    """Supprime les fichiers des catégories choisies. Renvoie (octets libérés, nombre, erreurs)."""
    liberes, nombre, erreurs = 0, 0, 0
    for c in categories:
        for chemin, taille in c.fichiers:
            try:
                if c.definitif:
                    os.remove(chemin)
                else:
                    send2trash(chemin)
                    classement.noter(chemin, "Corbeille")
                liberes += taille
                nombre += 1
            except OSError:
                erreurs += 1              # fichier utilisé en ce moment : on le laisse
    return liberes, nombre, erreurs


def resume(analyse):
    """Le texte que l'IA reçoit après une analyse."""
    total, utilise, libre = analyse["disque"]
    lignes = [f"Disque : {taille_lisible(libre)} libres sur {taille_lisible(total)}."]
    for c in analyse["categories"]:
        lignes.append(f"- {c.titre} : {taille_lisible(c.total)} ({len(c.fichiers)} fichiers)")
    taille_corbeille, _ = analyse["corbeille"]
    if taille_corbeille:
        lignes.append(f"- Corbeille : {taille_lisible(taille_corbeille)}")
    lignes.append("L'interface affiche une carte où l'utilisateur choisit quoi supprimer.")
    return "\n".join(lignes)
