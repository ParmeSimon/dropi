"""Les ordres directs : une demande simple (« ouvre Excel », « volume à 30 », « minuteur 5 min »)
est reconnue ici et exécutée tout de suite, sans passer par l'IA.

L'IA ne sert plus qu'aux vraies questions et aux demandes compliquées. En cas de doute
(deux ordres dans la phrase, nom d'application inconnu…), reconnaitre() renvoie None et l'IA s'en occupe.
"""
import re
import unicodedata

import tools
import rappels


def simplifier(texte):
    """Minuscules, sans accents ni politesse : « Peux-tu ouvrir Excel, s'il te plaît ? » → « ouvrir excel »."""
    t = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"-(moi|toi|tu|il|elle|on|je|ce|le|la|les|nous|vous)\b", r" \1", t)
    t = re.sub(r"[\s.!?…]+$", "", t).strip()
    t = re.sub(r"^(?:s'il te plait|stp|dis(?: moi)?|hey|ok|bon|alors|plop)[, ]+", "", t)
    t = re.sub(r"[, ]+(?:s'il te plait|stp|merci)$", "", t)
    t = re.sub(r"^(?:(?:est ce que )?tu peux|peux tu|pourrais tu|tu pourrais|je veux que tu|j'aimerais que tu)\s+", "", t)
    return " ".join(t.split())


def _outil(fonction, /, **args):
    return ("outil", fonction, args)


def _regler(reglage, valeur=""):
    return _outil("regler_pc", reglage=reglage, valeur=valeur)


_POURCENT = r"(\d{1,3})(?: ?%| pour ?cent)?"

