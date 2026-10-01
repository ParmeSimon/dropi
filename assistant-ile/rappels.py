"""Rappels et minuteurs : « rappelle-moi dans 20 min d'appeler Paul », « minuteur 5 minutes ».

Ils sont gardés dans %APPDATA%\\AssistantIle\\rappels.json : un rappel survit à un redémarrage
(s'il est échu entre-temps, la goutte le donne au lancement).
"""
import re
import json
import time
import datetime

import donnees

FICHIER = donnees.fichier("rappels.json")

_MOTS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
         "neuf": 9, "dix": 10, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50}
_N = r"(?:\d+(?:[.,]\d+)?|" + "|".join(_MOTS) + r")"
_DUREE = (rf"(?:(?P<h>{_N})\s*(?:heures?|h)\s*(?P<hm>\d{{1,2}})?(?![a-zà-ÿ])"
          rf"|(?P<m>{_N})\s*(?:minutes?|min|mn)(?:\s*(?:et\s+)?(?P<ms>\d{{1,2}})(?:\s*(?:secondes?|sec|s))?)?(?![a-zà-ÿ])"
          rf"|(?P<s>{_N})\s*(?:secondes?|sec|s)(?![a-zà-ÿ])"
          r"|(?P<demi>une?\s+demi[- ]heure)|(?P<quart>un\s+quart\s+d['’]heure))")
_DANS = re.compile(r"\b(?:dans|d['’]ici)\s+" + _DUREE, re.I)
_HEURE = re.compile(r"(?:\b(?:à|a|pour|vers)\s+)(?:(?P<hh>\d{1,2})\s*(?:heures?|h|:)\s*(?P<mm>\d{2})?(?![a-zà-ÿ\d])"
                    r"|(?P<midi>midi)|(?P<minuit>minuit))", re.I)
_HEURE_NUE = re.compile(r"(?:(?P<hh>\d{1,2})\s*(?:heures?|h|:)\s*(?P<mm>\d{2})?(?![a-zà-ÿ\d])"
                        r"|(?P<midi>midi)|(?P<minuit>minuit))", re.I)
_MINUTEUR = re.compile(r"\b(?:minuteur|minuterie|timer|chrono(?:m[eè]tre)?|compte\s+[àa]\s+rebours)\b", re.I)
_RAPPEL = re.compile(r"\b(?:rappelle|rappelles|rappel|fais[- ]moi\s+penser|pr[ée]viens|r[ée]veille)(?:[- ]moi)?\b", re.I)
_DEMAIN = re.compile(r"\bdemain\b", re.I)


def _valeur(mot):
    mot = mot.lower()
    return _MOTS[mot] if mot in _MOTS else float(mot.replace(",", "."))


def _secondes(m):
    """La durée (en secondes) d'une correspondance de _DUREE."""
    if m.group("demi"):
        return 1800
    if m.group("quart"):
        return 900
    if m.group("h"):
        return _valeur(m.group("h")) * 3600 + int(m.group("hm") or 0) * 60
    if m.group("m"):
        return _valeur(m.group("m")) * 60 + int(m.group("ms") or 0)
    return _valeur(m.group("s"))


def duree_lisible(secondes):
    secondes = int(round(secondes))
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    if h:
        return f"{h} h {m:02d}" if m else f"{h} h"
    if m:
        return f"{m} min {s:02d}" if s else f"{m} min"
    return f"{s} s"


def _moment(texte, maintenant, strict=True):
    """(date et heure visées, morceau de texte qui le disait) ou None. strict : il faut « dans … » ou « à … »."""
    m = _DANS.search(texte)
    if m:
        return maintenant + datetime.timedelta(seconds=_secondes(m)), m.group(0)
    m = _HEURE.search(texte) or (None if strict else _HEURE_NUE.search(texte))
    if not m:                    # sans « dans » ni « à » : « 15h30 » est une heure, « 20 minutes » une durée
        m = None if strict else re.search(_DUREE, texte, re.I)
        return (maintenant + datetime.timedelta(seconds=_secondes(m)), m.group(0)) if m else None
    heure = 12 if m.group("midi") else 0 if m.group("minuit") else int(m.group("hh"))
    minute = int(m.group("mm") or 0) if m.group("hh") else 0
    if heure > 23 or minute > 59:
        return None
    quand = maintenant.replace(hour=heure, minute=minute, second=0, microsecond=0)
    if _DEMAIN.search(texte) or quand <= maintenant:
        quand += datetime.timedelta(days=1)
    return quand, m.group(0)


