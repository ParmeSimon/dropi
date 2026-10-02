"""Le rangement par thème de vie : chaque fichier va dans THÈME / SOUS-THÈME / ANNÉE.

    01 Études / Cours / 2026 / chapitre-3.pdf
    03 Administratif / Impôts / 2026 / avis-imposition.pdf
    05 Médias / Images / 2026 / photo.jpg

Comment Dropi choisit (sans IA, instantané) :
  1. des mots-clés dans le NOM du fichier (« facture-edf-mars.pdf » -> Logement et énergie) ;
  2. la SOURCE d'où il vient (Ameli -> Santé, Moodle -> Cours, Steam -> Jeux) ;
  3. des mots-clés dans le CONTENU des PDF, Word et textes (utile pour « scan0042.pdf ») ;
  4. à défaut, le type de fichier (images, vidéos, installateurs…).
Si c'est encore flou, le fichier va dans « À trier » et l'IA locale le classe en tâche de fond (voir classement.py).
"""
import re
import unicodedata
from pathlib import Path

# (dossier du thème, [sous-dossiers]) : l'ordre sert à l'affichage
ARBORESCENCE = [
    ("01 Études", ["Cours", "TP et projets", "Examens et notes", "Administratif école", "Lectures"]),
    ("02 Travail", ["Contrats et paie", "CV et candidatures", "Projets", "Présentations", "Réunions"]),
    ("03 Administratif", ["Impôts", "Santé", "Banque", "Assurances", "Logement et énergie", "Transports",
                          "Achats et factures", "Identité et démarches"]),
    ("04 Perso", ["Photos", "Captures d'écran", "Réseaux sociaux", "Voyages", "Divers"]),
    ("05 Médias", ["Images", "Vidéos", "Musique"]),
    ("06 Jeux", ["Mods et sauvegardes", "Captures de jeu"]),
    ("07 Logiciels", ["Installateurs", "Archives", "Code"]),
    ("99 À trier", [""]),
]
GLYPHES = {"01 Études": "document", "02 Travail": "tableau", "03 Administratif": "cadenas", "04 Perso": "oeil",
           "05 Médias": "video", "06 Jeux": "manette", "07 Logiciels": "code", "99 À trier": "horloge"}    # icône de chaque thème
A_TRIER = ("99 À trier", "")
SANS_ANNEE = {"99 À trier"}                       # pas de sous-dossier d'année pour ces thèmes
NOMS_THEMES = {d: d[3:] for d, _ in ARBORESCENCE}