# (motif à faire correspondre à toute la phrase simplifiée, ce qu'il faut faire ; m = la correspondance)
MOTIFS = [
    # ---- musique
    (r"(?:mets? (?:en |sur )?pause|pause|(?:stop|stoppe|arrete|coupe) la musique)", lambda m: _outil("controler_musique", action="pause")),
    (r"(?:play|lecture|reprends?(?: la musique)?|(?:remets?|relance) la musique)", lambda m: _outil("controler_musique", action="lecture")),
    (r"(?:(?:musique|chanson|morceau|titre|piste) suivante?|suivante?|next|passe (?:la|cette|ce|le) (?:musique|chanson|morceau|titre))",
     lambda m: _outil("controler_musique", action="suivant")),
    (r"(?:(?:musique|chanson|morceau|titre|piste) precedente?|precedente?|(?:musique|chanson|morceau|titre) d'avant)",
     lambda m: _outil("controler_musique", action="precedent")),
    (r"(?:c'est quoi|quelle est|quel est|quelle|quel) (?:cette |la |ce |le )?(?:musique|chanson|morceau|titre)(?: en cours| qui passe| qui joue)?"
     r"|qu'est ce qui (?:joue|passe)|qu'est ce que j'ecoute", lambda m: _outil("musique_en_cours")),
    # ---- heure
    (r"(?:il est )?quelle heure(?: il est| est il)?|l'heure|on est quel jour|quel jour (?:on est|sommes nous)"
     r"|(?:c'est quoi |quelle est )?la date|quelle date", lambda m: _outil("date_heure")),
    # ---- volume
    (rf"(?:mets? |regle |monte |baisse )?(?:le )?(?:volume|son) (?:a|sur) {_POURCENT}", lambda m: _regler("volume", m.group(1))),
    (r"(?:monte|augmente|pousse) (?:un peu )?(?:le )?(?:son|volume)|plus fort", lambda m: _regler("volume", "+10")),
    (r"(?:baisse|diminue) (?:un peu )?(?:le )?(?:son|volume)|moins fort", lambda m: _regler("volume", "-10")),
    (r"(?:coupe|eteins) (?:le )?(?:son|volume)|muet|mute|silence", lambda m: _regler("volume", "muet")),
    (r"(?:remets?|reactive|rallume|retablis) (?:le )?(?:son|volume)|unmute", lambda m: _regler("volume", "son")),
    (r"(?:(?:quel est|c'est quoi) le )?volume|le (?:volume|son) est a combien", lambda m: _regler("volume")),
    # ---- luminosité
    (rf"(?:mets? |regle )?(?:la )?luminosite (?:a|sur) {_POURCENT}", lambda m: _regler("luminosite", m.group(1))),
    (r"(?:monte|augmente) (?:un peu )?la luminosite|plus lumineux|eclaircis l'ecran", lambda m: _regler("luminosite", "+10")),
    (r"(?:baisse|diminue) (?:un peu )?la luminosite|moins lumineux|assombris l'ecran", lambda m: _regler("luminosite", "-10")),
    (r"(?:(?:quelle est|c'est quoi) la )?luminosite", lambda m: _regler("luminosite")),
    # ---- écran et session
    (r"(?:verrouille|verrouiller|lock)(?: (?:le pc|mon pc|l'ordi|l'ordinateur|l'ecran|la session|ma session))?", lambda m: _regler("verrouiller")),
    (r"etein[sd]s? (?:l'ecran|mon ecran|les ecrans)", lambda m: _regler("ecran")),
    (r"(?:ouvre|affiche|montre(?: moi)?|va dans) (?:les |le |la )?(?:reglages?|parametres?)(?: (?:du |de la |de l'|des |de |d'))?(.*)",
     lambda m: _regler("parametres", m.group(1).strip() or "parametres")),
    (r"(?:active|desactive|coupe|allume|eteins|mets?) (?:le |la )?(wi ?fi|wi-fi|bluetooth)", lambda m: _regler("parametres", m.group(1))),
    # ---- rangement
    (r"range (?:mes |les |le dossier )?telechargements", lambda m: ("ile", "_ranger_telechargements")),
    (r"range (?:mon |le )?bureau", lambda m: _outil("ranger_dossier", dossier="~/Desktop")),
    (r"annule(?: (?:ca|le rangement|le dernier rangement))?", lambda m: _outil("annuler_rangement")),
    (r"(?:re)?(?:organise|classe)(?: moi)? (?:tout )?(?:mon|mes|le|les) (?:ancien )?(?:classement|dossiers|fichiers|documents)(?: par theme)?|range(?: moi)? (?:mon|le) classement"
     r"|(?:re)?organise tout|nouveau classement|passe(?: mon classement)? en theme"
     r"|range(?: moi)? (?:tout|mon pc|mon ordi|mon ordinateur|tout mon pc|ce qui traine)|fais le rangement|range tout ce qui traine", lambda m: ("ile", "_reorganiser")),
    (r"fais(?: moi)? de la place|libere de la place|nettoie (?:mon |le )?(?:disque|pc)", lambda m: ("ile", "_faire_de_la_place")),
    # ---- tableau de bord (Dropi en plein écran)
    (r"(?:ouvre|affiche|montre(?: moi)?|lance|mets?|passe en|va sur)? ?(?:le |mon |en |au )?(?:tableau de bord|dashboard|plein ecran|mode bureau|grand ecran)"
     r"|agrandis(?: toi)?|mets? toi en grand", lambda m: ("ile", "_ouvrir_tableau")),
    (r"(?:ferme|reduis|quitte|enleve)(?: le| la)? (?:tableau de bord|dashboard|plein ecran)|mode goutte|redeviens une goutte|reduis toi",
     lambda m: ("ile", "_fermer_tableau")),
    # ---- jouer avec Dropi (les mini-jeux)
    (r"(?:on )?(?:joue|jouons|jouer)(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:morpion|tic tac toe|tictactoe|croix et ronds)(?: avec moi| ensemble| contre moi)?"
     r"|(?:une )?partie de (?:morpion|tic tac toe)|morpion", lambda m: ("ile", "_jeu_morpion")),
    (r"(?:on )?(?:joue|jouons|jouer)(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:pierre ?(?:feuille)? ?(?:ciseaux?)?|chifoumi|shifumi|pfc)(?: avec moi| ensemble| contre moi)?"
     r"|(?:une )?partie de (?:pierre ?feuille ?ciseaux?|chifoumi|shifumi)|pierre feuille ciseaux?|chifoumi|shifumi", lambda m: ("ile", "_jeu_pfc")),
    (r"(?:on )?(?:joue|jouons|jouer)?(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:puissance ?4|puissance quatre|connect ?4|p4)(?: avec moi| ensemble| contre moi)?"
     r"|(?:une )?partie de (?:puissance ?4|connect ?4)", lambda m: ("ile", "_jeu_p4")),
    (r"(?:on )?(?:joue|jouons|jouer)?(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:memoire|memory|jeu de memoire|jeu de paires|paires)(?: avec moi| ensemble| contre moi)?"
     r"|(?:une )?partie de (?:memoire|memory)", lambda m: ("ile", "_jeu_memoire")),
    (r"(?:on )?(?:joue|jouons|jouer)?(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:devine(?: le)? nombre|plus ou moins|juste prix|nombre mystere)(?: avec moi| ensemble| contre moi)?",
     lambda m: ("ile", "_jeu_nombre")),
    (r"(?:on )?(?:joue|jouons|jouer)(?: (?:au|a la|aux|a|un|une|le|la))? ?(?:reflexes?|reactivite|duel de reflexes?)(?: avec moi| ensemble| contre moi)?"
     r"|(?:un )?duel de reflexes?|test de reflexes?", lambda m: ("ile", "_jeu_reflexe")),
    # s'ennuyer, vouloir jouer, demander un jeu : on ouvre les mini-jeux (sans passer par l'IA)
    (r"(?:.*\b)?(?:m ?'?ennui\w*|ennui\w*|j ?'?ai rien a faire|rien a faire|(?:occupe|divertis|distrais|amuse)(?: |-)?(?:moi)?"
     r"|je veux (?:m ?'?amuser|jouer|un jeu)|j ?'?ai envie de jouer|envie de jouer|je veux faire un jeu)(?:\b.*)?", lambda m: ("ile", "_jeux")),
    (r"(?:on |tu veux |veux tu |tu veut |tu sais |sais tu )?(?:joue|jouons|jouer)(?: un peu| ensemble| avec moi| avec toi| contre moi| une partie| a un jeu| a quelque chose)*"
     r"|(?:lance|ouvre|fais|propose|montre)(?: moi)? (?:un |une |les |des |tes )?(?:petits? )?(?:mini ?jeux?|jeux?|partie|duel)"
     r"|(?:t'as|tu as|as tu|y a t il|il y a) (?:un |des )?(?:petits? )?(?:jeux?|mini ?jeux?)(?: a me proposer| pour moi| ici)?"
     r"|(?:un |une |des )?(?:petits? )?(?:mini ?jeux?|jeux?|partie|defi)(?: avec toi| contre toi)?|defie(?: moi)?|je te defie|joue avec moi", lambda m: ("ile", "_jeux")),
    # ---- jeux installés
    (r"(?:(?:montre(?: moi)?|affiche|liste) )?(?:mes|les) jeux|quels jeux (?:j'ai|ai je|sont installes)", lambda m: ("ile", "_mes_jeux")),
    # ---- capture de texte à l'écran
    (r"(?:capture|lis|copie|recupere|extrais)(?: moi)? (?:le |du |un )?texte (?:de |a |sur )?l'ecran"
     r"|capture(?: d'ecran)?(?: (?:de |du )?texte)?|lis(?: moi)? l'ecran|ocr", lambda m: ("ile", "_capturer_texte")),
    # ---- rappels
    (r"(?:annule|arrete|stoppe|supprime|enleve) (?:le |les |mon |mes |tous les |tous mes )?(?:minuteurs?|minuterie|timers?|chrono)",
     lambda m: _outil("supprimer_rappels", genre="minuteur")),
    (r"(?:annule|supprime|enleve|oublie) (?:les |mes |tous les |tous mes )rappels", lambda m: _outil("supprimer_rappels", genre="rappel")),
    (r"(?:(?:quels sont|liste|montre(?: moi)?|affiche|c'est quoi) )?(?:mes|les) (?:rappels|minuteurs)"
     r"|(?:il reste )?combien de temps(?: il reste)?(?: (?:au|sur le) minuteur)?", lambda m: _outil("lister_rappels")),
    # ---- messagerie
    (r"(?:connecte|configure|branche|ajoute|change)r? (?:mes mails|ma messagerie|ma boite mail|mon mail|mon adresse mail)",
     lambda m: ("ile", "_ouvrir_mail")),
    (r"(?:(?:montre(?: moi)?|affiche|lis(?: moi)?) )?(?:mes |les )?(?:(\d{1,2}) )?(?:derniers |nouveaux )?(?:mails|messages|courriels)"
     r" (?:importants|qui comptent|non lus|urgents)|j'ai (?:des|quoi comme) (?:mails|messages) importants",
     lambda m: _outil("mails_recents", nombre=int(m.group(1) or 8), importants=True)),
    (r"(?:(?:montre(?: moi)?|affiche|lis(?: moi)?) )?mes (?:(\d{1,2}) )?(?:derniers |nouveaux )?(?:mails|messages|courriels)",
     lambda m: _outil("mails_recents", nombre=int(m.group(1) or 5))),
    # ---- recherche
    (r"(?:cherche|recherche|google) (.+) sur (?:google|internet|le web)", lambda m: _outil("recherche_web", requete=m.group(1))),
    (r"google (.+)", lambda m: _outil("recherche_web", requete=m.group(1))),
]
MOTIFS = [(re.compile(motif), action) for motif, action in MOTIFS]