def analyser(texte, maintenant=None):
    """Comprend une demande de rappel ou de minuteur : {"genre", "quand", "texte"} ou None."""
    maintenant = maintenant or datetime.datetime.now()
    if _MINUTEUR.search(texte):
        m = re.search(_DUREE, texte, re.I)
        if not m:
            return None
        return {"genre": "minuteur", "quand": maintenant + datetime.timedelta(seconds=_secondes(m)),
                "texte": f"Minuteur de {duree_lisible(_secondes(m))}"}
    declencheur = _RAPPEL.search(texte)
    moment = declencheur and _moment(texte, maintenant)
    if not moment:
        return None
    quand, morceau = moment
    sujet = texte.replace(declencheur.group(0), " ").replace(morceau, " ")
    sujet = _DEMAIN.sub(" ", sujet)
    sujet = re.sub(r"^[\s,:;.!-]*(?:de\s+|d['’]|que\s+|qu['’]|pour\s+|à\s+)?", "", " ".join(sujet.split()), flags=re.I)
    sujet = sujet.strip(" ,:;.!-")
    return {"genre": "rappel", "quand": quand, "texte": sujet[:1].upper() + sujet[1:] if sujet else "Rappel"}


def quand_lisible(quand, maintenant=None):
    maintenant = maintenant or datetime.datetime.now()
    heure = quand.strftime("%Hh%M")
    if quand.date() == maintenant.date():
        return f"à {heure}"
    if quand.date() == (maintenant + datetime.timedelta(days=1)).date():
        return f"demain à {heure}"
    return quand.strftime("le %d/%m à ") + heure


# ------------------------------------------------------------------ Le carnet

def _lire():
    try:
        liste = json.loads(FICHIER.read_text(encoding="utf-8"))
        return liste if isinstance(liste, list) else []
    except (OSError, ValueError):
        return []


def _ecrire(liste):
    FICHIER.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")


def ajouter(quand, texte, genre="rappel"):
    fiche = {"id": int(time.time() * 1000), "quand": quand.timestamp(), "texte": texte, "genre": genre}
    _ecrire(_lire() + [fiche])
    return fiche


def a_venir():
    return sorted(_lire(), key=lambda f: f["quand"])


def echus(maintenant=None):
    """Les rappels dont l'heure est passée : rendus une seule fois (ils quittent le carnet)."""
    maintenant = maintenant or time.time()
    liste = _lire()
    sonnes = [f for f in liste if f["quand"] <= maintenant]
    if sonnes:
        _ecrire([f for f in liste if f["quand"] > maintenant])
    return sorted(sonnes, key=lambda f: f["quand"])


def supprimer(genre=None):
    """Enlève tout (ou seulement les minuteurs / les rappels). Renvoie combien."""
    liste = _lire()
    gardes = [f for f in liste if genre and f["genre"] != genre]
    _ecrire(gardes)
    return len(liste) - len(gardes)


# ------------------------------------------------------------------ Pour l'IA et les ordres directs

def creer(quand, texte=""):
    """« dans 20 minutes », « 15h30 », « demain 9h » + ce qu'il faut rappeler."""
    maintenant = datetime.datetime.now()
    moment = _moment(str(quand), maintenant, strict=False)
    if not moment:
        return f"Erreur : je n'ai pas compris le moment « {quand} » (ex : dans 20 minutes, 15h30, demain 9h)."
    fiche = ajouter(moment[0], str(texte).strip() or "Rappel")
    return f"Rappel {quand_lisible(moment[0], maintenant)} : {fiche['texte']}"


def lister():
    fiches = a_venir()
    if not fiches:
        return "Aucun rappel ni minuteur en cours."
    maintenant = datetime.datetime.now()
    lignes = []
    for f in fiches:
        quand = datetime.datetime.fromtimestamp(f["quand"])
        if f["genre"] == "minuteur":
            lignes.append(f"- {f['texte']} : encore {duree_lisible(max(0, f['quand'] - time.time()))}")
        else:
            lignes.append(f"- {quand_lisible(quand, maintenant)} : {f['texte']}")
    return "En cours :\n" + "\n".join(lignes)
