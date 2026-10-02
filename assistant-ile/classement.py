"""Le rangement : chaque fichier va dans le bon dossier, et le journal note tout.

Deux modes (config.yaml, classement: mode:)
- « theme » (par défaut) : THÈME / SOUS-THÈME / ANNÉE, voir themes.py. Études > Cours > 2026, Administratif > Impôts > 2026…
  Dropi lit le nom, la source et le début du contenu ; si c'est flou, le fichier attend dans « À trier » et l'IA
  locale le classe en tâche de fond.
- « type » (l'ancien) : TYPE / SOURCE, expliqué ci-dessous.

Mode « type » :
- le TYPE vient de l'extension (PDF, Word, Bloc-notes, Images…) ;
- la SOURCE est le site ou l'appli d'où il vient. Quand tu télécharges un fichier, Windows note
  l'adresse du site dans une « étiquette » cachée (Zone.Identifier) : on la lit. Sinon on devine
  d'après le nom (Capture d'écran, WhatsApp…), et en dernier recours : « Origine inconnue ».

Exemple : une facture PDF reçue sur Gmail -> Documents/Classement/PDF/Gmail/facture.pdf

Chaque déplacement est noté dans un journal : l'assistant sait toujours où il a mis un fichier.
"""
import os
import re
import json
import shutil
import datetime
import queue
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import donnees
import themes

JOURNAL = donnees.fichier("journal_rangement.json")
_verrou = threading.Lock()

TYPES_PAR_DEFAUT = {
    "PDF": ("~/Documents/Classement/PDF", [".pdf"]),
    "Word": ("~/Documents/Classement/Word", [".doc", ".docx", ".odt", ".rtf"]),
    "Bloc-notes": ("~/Documents/Classement/Bloc-notes", [".txt", ".md", ".log"]),
    "Tableurs": ("~/Documents/Classement/Tableurs", [".xls", ".xlsx", ".csv", ".ods"]),
    "Présentations": ("~/Documents/Classement/Présentations", [".ppt", ".pptx", ".odp"]),
    "Images": ("~/Pictures/Classement", [".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg", ".avif"]),
    "Vidéos": ("~/Videos/Classement", [".mp4", ".mov", ".mkv", ".avi", ".webm"]),
    "Musique": ("~/Music/Classement", [".mp3", ".wav", ".flac", ".m4a", ".ogg"]),
    "Archives": ("~/Downloads/Classement/Archives", [".zip", ".rar", ".7z", ".tar", ".gz"]),
    "Installateurs": ("~/Downloads/Classement/Installateurs", [".exe", ".msi", ".msix"]),
    "Dossiers": ("~/Documents/Classement/Dossiers", []),
    "Autres": ("~/Documents/Classement/Autres", []),
}