_OUVRIR = re.compile(r"(?:ouvre|ouvrir|lance|lancer|demarre|demarrer|va sur)(?: moi)? (?:le |la |l'|les |mon |ma |mes )?(.+)")
_STREAM = re.compile(r"(?:stream|live|chaine)(?: twitch)? (?:de |d')?(.+)|(.+) sur twitch")
_ADRESSE = re.compile(r"[\w-]+(?:\.[\w-]+)+(?:/\S*)?")


# Sites qu'on ouvre sans rien demander à personne (tes favoris de config.yaml passent avant).
SITES_CONNUS = {
    "github": "github.com", "gitlab": "gitlab.com", "chatgpt": "chatgpt.com", "claude": "claude.ai",
    "gemini": "gemini.google.com", "copilot": "copilot.microsoft.com", "notion": "notion.so",
    "linkedin": "linkedin.com", "twitter": "x.com", "x": "x.com", "facebook": "facebook.com",
    "instagram": "instagram.com", "reddit": "reddit.com", "amazon": "amazon.fr", "wikipedia": "fr.wikipedia.org",
    "twitch": "twitch.tv", "google": "google.com", "maps": "maps.google.com", "google maps": "maps.google.com",
    "drive": "drive.google.com", "google drive": "drive.google.com", "agenda": "calendar.google.com",
    "outlook": "outlook.live.com", "whatsapp web": "web.whatsapp.com", "stackoverflow": "stackoverflow.com",
    "stack overflow": "stackoverflow.com", "leboncoin": "leboncoin.fr", "vinted": "vinted.fr", "deepl": "deepl.com",
    "traducteur": "translate.google.com", "disney+": "disneyplus.com", "disney plus": "disneyplus.com",
    "prime video": "primevideo.com", "canva": "canva.com", "figma": "figma.com", "tiktok": "tiktok.com",
    "pinterest": "pinterest.com", "ebay": "ebay.fr", "paypal": "paypal.com", "dropbox": "dropbox.com",
    "onedrive": "onedrive.live.com", "docs": "docs.google.com", "google docs": "docs.google.com",
    "sheets": "sheets.google.com", "meteo": "meteofrance.com", "le monde": "lemonde.fr", "lemonde": "lemonde.fr",
    "youtube music": "music.youtube.com", "crunchyroll": "crunchyroll.com", "steam web": "store.steampowered.com",
}
DOSSIERS = {
    "telechargements": "~/Downloads", "downloads": "~/Downloads", "documents": "~/Documents", "bureau": "~/Desktop",
    "images": "~/Pictures", "photos": "~/Pictures", "videos": "~/Videos", "musique": "~/Music",
    "corbeille": "shell:RecycleBinFolder",
}