# (thème, sous-thème, mots-clés du nom/contenu, sources). Une règle plus haut gagne à égalité.
REGLES = [
    ("03 Administratif", "Impôts", ["impot", "impots", "avis d imposition", "avis imposition", "imposition", "declaration de revenus", "dgfip", "taxe fonciere",
                                    "taxe d habitation", "prelevement a la source", "impots gouv", "revenu fiscal", "numero fiscal"], ["Impôts"]),
    ("03 Administratif", "Santé", ["ordonnance", "mutuelle", "feuille de soins", "attestation de droits", "remboursement", "ameli",
                                   "carte vitale", "compte rendu medical", "analyse", "radiographie", "doctolib", "medecin",
                                   "certificat medical", "securite sociale", "cpam", "vaccin", "pharmacie", "dentiste"], ["Ameli", "Doctolib"]),
    ("03 Administratif", "Banque", ["releve de compte", "releve bancaire", "rib", "iban", "virement", "pret immobilier", "credit",
                                    "banque", "carte bancaire", "bnp", "societe generale", "credit agricole", "boursorama", "revolut", "paypal"], []),
    ("03 Administratif", "Assurances", ["assurance", "attestation d assurance", "sinistre", "macif", "maif", "axa", "allianz", "matmut",
                                        "garantie decennale", "constat amiable"], []),
    ("03 Administratif", "Logement et énergie", ["quittance", "loyer", "bail", "edf", "engie", "electricite", "gaz", "etat des lieux",
                                                 "taxe d ordures", "syndic", "copropriete", "box internet", "orange", "sfr", "bouygues",
                                                 "free mobile", "facture eau", "caf", "apl"], ["EDF", "CAF"]),
    ("03 Administratif", "Transports", ["billet", "sncf", "train", "billet d avion", "boarding", "carte d embarquement", "navigo",
                                        "permis de conduire", "carte grise", "vignette", "certificat d immatriculation", "ouigo"], ["SNCF"]),
    ("03 Administratif", "Identité et démarches", ["carte d identite", "carte identite", "piece d identite", "piece identite", "passeport", "cni", "acte de naissance", "justificatif de domicile", "justificatif domicile",
                                                   "attestation sur l honneur", "attestation honneur", "cerfa", "france travail", "pole emploi", "service public",
                                                   "livret de famille", "titre de sejour", "casier judiciaire"], ["Service Public", "France Travail"]),
    ("03 Administratif", "Achats et factures", ["facture", "invoice", "recu", "commande", "bon de livraison", "garantie", "ticket de caisse",
                                                "bon de commande", "confirmation de commande", "retour colis"], ["Amazon", "Leboncoin", "Vinted"]),
    ("02 Travail", "Contrats et paie", ["contrat de travail", "fiche de paie", "bulletin de salaire", "bulletin de paie", "avenant",
                                        "rupture conventionnelle", "attestation employeur", "certificat de travail", "solde de tout compte",
                                        "cdi", "cdd", "alternance contrat"], []),
    ("02 Travail", "CV et candidatures", ["cv", "curriculum vitae", "lettre de motivation", "candidature", "portfolio", "offre d emploi",
                                          "entretien d embauche", "recommandation"], ["LinkedIn"]),
    ("02 Travail", "Réunions", ["compte rendu de reunion", "cr reunion", "ordre du jour", "reunion", "comite de pilotage", "copil", "seminaire", "equipe", "trimestre", "atelier", "team building", "point hebdo", "retrospective"], []),
    ("01 Études", "Examens et notes", ["releve de notes", "bulletin scolaire", "examen", "partiel", "sujet d examen", "diplome",
                                       "resultats", "annales", "controle", "correction", "attestation de reussite", "bac"], []),
    ("01 Études", "TP et projets", ["tp", "projet", "dossier de modelisation", "dossier projet", "rapport de stage", "memoire", "soutenance",
                                    "compte rendu de tp", "uml", "sae", "cahier des charges", "specification", "diagramme", "livrable",
                                    "rapport de projet", "dossier technique"], []),
    ("01 Études", "Cours", ["cours", "chapitre", "td", "cm", "support de cours", "lecon", "resume de cours", "fiche de revision",
                            "polycopie", "moodle", "slides", "notes de cours", "revision", "exercices", "corrige"], ["Moodle", "Pronote", "École Directe"]),
    ("01 Études", "Administratif école", ["inscription", "certificat de scolarite", "carte etudiante", "emploi du temps", "convention de stage",
                                          "reglement interieur", "bourse", "crous", "campus", "scolarite", "etudiant"], ["École Directe"]),
    ("01 Études", "Lectures", ["livre", "ebook", "epub", "article", "etat de l art", "bibliographie", "papier de recherche"], []),
    ("02 Travail", "Présentations", ["presentation", "pitch", "slides client", "soutenance entreprise", "deck", "powerpoint"], []),
    ("02 Travail", "Projets", ["devis", "proposition commerciale", "specifications fonctionnelles", "roadmap", "planning projet",
                               "backlog", "budget", "client", "livraison"], ["Notion"]),
    ("04 Perso", "Voyages", ["voyage", "vacances", "reservation hotel", "airbnb", "booking", "itineraire", "visa", "sejour"], []),
    ("07 Logiciels", "Code", ["readme", "source code", "code source", "script", "notebook"], ["GitHub"]),
    ("06 Jeux", "Mods et sauvegardes", ["mod", "modpack", "savegame", "sauvegarde de jeu", "texture pack", "resource pack"],
     ["Steam", "Epic Games", "CurseForge", "Nexus Mods"]),
]

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg", ".avif", ".tif", ".tiff"}
EXT_VIDEOS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v"}
EXT_MUSIQUE = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
EXT_INSTALL = {".exe", ".msi", ".msix", ".appx", ".dmg", ".apk"}
EXT_ARCHIVES = {".zip", ".rar", ".7z", ".tar", ".gz", ".iso"}
EXT_CODE = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".html", ".css", ".json", ".xml", ".sql", ".ipynb", ".sh", ".bat", ".yml", ".yaml"}
EXT_DOCUMENTS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls", ".xlsx", ".csv", ".ods", ".ppt", ".pptx", ".odp"}
EXT_LISIBLES = {".pdf", ".docx", ".txt", ".md", ".rtf", ".csv"}      # dont on peut lire le contenu pour mieux classer

