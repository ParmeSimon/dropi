"""La mémoire : l'assistant apprend de tes demandes et de ses recherches.

Ce n'est pas le modèle qui change (ça demanderait un entraînement très lourd) : l'assistant garde
des « souvenirs » — ce que tu lui apprends, tes préférences, tes corrections, ce qu'il a trouvé
sur internet — et relit les plus utiles avant chaque réponse. Il retient aussi tes habitudes
(jeux, applis, sites que tu lances). Plus tu t'en sers, plus ses réponses sont précises.

Tout reste sur ton PC : %APPDATA%\\AssistantIle\\memoire.json
"""
import re
import json
import math
import datetime
import threading
import unicodedata

import donnees

FICHIER = donnees.fichier("memoire.json")
MAX_SOUVENIRS = 600
_verrou = threading.Lock()

MOTS_VIDES = set("""le la les un une des du de d l au aux et ou en dans sur sous pour par avec sans ce cet cette ces
mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je tu il elle on nous vous ils elles me te se
moi toi lui y a est sont suis es etre avoir ai as avons avez ont fait faire qui que quoi quel quelle quels
quelles dont ne pas plus tres bien tout tous toute toutes comme mais donc car si alors aussi peux peut veux
veut c ca cest qu s n j m t the of and to is it""".split())

HABITUDES = {"lancer_jeu": "nom", "ouvrir_application": "nom", "ouvrir_site": "site",
             "ouvrir_stream_twitch": "streamer"}


def _lire():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        return {"souvenirs": d.get("souvenirs", []), "usages": d.get("usages", {})}
    except (OSError, ValueError):
        return {"souvenirs": [], "usages": {}}


def _ecrire(d):
    FICHIER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def mots(texte):
    """Les mots importants d'un texte, sans accents ni majuscules."""
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return [m for m in re.findall(r"[a-z0-9]+", texte) if len(m) > 2 and m not in MOTS_VIDES]


def retenir(texte, genre="fait"):
    """Ajoute un souvenir (ou rafraîchit un souvenir presque identique)."""
    texte = " ".join(str(texte).split())[:600]
    if not texte:
        return
    cle = set(mots(texte))
    with _verrou:
        d = _lire()
        for s in d["souvenirs"]:
            autre = set(mots(s["texte"]))
            if cle and autre and len(cle & autre) / len(cle | autre) >= 0.75:
                s.update(texte=texte, date=_maintenant())
                break
        else:
            d["souvenirs"].append({"texte": texte, "genre": genre, "date": _maintenant(), "utilise": 0})
        # on garde les souvenirs utiles et récents
        d["souvenirs"].sort(key=lambda s: (s.get("genre") == "preference", s.get("utilise", 0), s["date"]))
        d["souvenirs"] = d["souvenirs"][-MAX_SOUVENIRS:]
        _ecrire(d)


def _maintenant():
    return datetime.datetime.now().isoformat(timespec="seconds")


def pertinents(question, n=6):
    """Les souvenirs qui parlent de la même chose que la question."""
    q = set(mots(question))
    with _verrou:
        d = _lire()
        souvenirs = d["souvenirs"]
        if not q or not souvenirs:
            return [s for s in souvenirs if s.get("genre") == "preference"][-6:]
        freq = {}
        for s in souvenirs:
            for m in set(mots(s["texte"])):
                freq[m] = freq.get(m, 0) + 1
        notes = []
        for s in souvenirs:
            if s.get("genre") == "preference":
                continue
            communs = q & set(mots(s["texte"]))
            note = sum(math.log(1 + len(souvenirs) / freq[m]) for m in communs)
            if note > 0.6:
                notes.append((note, s))
        # ce qu'il sait de toi (préférences, ton PC…) sert toujours ; le reste seulement si ça parle du sujet
        choisis = [s for s in souvenirs if s.get("genre") == "preference"][-6:]
        choisis += [s for _, s in sorted(notes, key=lambda x: -x[0])[:n]]
        for s in choisis:
            s["utilise"] = s.get("utilise", 0) + 1
        if choisis:
            _ecrire(d)
        return choisis


def noter_usage(outil, args):
    """Compte ce que tu lances souvent (jeux, applis, sites) pour mieux te comprendre."""
    cle = HABITUDES.get(outil)
    if not cle or not args.get(cle):
        return
    etiquette = f"{outil}:{str(args[cle]).strip().lower()}"
    with _verrou:
        d = _lire()
        d["usages"][etiquette] = d["usages"].get(etiquette, 0) + 1
        _ecrire(d)


def habitudes(n=6):
    with _verrou:
        usages = _lire()["usages"]
    tri = sorted(usages.items(), key=lambda x: -x[1])[:n]
    noms = {"lancer_jeu": "jeu", "ouvrir_application": "appli", "ouvrir_site": "site",
            "ouvrir_stream_twitch": "stream"}
    return [f"{valeur} ({noms.get(outil, outil)}, {fois} fois)" for (etiquette, fois) in tri
            for outil, valeur in [etiquette.split(":", 1)] if fois >= 2]


def contexte(question):
    """Ce que l'IA doit savoir avant de répondre."""
    parties = []
    souvenirs = pertinents(question)
    moi = [s for s in souvenirs if s.get("genre") == "preference"]
    appris = [s for s in souvenirs if s.get("genre") != "preference"]
    if moi:
        parties.append("Ce que tu sais de l'utilisateur :\n" + "\n".join(f"- {s['texte']}" for s in moi))
    if appris:
        parties.append("Ce que tu as appris (tes souvenirs, fiables) :\n"
                       + "\n".join(f"- {s['texte']}" for s in appris))
    h = habitudes()
    if h:
        parties.append("Ce que l'utilisateur lance souvent : " + ", ".join(h) + ".")
    return ("\n\n" + "\n\n".join(parties)) if parties else ""


def tout():
    with _verrou:
        return _lire()


def oublier_tout():
    with _verrou:
        _ecrire({"souvenirs": [], "usages": {}})