def _domaine_existe(nom):
    """« ouvre fnac » : fnac.com existe-t-il ? Réponse en moins de 1,5 s, sinon on laisse tomber."""
    import socket
    import threading
    trouve = []

    def chercher():
        for fin in (".com", ".fr"):
            try:
                socket.gethostbyname(nom + fin)
                trouve.append(nom + fin)
                return
            except OSError:
                pass

    fil = threading.Thread(target=chercher, daemon=True)
    fil.start()
    fil.join(1.5)
    return trouve[0] if trouve else None


def _ouvrir(quoi):
    """« ouvre X » : un stream, un site, un dossier, une application ou un jeu. Une demande aussi simple ne doit
    jamais attendre l'IA : si on ne trouve rien, on répond tout de suite que c'est introuvable."""
    quoi = re.sub(r"^(?:(?:le |la |l'|les |mon |ma |mes |un |une )?(?:site|dossier)s? )?(?:(?:de la|du|de l'|des|de|d')\s*)?"
                  r"(?:le |la |l'|les |mon |ma |mes )?", "", quoi).strip() or quoi
    stream = _STREAM.fullmatch(quoi)
    if stream:
        return _outil("ouvrir_stream_twitch", streamer=(stream.group(1) or stream.group(2)).strip())
    if quoi in {s.lower() for s in tools.CONFIG.get("sites", {})} or _ADRESSE.fullmatch(quoi):
        return _outil("ouvrir_site", site=quoi)
    if quoi in {s.lower() for s in tools.CONFIG.get("streamers", {})}:
        return _outil("ouvrir_stream_twitch", streamer=quoi)
    if len(quoi) < 2 or len(quoi.split()) > 4:
        return None
    if quoi in DOSSIERS:
        return _outil("ouvrir_fichier", chemin=DOSSIERS[quoi])
    appli = tools.trouver_application(quoi) if len(quoi) >= 3 else None
    if appli:
        return _outil("ouvrir_application", nom=appli)
    jeu = tools.trouver_jeu(quoi, seuil=0.85)
    if jeu:
        return _outil("lancer_jeu", nom=jeu["nom"])
    if quoi in SITES_CONNUS:
        return _outil("ouvrir_site", site=SITES_CONNUS[quoi])
    if quoi in {a.lower() for a in tools.CONFIG.get("jeux", {})}:
        return _outil("lancer_jeu", nom=quoi)            # réglé dans config.yaml mais pas installé ici : on le dit
    if any(quoi == connue.lower() for connues in tools.USAGES.values() for connue in connues):
        return _outil("ouvrir_application", nom=quoi)
    mot = quoi.replace(" ", "")
    if re.fullmatch(r"[a-z0-9-]{3,}", mot):
        domaine = _domaine_existe(mot)
        if domaine:
            return _outil("ouvrir_site", site=domaine)
    return _outil("ouvrir_application", nom=quoi)         # cherche large dans Windows, sinon « introuvable » + suggestions


def reconnaitre(texte):
    """("outil", nom, arguments), ("ile", méthode), ("rappel", fiche) ou None si ce n'est pas un ordre simple."""
    t = simplifier(texte)
    if not t or len(t) > 140:
        return None
    fiche = rappels.analyser(texte)
    if fiche:
        return ("rappel", fiche)
    if re.search(r"[,;]| (?:et|puis|ensuite|apres) ", t):
        return None                      # plusieurs choses demandées à la fois : c'est pour l'IA
    for motif, action in MOTIFS:
        m = motif.fullmatch(t)
        if m:
            return action(m)
    m = _OUVRIR.fullmatch(t)
    return _ouvrir(m.group(1).strip()) if m else None
