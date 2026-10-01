"""La messagerie : connecter sa boîte mail (Orange, Gmail, Free… n'importe laquelle en IMAP) et lire les derniers messages.

L'adresse et le serveur sont gardés dans %APPDATA%\\AssistantIle\\messagerie.json ; le mot de passe, lui,
va dans le coffre de Windows (coffre.py), jamais dans un fichier. La lecture est en lecture seule :
rien n'est marqué comme lu, rien n'est supprimé.
"""
import re
import json
import email
import socket
import imaplib
import urllib.request
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, parseaddr

import coffre
import donnees

FICHIER = donnees.fichier("messagerie.json")
COFFRE = "@messagerie"            # sous ce nom dans le coffre (ce n'est pas un site : le guetteur ne le propose jamais)
ANCIENNE = {}                     # l'ancienne section « email » de config.yaml, encore acceptée (voir tools.init)

_APPLI = "demande un <b>mot de passe d'application</b>, pas ton mot de passe habituel"
_GMAIL = (f"Gmail {_APPLI}. Active la validation en 2 étapes, puis crée-le sur "
          "<a href='https://myaccount.google.com/apppasswords'>myaccount.google.com/apppasswords</a> (16 lettres).")
_YAHOO = (f"Yahoo {_APPLI} : Compte › Sécurité › "
          "<a href='https://login.yahoo.com/account/security'>Générer un mot de passe d'application</a>.")
_ICLOUD = (f"iCloud {_APPLI} : <a href='https://account.apple.com'>account.apple.com</a> › "
           "Connexion et sécurité › Mots de passe pour applications.")
_ORANGE = ("Ton mot de passe Orange habituel. Si la connexion est refusée, autorise les applications de messagerie "
           "dans ton espace client Orange (Mail › Paramètres › Accès depuis d'autres applications).")
_MICROSOFT = ("Microsoft n'accepte plus la connexion par mot de passe pour Outlook, Hotmail et Live (depuis fin 2024) : "
              "ces boîtes ne peuvent pas être connectées ici pour l'instant.")
_PROTON = "Proton Mail ne s'ouvre qu'avec son application « Proton Mail Bridge » (offre payante) lancée sur ce PC."
_SIMPLE = "Ton mot de passe habituel de messagerie."

# domaine de l'adresse -> (serveur IMAP, aide affichée, connexion possible ?)
FOURNISSEURS = {}
for _domaines, _fiche in (
        (("gmail.com", "googlemail.com"), ("imap.gmail.com", _GMAIL, True)),
        (("orange.fr", "wanadoo.fr"), ("imap.orange.fr", _ORANGE, True)),
        (("free.fr",), ("imap.free.fr", _SIMPLE, True)),
        (("sfr.fr", "neuf.fr", "club-internet.fr"), ("imap.sfr.fr", _SIMPLE, True)),
        (("laposte.net",), ("imap.laposte.net", _SIMPLE, True)),
        (("bbox.fr",), ("imap4.bbox.fr", _SIMPLE, True)),
        (("yahoo.fr", "yahoo.com", "ymail.com"), ("imap.mail.yahoo.com", _YAHOO, True)),
        (("icloud.com", "me.com", "mac.com"), ("imap.mail.me.com", _ICLOUD, True)),
        (("gmx.fr", "gmx.com", "gmx.net"), ("imap.gmx.com", _SIMPLE + " (IMAP doit être activé dans les réglages GMX.)", True)),
        (("aol.com",), ("imap.aol.com", f"AOL {_APPLI}.", True)),
        (("outlook.com", "outlook.fr", "hotmail.com", "hotmail.fr", "live.com", "live.fr", "msn.com"),
         ("outlook.office365.com", _MICROSOFT, False)),
        (("proton.me", "protonmail.com", "pm.me"), ("127.0.0.1", _PROTON, False))):
    for _d in _domaines:
        FOURNISSEURS[_d] = _fiche


def domaine_de(adresse):
    adresse = adresse.strip().lower()
    return adresse.rpartition("@")[2] if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", adresse) else ""


def fournisseur(adresse):
    """(serveur IMAP ou "", aide, connexion possible ?) pour cette adresse, sans rien demander à internet."""
    domaine = domaine_de(adresse)
    if not domaine:
        return "", "", True
    return FOURNISSEURS.get(domaine, ("", "Ton mot de passe de messagerie. Je chercherai le serveur de " + domaine + " tout seul.", True))


def chercher_serveur(domaine):
    """Le serveur IMAP d'un domaine qu'on ne connaît pas : l'annuaire public de Thunderbird, sinon imap.<domaine>."""
    try:
        with urllib.request.urlopen(f"https://autoconfig.thunderbird.net/v1.1/{domaine}", timeout=8) as reponse:
            page = reponse.read(200_000).decode("utf-8", errors="ignore")
        trouve = re.search(r'<incomingServer type="imap">.*?<hostname>([^<]+)</hostname>', page, re.S)
        if trouve:
            return trouve.group(1).strip()
    except (OSError, ValueError):
        pass
    return "imap." + domaine