# Noms lisibles des sites et applis connus (on compare la fin de l'adresse)
SOURCES = {
    "mail.google.com": "Gmail", "drive.google.com": "Google Drive", "docs.google.com": "Google Docs",
    "photos.google.com": "Google Photos", "outlook.live.com": "Outlook", "outlook.office.com": "Outlook",
    "outlook.office365.com": "Outlook", "onedrive.live.com": "OneDrive", "1drv.ms": "OneDrive",
    "sharepoint.com": "OneDrive", "discord.com": "Discord", "discordapp.com": "Discord",
    "discordapp.net": "Discord", "whatsapp.com": "WhatsApp", "whatsapp.net": "WhatsApp",
    "telegram.org": "Telegram", "github.com": "GitHub", "githubusercontent.com": "GitHub",
    "youtube.com": "YouTube", "twitter.com": "X", "x.com": "X", "twimg.com": "X",
    "instagram.com": "Instagram", "cdninstagram.com": "Instagram", "facebook.com": "Facebook",
    "fbcdn.net": "Facebook", "messenger.com": "Messenger", "pinterest.com": "Pinterest",
    "pinterest.fr": "Pinterest", "pinimg.com": "Pinterest", "reddit.com": "Reddit", "redd.it": "Reddit",
    "snapchat.com": "Snapchat", "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "licdn.com": "LinkedIn",
    "amazon.fr": "Amazon", "amazon.com": "Amazon", "leboncoin.fr": "Leboncoin", "vinted.fr": "Vinted",
    "impots.gouv.fr": "Impôts", "ameli.fr": "Ameli", "caf.fr": "CAF", "edf.fr": "EDF",
    "service-public.fr": "Service Public", "francetravail.fr": "France Travail", "doctolib.fr": "Doctolib",
    "sncf-connect.com": "SNCF", "dropbox.com": "Dropbox", "dropboxusercontent.com": "Dropbox",
    "wetransfer.com": "WeTransfer", "chatgpt.com": "ChatGPT", "openai.com": "ChatGPT", "claude.ai": "Claude",
    "anthropic.com": "Claude", "canva.com": "Canva", "notion.so": "Notion", "steampowered.com": "Steam",
    "steamstatic.com": "Steam", "epicgames.com": "Epic Games", "microsoft.com": "Microsoft",
    "ecoledirecte.com": "École Directe", "index-education.net": "Pronote", "moodle": "Moodle",
    "curseforge.com": "CurseForge", "nexusmods.com": "Nexus Mods", "jetbrains.com": "JetBrains",
    "mozilla.org": "Mozilla", "python.org": "Python", "nvidia.com": "NVIDIA", "amd.com": "AMD",
}
# Serveurs de stockage anonymes : la vraie source est alors la page d'où on a cliqué
CDN = ("googleusercontent.com", "cloudfront.net", "amazonaws.com", "akamaihd.net", "akamaized.net",
       "fastly.net", "azureedge.net", "windows.net", "cloudflare.com", "cloudflarestorage.com",
       "r2.dev", "b-cdn.net", "gstatic.com", "bunnycdn.com", "backblazeb2.com")
DOUBLES_EXTENSIONS = ("gouv.fr", "co.uk", "com.au", "co.jp", "com.br", "ac.uk", "org.uk")
PARTIELS = (".crdownload", ".part", ".partial", ".tmp", ".opdownload", ".download")
INCONNUE = "Origine inconnue"

CONFIG = {}
CLASSIFIEUR = None          # fonction(nom, extrait, categories) -> "01 Études/Cours" ou None : l'IA locale (branchée par l'appli)
SUR_RECLASSE = None         # fonction(nom, nouveau chemin) appelée quand l'IA a rangé un fichier en arrière-plan
RACINE_PAR_DEFAUT = "~/Documents/Dropi"
ANCIENS_DOSSIERS = ["~/Documents/Classement", "~/Pictures/Classement", "~/Videos/Classement", "~/Music/Classement",
                    "~/Downloads/Classement"]


def init(config):
    CONFIG.clear()
    CONFIG.update(config or {})


def _chemin(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p).strip().strip('"'))))


def _types():
    types = {nom: {"dossier": d, "extensions": e} for nom, (d, e) in TYPES_PAR_DEFAUT.items()}
    for nom, regle in (CONFIG.get("types") or {}).items():
        types.setdefault(nom, {"dossier": f"~/Documents/Classement/{nom}", "extensions": []}).update(regle or {})
    return types


# ------------------------------------------------------------------ type et source

def type_de(p):
    p = Path(p)
    if p.is_dir():
        return "Dossiers"
    ext = p.suffix.lower()
    for nom, regle in _types().items():
        if ext in [e.lower() for e in regle.get("extensions", [])]:
            return nom
    return "Autres"


def _etiquette_windows(p):
    """L'étiquette cachée que Windows colle aux fichiers téléchargés (adresse du site)."""
    try:
        with open(str(p) + ":Zone.Identifier", encoding="utf-8", errors="ignore") as f:
            return dict(re.findall(r"^(\w+)=(.*?)\s*$", f.read(), re.M))
    except OSError:
        return {}


