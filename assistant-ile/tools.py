"""Les actions que l'assistant peut faire sur ton PC.

Pour ajouter une capacité : écris une fonction ici, puis ajoute-la
dans FONCTIONS et dans schemas() en bas du fichier.
"""
import os
import re
import email
import imaplib
import difflib
import datetime
import subprocess
import webbrowser
from pathlib import Path
from email.header import decode_header, make_header

from send2trash import send2trash

import web
import musique
import memoire
import classement
import menage

CONFIG = {}


def init(config):
    CONFIG.update(config)
    classement.init({**(config.get("classement") or {}), "telechargements": config.get("telechargements") or {}})


def _chemin(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p).strip().strip('"'))))


def _lancer(cmd):
    """Lance un programme, un lien steam://, etc."""
    cmd = os.path.expandvars(os.path.expanduser(cmd))
    if "://" in cmd:
        os.startfile(cmd)
        return
    exe, _, args = cmd.partition(" --")
    argv = [exe.strip()] + (("--" + args).split() if args else [])
    dossier = os.path.dirname(exe.strip()) or None
    subprocess.Popen(argv, cwd=dossier)


def _meilleur(nom, choix):
    """Trouve le nom le plus proche dans une liste (tolère les fautes)."""
    nom = nom.lower().strip()
    choix = list(choix)
    exacts = [c for c in choix if c.lower() == nom]
    if exacts:
        return exacts[0]
    contient = [c for c in choix if nom in c.lower()]
    if contient:
        return min(contient, key=len)
    proches = difflib.get_close_matches(nom, [c.lower() for c in choix], n=1, cutoff=0.5)
    if proches:
        return next(c for c in choix if c.lower() == proches[0])
    return None


# ------------------------------------------------------------------ Web

def ouvrir_stream_twitch(streamer):
    s = streamer.lower().strip()
    login = CONFIG.get("streamers", {}).get(s, s.replace(" ", ""))
    webbrowser.open(f"https://www.twitch.tv/{login}")
    return f"Stream de {login} ouvert sur Twitch."


def ouvrir_site(site):
    sites = CONFIG.get("sites", {})
    cle = _meilleur(site, sites) if sites else None
    url = sites[cle] if cle else site
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"{url} ouvert."


def recherche_web(requete):
    webbrowser.open("https://www.google.com/search?q=" + requete.replace(" ", "+"))
    return f"Recherche lancée : {requete}"


# ------------------------------------------------------------------ Jeux et applis

def _dossier_steam():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as cle:
            return Path(winreg.QueryValueEx(cle, "SteamPath")[0])
    except OSError:
        return Path(r"C:\Program Files (x86)\Steam")