def _ouvrir(serveur, adresse, mot_de_passe):
    boite = imaplib.IMAP4_SSL(serveur, 993, timeout=15)
    try:
        try:
            boite.login(adresse, mot_de_passe)
        except UnicodeEncodeError:                       # mot de passe avec accents : imaplib ne sait pas l'envoyer tel quel
            boite.authenticate("PLAIN", lambda _: f"\0{adresse}\0{mot_de_passe}".encode("utf-8"))
    except BaseException:
        boite.shutdown()
        raise
    return boite


def tester(adresse, mot_de_passe, serveur):
    """Essaie de se connecter. Renvoie "" si ça marche, sinon l'explication."""
    try:
        _ouvrir(serveur, adresse, mot_de_passe).logout()
        return ""
    except imaplib.IMAP4.error as refus:
        detail = " ".join(str(refus).strip("b'\"").split())[:120]
        return f"Connexion refusée par {serveur} : adresse ou mot de passe incorrect ({detail})."
    except socket.gaierror:
        return f"Serveur {serveur} introuvable : pas d'internet, ou un réseau (entreprise, école) qui bloque les mails."
    except (TimeoutError, OSError) as panne:
        return f"Impossible de joindre {serveur} (port 993) : {panne}. Un réseau d'entreprise bloque souvent les mails."


def compte():
    """{"adresse", "serveur"} de la boîte connectée, ou None."""
    try:
        fiche = json.loads(FICHIER.read_text(encoding="utf-8"))
        if fiche.get("adresse") and fiche.get("serveur"):
            return fiche
    except (OSError, ValueError):
        pass
    if ANCIENNE.get("adresse") and ANCIENNE.get("mot_de_passe_app"):
        return {"adresse": ANCIENNE["adresse"], "serveur": ANCIENNE.get("serveur_imap", "imap.gmail.com"), "ancienne": True}
    return None


def connecter(adresse, mot_de_passe, serveur=""):
    """Vérifie la connexion puis la retient. Renvoie "" si c'est bon, sinon l'explication."""
    adresse, serveur = adresse.strip(), serveur.strip()
    domaine = domaine_de(adresse)
    if not domaine:
        return "Cette adresse e-mail n'a pas l'air complète."
    if not mot_de_passe:
        return "Il manque le mot de passe."
    serveur = serveur or fournisseur(adresse)[0] or chercher_serveur(domaine)
    erreur = tester(adresse, mot_de_passe, serveur)
    if erreur:
        return erreur
    deconnecter()
    coffre.enregistrer(COFFRE, adresse, mot_de_passe)
    FICHIER.write_text(json.dumps({"adresse": adresse, "serveur": serveur}, ensure_ascii=False), encoding="utf-8")
    return ""


def deconnecter():
    fiche = compte()
    if fiche and not fiche.get("ancienne"):
        coffre.supprimer(COFFRE, fiche["adresse"])
    FICHIER.unlink(missing_ok=True)


def _texte(message):
    for partie in message.walk() if message.is_multipart() else [message]:
        if partie.get_content_type() == "text/plain":
            octets = partie.get_payload(decode=True) or b""
            return octets.decode(partie.get_content_charset() or "utf-8", errors="ignore")
    return ""


def _entete(message, nom):
    try:
        return str(make_header(decode_header(message.get(nom, ""))))
    except (ValueError, LookupError):
        return str(message.get(nom, ""))


AUTOMATIQUE = re.compile(r"no-?reply|ne-?pas-?repondre|newsletter|news@|marketing|promo|mailer|offres?@|notification", re.I)
SECURITE = re.compile(r"s[ée]curit|security|alerte|mot de passe|password|nouvelle connexion|v[ée]rifi|"
                      r"code de (?:v[ée]rification|s[ée]curit[ée]|confirmation)", re.I)
AFFAIRES = re.compile(r"facture|paiement|pr[ée]l[èe]vement|commande|livraison|colis|rendez-vous|rdv|convocation|contrat|"
                      r"imp[ôo]ts|urgent|[ée]ch[ée]ance|r[ée]servation|billet", re.I)
FENETRE = 40                      # on cherche les mails importants parmi les 40 derniers reçus