def _domaine(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("blob:"):
        url = url[5:]
    if not url.startswith(("http://", "https://")):
        return ""
    return (urlparse(url).hostname or "").lower()


def nom_du_site(domaine):
    perso = CONFIG.get("sources") or {}
    for table in (perso, SOURCES):
        for cle, nom in table.items():
            if domaine == cle or domaine.endswith("." + cle) or (cle == "moodle" and "moodle" in domaine):
                return nom
    morceaux = domaine.split(".")
    if len(morceaux) >= 3 and ".".join(morceaux[-2:]) in DOUBLES_EXTENSIONS:
        nom = morceaux[-3]
    else:
        nom = morceaux[-2] if len(morceaux) >= 2 else morceaux[0]
    return nom.upper() if len(nom) <= 3 else nom.capitalize()


def source_de(p, _profondeur=0):
    p = Path(p)
    etiquette = _etiquette_windows(p)
    hote = _domaine(etiquette.get("HostUrl"))
    reference = etiquette.get("ReferrerUrl", "")
    ref_domaine = _domaine(reference)
    if hote and not hote.endswith(CDN):
        return nom_du_site(hote)
    if ref_domaine:
        return nom_du_site(ref_domaine)
    if hote:
        return nom_du_site(hote)
    # fichier sorti d'une archive : on remonte à l'archive
    if reference and _profondeur < 3 and not ref_domaine and ":" in reference:
        archive = retrouver(reference)          # l'archive a peut-être déjà été rangée
        if archive.exists():
            return source_de(archive, _profondeur + 1)
    nom = p.name.lower()
    if nom.startswith(("capture d'écran", "capture d’écran", "screenshot", "capture d")):
        return "Captures d'écran"
    if nom.startswith("whatsapp"):
        return "WhatsApp"
    if re.match(r"(img|pxl|dsc|vid|mvimg)[_-]?\d", nom):
        return "Téléphone"
    if nom.startswith(("snapchat", "snap-")):
        return "Snapchat"
    return INCONNUE


def _nettoyer_nom(nom):
    return re.sub(r'[<>:"/\\|?*]', "-", nom).strip(" .") or INCONNUE


def mode():
    return "type" if str(CONFIG.get("mode", "theme")).lower() in ("type", "ancien") else "theme"


def racine():
    return _chemin(CONFIG.get("racine", RACINE_PAR_DEFAUT))


def _date(p):
    try:
        return datetime.datetime.fromtimestamp(Path(p).stat().st_mtime)
    except OSError:
        return datetime.datetime.now()


def extrait(p, limite=3500):
    """Le début du texte d'un PDF, d'un Word ou d'un fichier texte (pour classer « scan0042.pdf »). Vide si illisible."""
    p = Path(p)
    ext = p.suffix.lower()
    try:
        if not p.is_file() or p.stat().st_size > 40_000_000 or ext not in themes.EXT_LISIBLES:
            return ""
        if ext == ".pdf":
            from pypdf import PdfReader
            lecteur = PdfReader(str(p))
            if lecteur.is_encrypted:
                return ""
            texte = ""
            for page in lecteur.pages[:4]:
                texte += " " + (page.extract_text() or "")
                if len(texte) > limite:
                    break
            return " ".join(texte.split())[:limite]
        if ext == ".docx":
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            return " ".join(re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", " ")).split())[:limite]
        brut = p.read_bytes()[:limite * 3]
        if b"\x00" in brut[:2000]:
            return ""
        return " ".join(brut.decode("utf-8", "ignore").split())[:limite]
    except Exception:
        return ""


_cache_classes = {}


def classer(p, avec_contenu=True):
    """(résultat de themes.classer, source, extrait). Le contenu n'est lu que si le nom et la source ne suffisent pas.
    Mis en cache (un fichier déposé est classé pour l'affichage puis pour le rangement : on ne le relit pas deux fois)."""
    p = Path(p)
    try:
        st = p.stat()
        cle = (str(p), st.st_mtime_ns, st.st_size, avec_contenu)
    except OSError:
        cle = None
    if cle and cle in _cache_classes:
        return _cache_classes[cle]
    source = source_de(p)
    resultat = themes.classer(p, source)
    texte = ""
    if avec_contenu and resultat["confiance"] != "forte" and resultat["lisible"]:
        texte = extrait(p)
        if texte:
            resultat = themes.classer(p, source, texte)
    if cle:
        if len(_cache_classes) > 400:
            _cache_classes.clear()
        _cache_classes[cle] = (resultat, source, texte)
    return resultat, source, texte


def dossier_pour(p):
    """Où ce fichier doit aller : (dossier, type ou thème, source)."""
    p = Path(p)
    if mode() == "theme":
        resultat, source, _ = classer(p)
        return themes.dossier(racine(), resultat, _date(p)), themes.nom_affiche(resultat), source
    type_ = type_de(p)
    source = source_de(p)
    date = _date(p)
    modele = CONFIG.get("modele", "{source}")
    sous = modele.format(source=_nettoyer_nom(source), annee=date.year, mois=f"{date.year}-{date.month:02d}")
    racine = _chemin(_types()[type_]["dossier"])
    return racine.joinpath(*[_nettoyer_nom(m) for m in sous.replace("\\", "/").split("/") if m]), type_, source


NOMS_DOSSIERS = {"Documents": "Documents", "Pictures": "Images", "Videos": "Vidéos", "Music": "Musique",
                 "Downloads": "Téléchargements", "Desktop": "Bureau"}


def joli(chemin):
    """C:/Users/toi/Documents/Classement/PDF/Gmail -> Documents › Classement › PDF › Gmail"""
    chemin = Path(chemin)
    try:
        morceaux = list(chemin.relative_to(Path.home()).parts)
    except ValueError:
        return str(chemin)
    if morceaux:
        morceaux[0] = NOMS_DOSSIERS.get(morceaux[0], morceaux[0])
    return " › ".join(morceaux)


def court(dossier):
    """Juste l'essentiel : Études › Cours › 2026 (ou PDF › Gmail en mode « type »)."""
    dossier = Path(dossier)
    try:
        reste = dossier.relative_to(racine())
        return " › ".join([themes.NOMS_THEMES.get(reste.parts[0], reste.parts[0]), *reste.parts[1:]]) if reste.parts else "Dropi"
    except ValueError:
        pass
    for nom, regle in _types().items():
        try:
            reste = dossier.relative_to(_chemin(regle["dossier"]))
        except ValueError:
            continue
        return " › ".join([nom, *reste.parts])
    return " › ".join(joli(dossier).split(" › ")[-3:])


def court_pour(p):
    return court(dossier_pour(p)[0])


# ------------------------------------------------------------------ déplacer en notant tout

def place_libre(dossier, nom):
    """Chemin qui n'écrase rien : ajoute (1), (2)… si le nom est pris."""
    dossier.mkdir(parents=True, exist_ok=True)
    dest = dossier / nom
    base, ext = Path(nom).stem, Path(nom).suffix
    i = 1
    while dest.exists():
        dest = dossier / f"{base} ({i}){ext}"
        i += 1
    return dest


def _retirer_vides(dossier):
    """Après un déplacement : les dossiers devenus vides (2026, puis Cours…) disparaissent, sans quitter la racine."""
    dossier, base = Path(dossier), racine()
    while dossier != base and base in dossier.parents:
        try:
            dossier.rmdir()
        except OSError:
            return
        dossier = dossier.parent


def deplacer(src, dossier, nom=None, **infos):
    """Déplace src dans dossier (sans rien écraser) et note le trajet dans le journal."""
    src = Path(src)
    dest = place_libre(Path(dossier), nom or src.name)
    shutil.move(str(src), str(dest))
    noter(src, dest, **infos)
    _retirer_vides(src.parent)
    return dest


def ranger(p):
    """Range un fichier à sa place. Renvoie (nouveau chemin, type ou thème, source)."""
    p = Path(p)
    if mode() == "theme":
        resultat, source, texte = classer(p)
        dossier = themes.dossier(racine(), resultat, _date(p))
        etiquette = themes.nom_affiche(resultat)
        if p.parent == dossier:
            return p, etiquette, source
        dest = deplacer(p, dossier, raison=resultat["raison"])
        if (resultat["theme"], resultat["sous"]) == themes.A_TRIER and texte and ia_active():
            _file_ia.put((str(dest), texte))           # l'IA le regardera en tâche de fond
            _demarrer_ia()
        return dest, etiquette, source
    dossier, type_, source = dossier_pour(p)
    if p.parent == dossier:
        return p, type_, source
    return deplacer(p, dossier), type_, source


# ------------------------------------------------------------------ journal

def _lire():
    try:
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(journal):
    JOURNAL.write_text(json.dumps(journal[-5000:], ensure_ascii=False, indent=0), encoding="utf-8")


def noter(avant, apres, **infos):
    with _verrou:
        journal = _lire()
        journal.append({"date": datetime.datetime.now().isoformat(timespec="seconds"),
                        "avant": str(avant), "apres": str(apres), **infos})
        _ecrire(journal)


def retrouver(chemin):
    """Si un fichier a été déplacé par l'assistant, renvoie où il est maintenant."""
    p = _chemin(chemin)
    if p.exists():
        return p
    with _verrou:
        journal = _lire()
    courant, vus = str(p), set()
    while courant not in vus:
        vus.add(courant)
        suite = next((e["apres"] for e in reversed(journal) if e["avant"].lower() == courant.lower()), None)
        if not suite:
            break
        courant = suite
    if Path(courant).exists():
        return Path(courant)
    for e in reversed(journal):           # même nom, rangé ailleurs
        if Path(e["avant"]).name.lower() == p.name.lower() and Path(e["apres"]).exists():
            return Path(e["apres"])
    return p


def recherche_journal(nom, limite=10):
    nom = nom.lower().strip()
    with _verrou:
        journal = _lire()
    trouves, vus = [], set()
    for e in reversed(journal):
        apres = Path(e["apres"])
        if nom in apres.name.lower() and str(apres) not in vus:
            vus.add(str(apres))
            trouves.append((e, apres.exists()))
            if len(trouves) >= limite:
                break
    return trouves


def derniers(n=8):
    with _verrou:
        return _lire()[-n:]


def annuler_dernier():
    """Remet le dernier fichier déplacé à son ancienne place."""
    with _verrou:
        journal = _lire()
        for e in reversed(journal):
            if e.get("annule") or e.get("annulation"):
                continue
            apres, avant = Path(e["apres"]), Path(e["avant"])
            if not apres.exists() or not avant.parent.exists():
                continue
            dest = place_libre(avant.parent, avant.name)
            shutil.move(str(apres), str(dest))
            _retirer_vides(apres.parent)
            e["annule"] = True
            journal.append({"date": datetime.datetime.now().isoformat(timespec="seconds"),
                            "avant": str(apres), "apres": str(dest), "annulation": True})
            _ecrire(journal)
            return f"« {apres.name} » remis dans {joli(avant.parent)}."
    return "Rien à annuler."


def contexte(n=8):
    """Résumé pour l'IA des derniers rangements (pour qu'elle retrouve les fichiers)."""
    lignes = [f"- {Path(e['avant']).name} -> " + ("(mis à la corbeille)" if e["apres"] == "Corbeille" else e["apres"])
              for e in derniers(n)]
    return ("\n\nDerniers fichiers que tu as déplacés (ils sont maintenant à ces chemins) :\n" + "\n".join(lignes)) \
        if lignes else ""


# ------------------------------------------------------------------ l'IA classe en arrière-plan

_file_ia = queue.Queue()
_fil_ia = None


def ia_active():
    return CLASSIFIEUR is not None and CONFIG.get("ia", True) not in (False, "non", "false")


def _demarrer_ia():
    global _fil_ia
    if _fil_ia is None or not _fil_ia.is_alive():
        _fil_ia = threading.Thread(target=_boucle_ia, daemon=True)
        _fil_ia.start()


def _boucle_ia():
    """Un fichier à la fois, quand le moteur d'IA n'est pas occupé à répondre à quelqu'un."""
    while True:
        try:
            chemin, texte = _file_ia.get(timeout=120)
        except queue.Empty:
            return
        p = Path(chemin)
        if not p.exists() or CLASSIFIEUR is None:
            continue
        try:
            choix = CLASSIFIEUR(p.name, texte, themes.categories())
        except Exception:
            choix = None
        cible = themes.depuis_categorie(choix) if choix else None
        if not cible or cible == themes.A_TRIER:
            continue                                   # l'IA ne sait pas non plus : il reste dans « À trier »
        resultat = {"theme": cible[0], "sous": cible[1], "raison": "IA"}
        try:
            dest = deplacer(p, themes.dossier(racine(), resultat, _date(p)), raison="IA")
        except OSError:
            continue
        if SUR_RECLASSE:
            try:
                SUR_RECLASSE(dest.name, dest)
            except Exception:
                pass


# ------------------------------------------------------------------ réorganiser l'existant

def _fichiers_a_reorganiser(dossiers):
    for d in dossiers:
        racine_d = _chemin(d)
        if not racine_d.is_dir():
            continue
        for p in racine_d.rglob("*"):
            if p.is_file() and not est_partiel(p) and not str(p).startswith(str(racine())):
                yield p


def plan_reorganisation(dossiers=None):
    """Ce que ferait la réorganisation : [(fichier, dossier d'arrivée, étiquette)]. Ne déplace rien.
    Par défaut : l'ancien classement (« Classement » dans Documents, Images…), qu'on range dans les nouveaux thèmes."""
    plan = []
    for p in _fichiers_a_reorganiser(dossiers or ANCIENS_DOSSIERS):
        resultat, _, _ = classer(p)
        plan.append((p, themes.dossier(racine(), resultat, _date(p)), themes.nom_affiche(resultat)))
    return plan


def appliquer_plan(plan, sur_progres=None):
    """Déplace tout (sans rien écraser, avec le journal). Renvoie (déplacés, erreurs). Nettoie les dossiers vides."""
    faits, erreurs, dossiers = 0, [], set()
    for i, (p, dossier, _) in enumerate(plan):
        try:
            if Path(p).exists() and Path(p).parent != dossier:
                dossiers.add(Path(p).parent)
                deplacer(p, dossier, raison="réorganisation")
                faits += 1
        except OSError as ex:
            erreurs.append(f"{Path(p).name} : {ex}")
        if sur_progres and i % 20 == 0:
            sur_progres(i, len(plan))
    proteges = {Path.home(), *(Path.home() / n for n in ("Documents", "Pictures", "Videos", "Music", "Downloads", "Desktop"))}
    for d in sorted(dossiers, key=lambda x: len(x.parts), reverse=True):     # les dossiers devenus vides disparaissent
        while d not in proteges and d.parent != d:
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent
    return faits, erreurs


# ------------------------------------------------------------------ téléchargements

def dossier_telechargements():
    return _chemin((CONFIG.get("telechargements") or {}).get("dossier", "~/Downloads"))


def est_partiel(p):
    nom = p.name.lower()
    return nom.endswith(PARTIELS) or nom.startswith(("~$", ".")) or nom == "desktop.ini"