SOURCES_RESEAUX = {"Instagram", "Facebook", "Snapchat", "TikTok", "X", "Pinterest", "Reddit", "Discord", "WhatsApp",
                   "Messenger", "Telegram", "YouTube"}
SEUIL_FORT = 3                                # score à partir duquel on est sûr de soi (un mot-clé dans le nom)
MAX_CONTENU = 3                               # points maximum qu'on accorde au contenu


def simple(texte):
    """Minuscules, sans accents, sans ponctuation : « Relevé_de-compte (2).PDF » -> « releve de compte 2 pdf »."""
    t = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _souche(mot):
    return mot[:-1] if len(mot) > 3 and mot.endswith("s") else mot


def _normaliser(texte):
    return " " + " ".join(_souche(m) for m in simple(texte).split()) + " "


_REGLES = [(theme, sous, [_normaliser(m) for m in mots], set(sources)) for theme, sous, mots, sources in REGLES]


INDICES = {   # pour les sous-thèmes sans règle de mots-clés : ce qu'on y range, en quelques mots
    "04 Perso/Photos": "photos personnelles, famille, amis", "04 Perso/Divers": "recettes, loisirs, papiers personnels divers",
    "05 Médias/Images": "images, fonds d'écran", "05 Médias/Vidéos": "vidéos", "05 Médias/Musique": "musique",
    "06 Jeux/Captures de jeu": "captures de jeux vidéo", "07 Logiciels/Installateurs": "programmes d'installation",
    "07 Logiciels/Archives": "archives zip", "04 Perso/Réseaux sociaux": "images et fichiers de réseaux sociaux",
    "04 Perso/Captures d'écran": "captures d'écran",
}


def legende():
    """Une ligne par catégorie (« 01 Études/Cours : cours, chapitre, td… ») : l'IA choisit mieux quand elle sait ce qu'on y met."""
    mots = {f"{t}/{s}": [m for m in motscles[:7]] for t, s, motscles, _ in REGLES}
    lignes = []
    for cat in categories():
        if cat == "99 À trier":
            lignes.append("- 99 À trier : texte illisible ou incohérent, ou aucune des catégories ci-dessus ne convient vraiment")
            continue
        indice = ", ".join(mots.get(cat, [])) or INDICES.get(cat, "")
        lignes.append(f"- {cat} : {indice}" if indice else f"- {cat}")
    return "\n".join(lignes)


def categories():
    """Toutes les destinations possibles (« 01 Études/Cours »), pour l'IA et pour l'affichage."""
    return [f"{d}/{s}" if s else d for d, sous in ARBORESCENCE for s in sous]


def _par_type(p, source):
    """Quand aucun mot-clé ne parle : le type de fichier décide, ou « À trier »."""
    ext = p.suffix.lower()
    if p.is_dir():
        return A_TRIER, "dossier"
    if ext in EXT_IMAGES:
        if source == "Captures d'écran":
            return ("04 Perso", "Captures d'écran"), "capture d'écran"
        if source in ("Steam", "Epic Games"):
            return ("06 Jeux", "Captures de jeu"), "capture de jeu"
        if source in ("Téléphone", "WhatsApp", "Snapchat"):
            return ("04 Perso", "Photos"), f"photo ({source})"
        if source in SOURCES_RESEAUX:
            return ("04 Perso", "Réseaux sociaux"), f"image ({source})"
        return ("05 Médias", "Images"), "image"
    if ext in EXT_VIDEOS:
        return ("05 Médias", "Vidéos"), "vidéo"
    if ext in EXT_MUSIQUE:
        return ("05 Médias", "Musique"), "musique"
    if ext in EXT_INSTALL:
        return ("07 Logiciels", "Installateurs"), "installateur"
    if ext in EXT_ARCHIVES:
        return ("07 Logiciels", "Archives"), "archive"
    if ext in EXT_CODE:
        return ("07 Logiciels", "Code"), "code"
    return A_TRIER, "inconnu"