def _steam_detail():
    """{nom: appid} des jeux Steam installés, dans toutes les bibliothèques."""
    racines = [_dossier_steam(), Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    racines += [Path(d) for d in CONFIG.get("steam_dossiers", [])]
    biblios = set()
    for r in racines:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            biblios.add(r)
            texte = vdf.read_text(encoding="utf-8", errors="ignore")
            for p in re.findall(r'"path"\s+"([^"]+)"', texte):
                biblios.add(Path(p.replace("\\\\", "\\")))
    jeux = {}
    for b in biblios:
        for acf in (b / "steamapps").glob("appmanifest_*.acf"):
            t = acf.read_text(encoding="utf-8", errors="ignore")
            appid = re.search(r'"appid"\s+"(\d+)"', t)
            nom = re.search(r'"name"\s+"([^"]+)"', t)
            if appid and nom and "Steamworks" not in nom.group(1):
                jeux[nom.group(1)] = appid.group(1)
    return jeux


def _jeux_steam():
    return {nom: f"steam://rungameid/{appid}" for nom, appid in _steam_detail().items()}


def _images_steam(appid):
    """Les visuels que Steam garde sur le disque (jaquette, bannière, fond, logo, icône)."""
    cache = _dossier_steam() / "appcache" / "librarycache"
    trouve = {}
    noms = {"library_600x900.jpg": "jaquette", "library_capsule.jpg": "jaquette2", "header.jpg": "banniere",
            "library_header.jpg": "banniere", "library_hero.jpg": "fond", "logo.png": "logo"}
    dossier = cache / appid
    if dossier.is_dir():
        for f in dossier.rglob("*"):
            if f.name in noms:
                trouve.setdefault(noms[f.name], f)
            elif f.parent == dossier and f.suffix == ".jpg" and len(f.stem) == 40:
                trouve.setdefault("icone", f)
    for suffixe, cle in (("_library_600x900.jpg", "jaquette"), ("_header.jpg", "banniere"),
                         ("_library_hero.jpg", "fond"), ("_logo.png", "logo"), ("_icon.jpg", "icone")):
        if (cache / f"{appid}{suffixe}").exists():
            trouve.setdefault(cle, cache / f"{appid}{suffixe}")
    if "jaquette" not in trouve and "jaquette2" in trouve:
        trouve["jaquette"] = trouve["jaquette2"]
    trouve.pop("jaquette2", None)
    return trouve


def _icone_hors_steam(cmd):
    """Icône d'un jeu hors Steam : celle de Riot si c'est un jeu Riot, sinon celle de l'exécutable."""
    produit = re.search(r"--launch-product=(\S+)", cmd)
    if produit:
        ligne = re.search(r"--launch-patchline=(\S+)", cmd)
        nom = f"{produit.group(1)}.{ligne.group(1) if ligne else 'live'}"
        ico = Path(r"C:\ProgramData\Riot Games\Metadata") / nom / f"{nom}.ico"
        if ico.exists():
            return ico
    exe = _chemin(cmd.partition(" --")[0])
    return exe if exe.exists() else None


def _joli_nom(nom):
    petits = {"of", "the", "de", "des", "du", "la", "le"}
    mots = nom.split()
    return " ".join(m if (i and m in petits) else m[:1].upper() + m[1:] for i, m in enumerate(mots))


def catalogue_jeux():
    """Tous les jeux (Steam + config.yaml) avec leurs visuels, pour l'affichage en jaquettes."""
    jeux = [{"nom": nom, "lancement": f"steam://rungameid/{appid}", **_images_steam(appid)}
            for nom, appid in _steam_detail().items()]
    par_commande = {}
    for nom, cmd in CONFIG.get("jeux", {}).items():
        par_commande.setdefault(cmd, []).append(nom)       # « lol » et « league of legends » = un seul jeu
    for cmd, noms in par_commande.items():
        jeux.append({"nom": _joli_nom(max(noms, key=len)), "lancement": cmd, "icone": _icone_hors_steam(cmd)})
    return sorted(jeux, key=lambda j: j["nom"].lower())


def trouver_jeu(nom):
    """Le jeu du catalogue qui correspond à un nom (tolère les fautes et les surnoms)."""
    catalogue = catalogue_jeux()
    par_nom = {j["nom"]: j for j in catalogue}
    for alias, cmd in CONFIG.get("jeux", {}).items():
        par_nom.setdefault(alias, next((j for j in catalogue if j["lancement"] == cmd), None))
    trouve = _meilleur(nom, par_nom)
    return par_nom[trouve] if trouve else None


def lister_jeux():
    noms = [j["nom"] for j in catalogue_jeux()]
    return "Jeux disponibles : " + ", ".join(noms) if noms else "Aucun jeu trouvé."


def lancer_jeu(nom):
    jeu = trouver_jeu(nom)
    if not jeu:
        return f"Jeu « {nom} » introuvable. Jeux connus : {', '.join(j['nom'] for j in catalogue_jeux()) or 'aucun'}"
    _lancer(jeu["lancement"])
    return f"{jeu['nom']} se lance."


def ouvrir_application(nom):
    applis = CONFIG.get("applications", {})
    trouve = _meilleur(nom, applis)
    if trouve:
        _lancer(applis[trouve])
        return f"{trouve} ouvert."
    try:
        os.startfile(nom)
        return f"{nom} ouvert."
    except OSError:
        return f"Application « {nom} » inconnue. Ajoute-la dans config.yaml."


# ------------------------------------------------------------------ Fichiers
# Rangement méthodique TYPE / SOURCE et journal des déplacements : voir classement.py

def _fichier(chemin):
    """Le fichier demandé, même s'il a été rangé ailleurs entre-temps."""
    return classement.retrouver(chemin)


def ranger_fichier(chemin):
    src = _fichier(chemin)
    if not src.exists():
        return f"Fichier introuvable : {src}"
    dest, type_, source = classement.ranger(src)
    if dest == src:
        return f"« {src.name} » est déjà bien rangé ({classement.joli(dest.parent)})."
    return f"« {src.name} » rangé dans {classement.court(dest.parent)} ({dest})."


def supprimer_fichier(chemin):
    src = _fichier(chemin)
    if not src.exists():
        return f"Introuvable : {src}"
    send2trash(str(src))
    classement.noter(src, "Corbeille")
    return f"« {src.name} » envoyé à la corbeille (récupérable)."


def deplacer_fichier(chemin, destination):
    src, dest = _fichier(chemin), _chemin(destination)
    if not src.exists():
        return f"Introuvable : {src}"
    nouveau = classement.deplacer(src, dest)
    return f"« {src.name} » déplacé dans {dest} ({nouveau})."


def renommer_fichier(chemin, nouveau_nom):
    src = _fichier(chemin)
    if not src.exists():
        return f"Introuvable : {src}"
    nom = Path(str(nouveau_nom).strip()).name
    if not Path(nom).suffix and src.suffix:
        nom += src.suffix  # garde l'extension si l'IA l'oublie
    dest = src.with_name(nom)
    if dest.exists():
        return f"« {nom} » existe déjà dans ce dossier."
    src.rename(dest)
    classement.noter(src, dest)
    return f"« {src.name} » renommé en « {dest.name} »."


def afficher_dans_explorateur(chemin):
    p = _fichier(chemin)
    if not p.exists():
        return f"Introuvable : {p}"
    if p.is_dir():
        os.startfile(str(p))
    else:
        subprocess.Popen(f'explorer /select,"{p}"')
    return f"{p.name} affiché dans l'explorateur."


def lire_fichier(chemin):
    """Lit le début d'un fichier texte ou PDF pour que l'IA puisse le résumer."""
    p = _fichier(chemin)
    if not p.is_file():
        return f"Introuvable : {p}"
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "Pour lire les PDF, installe pypdf (relance installer.bat)."
        pages = PdfReader(str(p)).pages[:10]
        texte = "\n".join(page.extract_text() or "" for page in pages)
    else:
        with open(p, "rb") as f:
            brut = f.read(20000)
        if b"\x00" in brut[:2000]:
            return "C'est un fichier binaire, je ne peux pas le lire."
        texte = brut.decode("utf-8", errors="ignore")
    texte = texte.strip()
    if not texte:
        return "Aucun texte lisible dans ce fichier."
    return f"(Fichier : {p})\n" + texte[:4000] + ("\n[… suite coupée]" if len(texte) > 4000 else "")


def lister_dossier(dossier):
    d = _chemin(dossier)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    elements = sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
    return "\n".join(("[dossier] " if p.is_dir() else "") + str(p) for p in elements) or "Dossier vide."


def fichiers_telechargements():
    d = classement.dossier_telechargements()
    return [p for p in d.iterdir() if p.is_file() and not classement.est_partiel(p)] if d.is_dir() else []


def _ranger_liste(fichiers, sous_dossiers=0):
    par_dossier, erreurs = {}, []
    for p in fichiers:
        try:
            dest, _, _ = classement.ranger(p)
            par_dossier.setdefault(classement.court(dest.parent), []).append(p.name)
        except OSError as ex:
            erreurs.append(f"{p.name} : {ex}")
    lignes = [f"{len(fichiers) - len(erreurs)} fichiers rangés :"]
    lignes += [f"- {dossier} : {', '.join(noms[:4])}{' …' if len(noms) > 4 else ''}"
               for dossier, noms in sorted(par_dossier.items())]
    if erreurs:
        lignes.append("Pas pu ranger (fichier ouvert ?) : " + "; ".join(erreurs[:3]))
    if sous_dossiers:
        lignes.append(f"{sous_dossiers} sous-dossiers laissés tels quels (je ne mélange pas leur contenu).")
    return "\n".join(lignes)


def ranger_telechargements():
    fichiers = fichiers_telechargements()
    return _ranger_liste(fichiers) if fichiers else "Téléchargements déjà rangés."


def ranger_dossier(dossier):
    """Range les fichiers d'un dossier (le Bureau, un vieux dossier…). Les sous-dossiers ne sont pas touchés."""
    d = _chemin(dossier)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    elements = list(d.iterdir())
    fichiers = [p for p in elements if p.is_file() and not classement.est_partiel(p)]
    sous = sum(1 for p in elements if p.is_dir())
    return _ranger_liste(fichiers, sous) if fichiers else f"Aucun fichier à ranger dans {d}."


def chercher_fichier(nom):
    resultats = []
    for e, existe in classement.recherche_journal(nom, 5):      # d'abord ce que j'ai rangé moi-même
        if existe:
            resultats.append(f"{e['apres']} (rangé par moi le {e['date'][:10]})")
    bases = ["~/Desktop", "~/Documents", "~/Downloads", "~/Pictures", "~/Videos", "~/Music"]
    for base in bases:
        for p in _chemin(base).rglob(f"*{nom}*"):
            if not any(str(p) in r for r in resultats):
                resultats.append(str(p))
            if len(resultats) >= 15:
                return "\n".join(resultats)
    return "\n".join(resultats) or f"Aucun fichier contenant « {nom} »."


def ouvrir_fichier(chemin):
    p = _fichier(chemin)
    if not p.exists():
        return f"Introuvable : {p}"
    os.startfile(str(p))
    return f"{p.name} ouvert."


def annuler_rangement():
    return classement.annuler_dernier()


def analyser_espace():
    return menage.resume(menage.analyser())


# ------------------------------------------------------------------ Mails

def _texte_mail(msg):
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "text/plain":
            data = part.get_payload(decode=True) or b""
            return data.decode(part.get_content_charset() or "utf-8", errors="ignore")
    return ""


def mails_recents(nombre=5):
    cfg = CONFIG.get("email", {})
    if not cfg.get("adresse") or not cfg.get("mot_de_passe_app"):
        return "Mail non configuré : remplis la section email de config.yaml."
    nombre = max(1, min(int(nombre), 15))
    sortie = []
    with imaplib.IMAP4_SSL(cfg["serveur_imap"]) as m:
        m.login(cfg["adresse"], cfg["mot_de_passe_app"])
        m.select("INBOX", readonly=True)
        _, data = m.search(None, "ALL")
        for num in reversed(data[0].split()[-nombre:]):
            _, contenu = m.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(contenu[0][1])
            de = str(make_header(decode_header(msg.get("From", ""))))
            sujet = str(make_header(decode_header(msg.get("Subject", ""))))
            corps = " ".join(_texte_mail(msg).split())[:400]
            sortie.append(f"De : {de}\nSujet : {sujet}\nDate : {msg.get('Date', '')}\nExtrait : {corps}")
    return "\n\n".join(sortie) or "Boîte vide."


# ------------------------------------------------------------------ Divers

def se_renseigner(question):
    return web.se_renseigner(question)


def memoriser(information):
    memoire.retenir(information, genre="preference")
    return "C'est noté, je m'en souviendrai."


def controler_musique(action):
    if not musique.derniere:
        return "Aucune musique en cours."
    musique.commander(action)
    return {"pause": "Pause / lecture.", "lecture": "Pause / lecture.", "suivant": "Morceau suivant.",
            "precedent": "Morceau précédent."}.get(action, "C'est fait.")


def musique_en_cours():
    return musique.en_cours_texte()


def date_heure():
    return datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")


# ------------------------------------------------------------------ Déclaration pour l'IA

FONCTIONS = {f.__name__: f for f in [
    ouvrir_stream_twitch, ouvrir_site, recherche_web, lister_jeux, lancer_jeu,
    ouvrir_application, ranger_fichier, supprimer_fichier, deplacer_fichier,
    renommer_fichier, afficher_dans_explorateur, lire_fichier,
    lister_dossier, ranger_telechargements, chercher_fichier, ouvrir_fichier,
    ranger_dossier, annuler_rangement, analyser_espace, mails_recents, date_heure,
    se_renseigner, memoriser, controler_musique, musique_en_cours,
]}


def _outil(nom, description, proprietes=None, requis=None):
    return {"type": "function", "function": {
        "name": nom, "description": description,
        "parameters": {"type": "object", "properties": proprietes or {}, "required": requis or []},
    }}


def _texte(desc):
    return {"type": "string", "description": desc}


def schemas():
    return [
        _outil("ouvrir_stream_twitch", "Ouvre le stream Twitch d'un streamer.",
               {"streamer": _texte("Nom du streamer, ex: kameto")}, ["streamer"]),
        _outil("ouvrir_site", "Ouvre un site web (nom de favori ou URL).",
               {"site": _texte("ex: youtube ou lemonde.fr")}, ["site"]),
        _outil("recherche_web", "Ouvre une recherche Google dans le navigateur (seulement si l'utilisateur veut voir "
               "les résultats lui-même).", {"requete": _texte("La recherche")}, ["requete"]),
        _outil("se_renseigner", "Cherche une information sur internet (DuckDuckGo, Wikipédia) et renvoie le texte trouvé. "
               "À utiliser pour toute question sur un sujet que tu ne connais pas bien ou récent "
               "(jeu, film, produit, actualité, personne, logiciel).",
               {"question": _texte("La recherche, précise, ex : RoadCraft jeu vidéo")}, ["question"]),
        _outil("memoriser", "Retiens une information pour toujours : une préférence de l'utilisateur, une correction "
               "qu'il te fait, un fait sur lui (ex : « Il range ses cours dans Documents/Cours »).",
               {"information": _texte("L'information à retenir, en une phrase")}, ["information"]),
        _outil("lister_jeux", "Liste les jeux installés."),
        _outil("lancer_jeu", "Lance un jeu installé.", {"nom": _texte("Nom du jeu")}, ["nom"]),
        _outil("ouvrir_application", "Ouvre une application (Discord, Spotify…).",
               {"nom": _texte("Nom de l'application")}, ["nom"]),
        _outil("ranger_fichier", "Range un fichier à sa place : dossier du TYPE (PDF, Word, Images…) puis de la SOURCE "
               "(site ou appli d'où il vient). Le dossier est choisi automatiquement.",
               {"chemin": _texte("Chemin complet du fichier")}, ["chemin"]),
        _outil("supprimer_fichier", "Envoie un fichier à la corbeille. Seulement si l'utilisateur le demande explicitement.",
               {"chemin": _texte("Chemin complet")}, ["chemin"]),
        _outil("deplacer_fichier", "Déplace un fichier vers un dossier précis.",
               {"chemin": _texte("Chemin du fichier"), "destination": _texte("Dossier de destination")},
               ["chemin", "destination"]),
        _outil("renommer_fichier", "Renomme un fichier (il reste dans le même dossier).",
               {"chemin": _texte("Chemin complet du fichier"), "nouveau_nom": _texte("Nouveau nom, ex: facture_edf_mars.pdf")},
               ["chemin", "nouveau_nom"]),
        _outil("afficher_dans_explorateur", "Montre un fichier dans l'explorateur Windows.",
               {"chemin": _texte("Chemin complet")}, ["chemin"]),
        _outil("lire_fichier", "Lit le contenu d'un fichier texte ou PDF (pour le résumer ou répondre à une question dessus).",
               {"chemin": _texte("Chemin complet")}, ["chemin"]),
        _outil("lister_dossier", "Liste le contenu d'un dossier (plus récents en premier).",
               {"dossier": _texte("ex: ~/Downloads ou ~/Desktop")}, ["dossier"]),
        _outil("ranger_telechargements", "Range automatiquement tout le dossier Téléchargements."),
        _outil("ranger_dossier", "Range les fichiers d'un dossier (ex : le Bureau). Les sous-dossiers restent intacts.",
               {"dossier": _texte("ex: ~/Desktop")}, ["dossier"]),
        _outil("chercher_fichier", "Cherche un fichier par son nom sur le PC (y compris ceux que tu as rangés).",
               {"nom": _texte("Partie du nom du fichier")}, ["nom"]),
        _outil("ouvrir_fichier", "Ouvre un fichier avec son application par défaut.",
               {"chemin": _texte("Chemin complet")}, ["chemin"]),
        _outil("mails_recents", "Récupère les derniers mails reçus pour les résumer.",
               {"nombre": {"type": "integer", "description": "Nombre de mails (défaut 5)"}}),
        _outil("date_heure", "Donne la date et l'heure actuelles."),
        _outil("controler_musique", "Contrôle la musique en cours (Apple Music, Spotify…).",
               {"action": {"type": "string", "enum": ["pause", "lecture", "suivant", "precedent"]}}, ["action"]),
        _outil("musique_en_cours", "Dit quelle musique joue en ce moment."),
        _outil("annuler_rangement", "Remet le dernier fichier rangé ou déplacé à son ancienne place."),
        _outil("analyser_espace", "Analyse le disque pour faire de la place (fichiers temporaires, vieux installateurs, "
               "doublons, gros fichiers oubliés). Ne supprime rien : l'utilisateur choisit ensuite."),
    ]