def classer(entetes, drapeaux):
    """« important », « normal » ou « publicite », d'après les en-têtes d'un mail et ses marques (lu, suivi…).

    Important : marqué d'une étoile ; ou une alerte de sécurité ; ou une facture, livraison, rendez-vous…
    qui n'est pas une lettre d'information ; ou écrit par une vraie personne et pas encore lu
    (ou jugé « important » par Gmail).
    Publicité : lettre d'information ou envoi en masse (lien de désabonnement, expéditeur « noreply »…).
    """
    sujet, expediteur = _entete(entetes, "Subject"), _entete(entetes, "From")
    lettre = bool(entetes.get("List-Unsubscribe") or entetes.get("List-Id")
                  or str(entetes.get("Precedence", "")).lower() in ("bulk", "list", "junk"))
    if "\\Flagged" in drapeaux or SECURITE.search(sujet):
        return "important"
    if AFFAIRES.search(sujet) and not lettre:
        return "important"
    if lettre or AUTOMATIQUE.search(expediteur):
        return "publicite"
    return "important" if "\\Seen" not in drapeaux or "\\Important" in drapeaux else "normal"


def _survol(boite, numeros, gmail):
    """Pour chaque numéro de message : (en-têtes, marques). Un seul aller-retour avec le serveur."""
    if not numeros:
        return {}
    quoi = "(FLAGS " + ("X-GM-LABELS " if gmail else "") + \
           "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE LIST-ID PRECEDENCE)])"
    _, reponse = boite.fetch(f"{int(numeros[0])}:{int(numeros[-1])}", quoi)
    resultat, courant = {}, None
    for element in reponse:
        if isinstance(element, tuple):
            courant = element[0].split()[0]
            resultat[courant] = [email.message_from_bytes(element[1]), element[0].decode("utf-8", "ignore")]
        elif courant is not None and isinstance(element, bytes):     # les marques arrivent parfois après les en-têtes
            resultat[courant][1] += element.decode("utf-8", "ignore")
    return resultat


def recents(nombre=5, importants=False):
    """Les derniers messages reçus, du plus récent au plus ancien : sujet, expéditeur, date, début du texte.
    importants=True : seulement ceux qui comptent (voir classer), cherchés parmi les 40 derniers."""
    fiche = compte()
    if not fiche:
        return ("Messagerie non connectée. Pour la connecter : tuile « Connecter mes mails » de l'accueil, "
                "ou clic droit sur la goutte › Messagerie.")
    mot_de_passe = ANCIENNE.get("mot_de_passe_app") if fiche.get("ancienne") else coffre.lire(COFFRE, fiche["adresse"])
    if not mot_de_passe:
        return "Erreur : je n'ai plus le mot de passe de ta messagerie. Reconnecte-la (clic droit sur la goutte › Messagerie)."
    nombre = max(1, min(int(nombre), 15))
    lignes = []
    try:
        boite = _ouvrir(fiche["serveur"], fiche["adresse"], mot_de_passe)
    except imaplib.IMAP4.error:
        return "Erreur : ta messagerie refuse la connexion (mot de passe changé ?). Reconnecte-la."
    except OSError as panne:
        return f"Erreur : impossible de joindre {fiche['serveur']} ({panne})."
    with boite:
        boite.select("INBOX", readonly=True)
        _, trouves = boite.search(None, "ALL")
        numeros = trouves[0].split()[-(FENETRE if importants else nombre):]
        try:
            survol = _survol(boite, numeros, "gmail" in fiche["serveur"])
        except imaplib.IMAP4.error:          # le serveur ne connaît pas les marques propres à Gmail
            survol = _survol(boite, numeros, False)
        for numero in reversed(numeros):
            entetes, marques = survol.get(numero, (None, ""))
            if entetes is None:
                continue
            genre = classer(entetes, marques)
            if importants and genre != "important":
                continue
            _, contenu = boite.fetch(numero, "(BODY.PEEK[])")
            message = email.message_from_bytes(contenu[0][1])
            try:
                date = parsedate_to_datetime(message.get("Date", "")).strftime("%d/%m à %Hh%M")
            except (TypeError, ValueError):
                date = message.get("Date", "")
            nom, adresse = parseaddr(_entete(message, "From"))
            etat = ", ".join(x for x in ("non lu" if "\\Seen" not in marques else "",
                                         "suivi" if "\\Flagged" in marques else "",
                                         "publicité" if genre == "publicite" else "") if x)
            extrait = " ".join(_texte(message).split())[:300]
            lignes.append(f"{len(lignes) + 1}. **{_entete(message, 'Subject') or '(sans sujet)'}** — {nom or adresse} "
                          f"({date}{', ' + etat if etat else ''})" + (f"\n   {extrait}" if extrait else ""))
            if len(lignes) >= nombre:
                break
    if not lignes:
        return f"Aucun mail important parmi les {FENETRE} derniers." if importants else "Boîte vide."
    return ("Mails importants :\n" if importants else "Derniers mails :\n") + "\n".join(lignes)