def classer(chemin, source="", contenu=""):
    """Où va ce fichier ? {"theme", "sous", "score", "confiance", "raison", "lisible"}.

    confiance : "forte" (mot-clé dans le nom, ou nom + source/contenu), "moyenne", "faible" (devinette ou « À trier »).
    contenu : le début du texte du fichier, si on l'a déjà lu (sinon on classe sur le nom et la source).
    """
    p = Path(chemin)
    nom = _normaliser(p.stem)
    texte = _normaliser(contenu[:6000]) if contenu else ""
    scores = []
    for ordre, (theme, sous, mots, sources) in enumerate(_REGLES):
        dans_nom = [m for m in mots if m in nom]
        pts = min(6, 3 * len(dans_nom))
        raisons = [f"nom : {m.strip()}" for m in dans_nom[:2]]
        if source and source in sources:
            pts += 2
            raisons.append(f"source : {source}")
        if texte:
            dans_texte = [m for m in mots if m in texte and m not in dans_nom]
            gain = min(MAX_CONTENU, len(dans_texte))
            if gain:
                pts += gain
                raisons.append(f"contenu : {dans_texte[0].strip()}" + (f" +{gain - 1}" if gain > 1 else ""))
        if pts:
            scores.append((pts, -ordre, theme, sous, " ; ".join(raisons)))
    scores.sort(reverse=True)
    ext = p.suffix.lower()
    lisible = ext in EXT_LISIBLES and p.is_file()
    if scores:
        pts, _, theme, sous, raison = scores[0]
        ecart = pts - (scores[1][0] if len(scores) > 1 else 0)
        # un fichier média ne devient pas un « cours » à cause d'un mot dans son nom : seuls les documents suivent les mots-clés
        document = ext in EXT_DOCUMENTS or p.is_dir() or not ext
        if document or pts >= 5:
            # à égalité, la règle la plus haute (la plus précise : « edf » avant « facture ») l'emporte
            if pts >= SEUIL_FORT and ecart >= 1:
                return {"theme": theme, "sous": sous, "score": pts, "confiance": "forte", "raison": raison, "lisible": lisible}
            if pts >= 2:
                return {"theme": theme, "sous": sous, "score": pts, "confiance": "moyenne", "raison": raison, "lisible": lisible}
    (theme, sous), raison = _par_type(p, source)
    confiance = "faible" if (theme, sous) == A_TRIER else "moyenne"
    return {"theme": theme, "sous": sous, "score": 0, "confiance": confiance, "raison": raison, "lisible": lisible}


def dossier(racine, resultat, date):
    """racine/01 Études/Cours/2026 (« 99 À trier » sans année)."""
    chemin = Path(racine) / resultat["theme"]
    if resultat["sous"]:
        chemin = chemin / resultat["sous"]
    if resultat["theme"] not in SANS_ANNEE:
        chemin = chemin / str(date.year)
    return chemin


def nom_affiche(resultat):
    """« Études › Cours » pour l'interface."""
    theme = NOMS_THEMES.get(resultat["theme"], resultat["theme"])
    return f"{theme} › {resultat['sous']}" if resultat["sous"] else theme


def depuis_categorie(categorie):
    """« 01 Études/Cours » -> ("01 Études", "Cours"), ou None si ça n'existe pas."""
    theme, _, sous = categorie.strip().partition("/")
    for d, liste in ARBORESCENCE:
        if d == theme and sous in liste:
            return d, sous
    return None
