"""Le rangement méthodique : chaque fichier va dans TYPE / SOURCE.

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
import threading
from pathlib import Path
from urllib.parse import urlparse

import donnees

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


def dossier_pour(p):
    """Où ce fichier doit aller : (dossier, type, source)."""
    p = Path(p)
    type_ = type_de(p)
    source = source_de(p)
    try:
        date = datetime.datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        date = datetime.datetime.now()
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
    """Juste l'essentiel : PDF › Gmail"""
    dossier = Path(dossier)
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


def deplacer(src, dossier, nom=None):
    """Déplace src dans dossier (sans rien écraser) et note le trajet dans le journal."""
    src = Path(src)
    dest = place_libre(Path(dossier), nom or src.name)
    shutil.move(str(src), str(dest))
    noter(src, dest)
    return dest


def ranger(p):
    """Range un fichier à sa place méthodique. Renvoie (nouveau chemin, type, source)."""
    p = Path(p)
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


# ------------------------------------------------------------------ téléchargements

def dossier_telechargements():
    return _chemin((CONFIG.get("telechargements") or {}).get("dossier", "~/Downloads"))


def est_partiel(p):
    nom = p.name.lower()
    return nom.endswith(PARTIELS) or nom.startswith(("~$", ".")) or nom == "desktop.ini"
