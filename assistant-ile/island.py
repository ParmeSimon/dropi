"""La Dynamic Island : une goutte d'eau collée au bord de l'écran, avec Plop la mascotte dedans.

- Survole la goutte : Plop te sourit et te rappelle quoi faire
- Clic : elle s'ouvre (discussion)
- Attrape-la et tire : le col liquide s'étire puis casse ; lâche-la, elle file se coller
  au bord le plus proche (haut, bas, gauche ou droite) et s'en souvient
- Glisse des fichiers dessus : elle grossit, Plop ouvre la bouche, puis te demande quoi en faire
- Maintiens le micro pour parler, relâche pour envoyer
- Échap ou clic ailleurs : elle se referme
- Clic droit : nouvelle conversation / replacer en haut / quitter
"""
import os
import re
import sys
import math
import time
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path

import yaml
from PySide6.QtCore import (Qt, QEvent, QRectF, QPointF, QSizeF, QTimer, QVariantAnimation,
                            QEasingCurve, Signal, QObject, QSettings, QMimeData, QBuffer)
from PySide6.QtGui import (QPainter, QColor, QPen, QLinearGradient, QConicalGradient, QCursor,
                           QFontMetrics, QPainterPath, QPixmap, QIcon)
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QMenu, QFileDialog
from PySide6.QtNetwork import QLocalServer, QLocalSocket

import tools
import goutte
import menage
import musique
import memoire
import demarrage
import donnees
import classement
import coffre
import guetteur
import passerelle
import ordres
import rappels
import messagerie
import ocr
import composants as ui
from brain import Cerveau, Arrete
from mascotte import Mascotte, VueMascotte, image_logo
from voice import Micro

CERCLE = 46             # la goutte au repos
ECART = 8               # espace entre le bord de l'écran et la bulle (comblé par le col liquide)
MARGE = 10              # distance minimale aux coins de l'écran
CAPSULE_MAX = 440
SURVOL = (350, 124)     # quand un fichier passe au-dessus
LARGEUR_FICHIERS = 500
LARGEUR_CLE = 420
LARGEUR_MAIL = 440
DISCUSSION = (540, 630)
PANNEAUX = ("discussion", "fichiers", "cle", "mail")
RAYON_MAX = 22
R_MASCOTTE = 13.5
FICHIERS_VISIBLES = 3
LARGEUR_MUSIQUE = 330
PAUSE_VISIBLE = 8          # secondes pendant lesquelles une musique en pause reste affichée

VERBES = {
    "ouvrir_stream_twitch": "J'ouvre le stream de", "ouvrir_site": "J'ouvre",
    "recherche_web": "Je cherche", "lister_jeux": "Je regarde tes jeux", "lancer_jeu": "Je lance",
    "ouvrir_application": "J'ouvre", "ranger_fichier": "Je range", "supprimer_fichier": "Je supprime",
    "deplacer_fichier": "Je déplace", "renommer_fichier": "Je renomme", "lister_dossier": "Je regarde",
    "ranger_telechargements": "Je range tes téléchargements", "chercher_fichier": "Je cherche",
    "ouvrir_fichier": "J'ouvre", "afficher_dans_explorateur": "Je te montre", "lire_fichier": "Je lis",
    "mails_recents": "Je lis tes mails", "date_heure": "Je regarde l'heure",
    "se_renseigner": "Je me renseigne sur", "memoriser": "Je retiens", "analyser_espace": "J'analyse ton disque",
    "ranger_dossier": "Je range", "annuler_rangement": "J'annule le dernier rangement",
    "controler_musique": "Musique :", "musique_en_cours": "Je regarde ce qui joue",
    "regler_pc": "Je règle", "creer_rappel": "Je note le rappel", "lister_rappels": "Je regarde tes rappels",
    "supprimer_rappels": "Je supprime",
}

# L'accueil : des tuiles par section. Chaque tuile = (icône, libellé, action) ; l'action est une méthode
# de l'île (« _… »), un début de phrase à compléter (« champ:… ») ou une demande envoyée telle quelle.
ACCUEIL_RAPIDE = [("camera", "Lire du texte à l'écran", "_capturer_texte"),
                  ("minuteur", "Minuteur 5 minutes", "minuteur 5 minutes"),
                  ("cloche", "Créer un rappel", "champ:Rappelle-moi dans ")]
ACCUEIL_PC = [("balai", "Faire de la place", "_faire_de_la_place"),
              ("ranger", "Ranger mes téléchargements", "_ranger_telechargements"),
              ("bureau", "Ranger mon bureau", "range mon bureau"),
              ("cadenas", "Verrouiller le PC", "verrouille le pc"),
              ("cle", "Mes mots de passe", "_montrer_coffre"),
              ("mail", "Connecter mes mails", "_mails")]     # devient « Résumer mes mails » une fois connectée
# une tuile par usage (la première application installée pour cet usage), dans cet ordre
USAGES_ACCUEIL = [("navigateur", "web"), ("mails", "mail"), ("discussion", "message"), ("code", "code"),
                  ("tableur", "tableau"), ("texte", "document"), ("musique", "note"), ("vidéo", "video")]


REGLAGES = {"volume": "Je règle le volume", "luminosite": "Je règle la luminosité", "verrouiller": "Je verrouille le PC",
            "ecran": "J'éteins l'écran", "parametres": "J'ouvre les réglages"}


def decrire_action(nom, args):
    if nom == "regler_pc":
        return REGLAGES.get(str(args.get("reglage")), "Je règle le PC")
    verbe = VERBES.get(nom, nom.replace("_", " ").capitalize())
    for cle in ("chemin", "nom", "streamer", "site", "requete", "dossier", "question", "information", "action",
                "texte", "genre"):
        if args.get(cle):
            valeur = Path(str(args[cle])).name if cle == "chemin" else str(args[cle])
            return f"{verbe} « {valeur} »"[:80] if cle in ("question", "information") else f"{verbe} {valeur}"[:70]
    return verbe


def plein_ecran_actif(moi=0):
    """Vrai si la fenêtre au premier plan occupe tout son écran (jeu, vidéo en plein écran…)."""
    if sys.platform != "win32":
        return False
    u32 = ctypes.windll.user32
    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.MonitorFromWindow.restype = wintypes.HMONITOR
    u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    hwnd = u32.GetForegroundWindow()
    if not hwnd or hwnd == moi:
        return False
    classe = ctypes.create_unicode_buffer(64)
    u32.GetClassNameW(wintypes.HWND(hwnd), classe, 64)
    if classe.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
        return False                       # le bureau, la barre des tâches, le menu Démarrer

    class InfoEcran(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    fenetre = wintypes.RECT()
    u32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(fenetre))
    info = InfoEcran()
    info.cbSize = ctypes.sizeof(InfoEcran)
    u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
    e = info.rcMonitor
    return fenetre.left <= e.left and fenetre.top <= e.top and fenetre.right >= e.right and fenetre.bottom >= e.bottom


def sans_chemin(texte):
    """Enlève le chemin complet entre parenthèses (utile à l'IA, pas à l'affichage)."""
    return re.sub(r"\s*\([A-Za-z]:[\\/].*\)(?=\.?$)", "", texte)


def est_erreur(resultat):
    return (resultat.startswith(("Erreur", "Introuvable", "Fichier introuvable", "Dossier introuvable"))
            or "introuvable" in resultat[:60])


class Pont(QObject):
    """Transmet les résultats des threads vers l'interface."""
    reponse = Signal(str, bool)       # texte, erreur ?
    action = Signal(str)              # description d'un outil lancé par l'IA
    resultat = Signal(str, dict, bool)  # outil, arguments, réussi ?
    voix = Signal(str, str)           # texte transcrit, erreur
    direct = Signal(str, list, str, list)   # résumé, résultats, trace pour l'IA, fichiers (action sans IA)
    analyse = Signal()                # l'analyse du disque est prête (menage.derniere_analyse)
    menage = Signal(float, int, int, str)   # octets libérés, nombre, erreurs, quoi
    lecture = Signal(object)          # la musique en cours (dict) ou None
    champ_mdp = Signal(object)        # le champ mot de passe où on vient de cliquer (dict) ou None
    rempli = Signal(bool, str)        # le remplissage a marché ? site ou message d'erreur
    instant = Signal(str, str, dict, str)   # un ordre direct est fait : demande, outil, arguments, résultat
    texte_lu = Signal(str, str)       # le texte lu dans une capture d'écran, ou l'erreur
    partiel = Signal(str)             # la réponse de l'IA en train de s'écrire
    moteur = Signal(str)              # le moteur d'IA télécharge ou charge quelque chose ("" : fini)
    mail = Signal(str)                # l'essai de connexion à la messagerie est fini : "" ou l'explication de l'échec


class Ile(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)

        self.config = config
        self.cerveau = Cerveau(config, lambda texte: self.pont.moteur.emit(texte))
        self.micro =Micro(config.get("whisper_modele", "small"), config.get("langue", "fr"))
        self.mascotte = Mascotte()

        self.mode = "repos"          # repos, survol, fichiers, discussion
        self.etat = "repos"          # repos, travail, ecoute, succes, erreur
        self.statut = ""
        self.occupee = False
        self.fichiers = []
        self._mode_avant = "repos"
        self._apercu = ""
        self._souris = False
        self._dialogue = False
        self._actions = []
        self._derniere_frappe = 0.0
        self._etincelles = -10.0

        # où la goutte est collée (mémorisé d'une fois sur l'autre)
        self.reglages = QSettings("AssistantIle", "Ile")
        self.bord = str(self.reglages.value("bord", "haut"))
        if self.bord not in goutte.NORMALES:
            self.bord = "haut"
        self._fraction = float(self.reglages.value("position", 0.5))

        # physique de la goutte
        self._libre = False          # détachée du bord (on la tire, ou elle vole vers un bord)
        self._glisse = False         # le bouton de la souris la tient
        self._appui = None
        self._decalage = QPointF()
        self._rouvrir = None
        self._cx = goutte.Ressort(0, 22, .78)
        self._cy = goutte.Ressort(0, 22, .78)
        self._col_bord = None
        self._col_force = goutte.Ressort(1, 18, .55)
        self._ecrase = goutte.Ressort(0, 19, .25)
        self._etire = 0.0
        self._angle = 0.0
        self._elan, self._contre, self._sens, self._secousses = 0.0, False, True, []    # chocs et secousses
        self._caresses, self._caresse_pos = [], None                                    # chatouilles
        self._geo = None
        self._cle_fond, self._pix_fond, self._origine_fond = None, None, QPointF()
        self._t = time.monotonic()

        self.pont = Pont()
        self.pont.reponse.connect(self._reponse)
        self.pont.action.connect(self._action_ia)
        self.pont.resultat.connect(self._resultat_ia)
        self.pont.voix.connect(self._voix_recue)
        self.pont.direct.connect(self._fin_directe)
        self.pont.analyse.connect(self._carte_menage)
        self.pont.menage.connect(self._menage_fini)
        self.pont.lecture.connect(self._maj_musique)

        # musique en cours (Apple Music, Spotify…)
        self._musique, self._pix_cover, self._piste_cover, self._pause_depuis = None, None, None, None
        reglage_musique = config.get("musique") or {}
        if reglage_musique.get("afficher", True):
            musique.demarrer(self.pont.lecture.emit, reglage_musique.get("applis", ["AppleMusic", "iTunes", "Spotify"]))

        # surveillance des téléchargements (voir _verifier_telechargements)
        self._origine = "depot"          # d'où viennent les fichiers du panneau : depot ou telechargement
        self._proposes = []
        self._toast_telechargement = False
        self._carte_nettoyage = None
        self._mode_telechargements = str((config.get("telechargements") or {}).get("mode", "auto"))
        self._tailles_en_cours = {}
        try:
            self._connus = {str(p) for p in tools.fichiers_telechargements()}
        except OSError:
            self._connus = set()

        # mots de passe : le guetteur signale les champs « mot de passe » du navigateur (voir _champ_mdp)
        self._cle, self._cle_faite, self._toast_cle = None, None, False
        reglage_mdp = config.get("mots_de_passe") or {}
        self._longueur_mdp = int(reglage_mdp.get("longueur", 20))
        self.pont.champ_mdp.connect(self._champ_mdp)
        self.pont.rempli.connect(self._fin_remplissage)
        if reglage_mdp.get("activer", True):
            guetteur.demarrer(self.pont.champ_mdp.emit, self.pont.rempli.emit,
                              reglage_mdp.get("navigateurs", guetteur.NAVIGATEURS))
        # l'extension du navigateur (dossier extension/) confie les mots de passe au moment où on se connecte
        self._capture, self._toast_capture = None, False
        if reglage_mdp.get("activer", True) and reglage_mdp.get("capture", True):
            try:
                passerelle.inscrire()
            except OSError:
                pass
            self.passerelle = passerelle.Passerelle(self._message_extension, self)

        # ordres directs (ordres.py), rappels et minuteurs, lecture de texte à l'écran
        self.pont.instant.connect(self._fin_instant)
        self.pont.texte_lu.connect(self._texte_lu)
        self._minuteur_fin, self._toast_rappel, self._selection = None, False, None
        self._ia_en_cours = False
        self._sonnerie = QTimer(self, interval=1000, timeout=self._verifier_rappels)
        self._sonnerie.start()
        threading.Thread(target=tools.prechauffer, daemon=True).start()

        self.pont.mail.connect(self._fin_mail)
        self.pont.partiel.connect(self._texte_partiel)
        self.pont.moteur.connect(self._etat_moteur)
        self._vivant = None                  # le texte de l'IA en train de s'écrire dans le fil
        if config.get("prechauffer_ia", True):
            QTimer.singleShot(4000, lambda: threading.Thread(target=self.cerveau.prechauffer, daemon=True).start())
        self._tuiles = {}                    # les tuiles de l'accueil, par action

        self._construire_discussion()
        self._construire_fichiers()
        self._construire_cle()
        self._construire_mail()
        self._maj_tuile_mail()
        self.voile = ui.Voile(self)

        self._taille = QSizeF(CERCLE * 0.3, CERCLE * 0.3)   # petite apparition au lancement
        self._cible = QSizeF(self._taille)
        self.anim = QVariantAnimation(self)
        self.anim.valueChanged.connect(self._sur_anim)
        self.anim.finished.connect(self._fin_anim)

        self._horloge = QTimer(self, interval=16, timeout=self._tic)
        self._veille = QTimer(self, interval=90, timeout=self._verifier_clic_exterieur)
        self._fin_toast = QTimer(self, singleShot=True, timeout=self._statut_repos)

        self._ecrans_suivis = set()
        self._placer_sur_ecran(self._ecran_enregistre())
        self._horloge.start()
        # en jeu ou devant une vidéo en plein écran, la goutte s'efface (et ne consomme plus rien)
        self._cachee_plein_ecran = False
        self._plein_ecran = QTimer(self, interval=1500, timeout=self._verifier_plein_ecran)
        if config.get("masquer_en_plein_ecran", True):
            self._plein_ecran.start()
        self._surveillance = QTimer(self, interval=2000, timeout=self._verifier_telechargements)
        if self._mode_telechargements != "rien":
            self._surveillance.start()
        QTimer.singleShot(150, self._morph)

    # ================================================================ construction
    def _entete(self, titre):
        tete = QHBoxLayout()
        tete.setSpacing(4)
        vue = VueMascotte(self.mascotte, 10.5)
        etiquette = ui.EtiquetteCoupee(titre, taille=14, gras=True)
        tete.addWidget(vue)
        tete.addWidget(etiquette, 1)
        return tete, vue, etiquette

    def _construire_discussion(self):
        self.page_discussion = page = QWidget(self)
        page.hide()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 10, 12, 14)
        lay.setSpacing(8)

        tete, self.vue_disc, self.titre_disc = self._entete("Dropi")
        nouveau = ui.Bouton("nouveau", info="Nouvelle conversation")
        nouveau.clicked.connect(self._reset)
        reduire = ui.Bouton("reduire", info="Réduire (Échap)")
        reduire.clicked.connect(self.fermer)
        tete.addWidget(nouveau)
        tete.addWidget(reduire)
        lay.addLayout(tete)

        self.fil = ui.Fil()
        lay.addWidget(self.fil, 1)

        self.accueil = QWidget()
        acc = QVBoxLayout(self.accueil)
        acc.setContentsMargins(6, 0, 6, 0)
        acc.setSpacing(4)
        acc.addStretch(1)
        self.vue_accueil = VueMascotte(self.mascotte, 19, halo=True)
        acc.addWidget(self.vue_accueil, 0, Qt.AlignHCenter)
        titre = ui.Etiquette("Qu'est-ce que je peux faire pour toi ?", 18, gras=True)
        titre.setAlignment(Qt.AlignCenter)
        sous = ui.Etiquette("Écris, parle, ou dépose un fichier sur la goutte.", 12, ui.TEXTE_3)
        sous.setAlignment(Qt.AlignCenter)
        acc.addWidget(titre)
        acc.addWidget(sous)
        acc.addSpacing(4)
        rapide, pc = list(ACCUEIL_RAPIDE), list(ACCUEIL_PC)
        if tools.catalogue_jeux():
            pc.append(("manette", "Mes jeux", "_mes_jeux"))
        self._section(acc, 1, "Rapide", "eclair", rapide)
        self._section(acc, 2, "Mon PC", "pc", pc)
        # la place qui reste : deux rangées d'applications si les sections du dessus en font trois au plus, sinon une
        self._places_applis = 6 if -(-len(rapide) // 3) - (-len(pc) // 3) <= 3 else 3
        # les applications installées : la section se remplit dès que Windows a donné la liste
        self.section_applis = QWidget()
        self.section_applis.hide()
        QVBoxLayout(self.section_applis).setContentsMargins(0, 0, 0, 0)
        acc.addWidget(self.section_applis)
        acc.addStretch(2)
        lay.addWidget(self.accueil, 1)

        barre, self.champ, micro, self.btn_envoyer = ui.barre_saisie("Demande-moi quelque chose…")
        self.champ.returnPressed.connect(lambda: self.envoyer(self.champ.text()))
        self.champ.textEdited.connect(self._frappe)
        # pendant que l'IA travaille, le bouton d'envoi devient un carré : il arrête la demande
        self.btn_envoyer.clicked.connect(lambda: self._arreter() if self._ia_en_cours else self.envoyer(self.champ.text()))
        micro.pressed.connect(self._micro_debut)
        micro.released.connect(self._micro_fin)
        lay.addWidget(barre)
        self._maj_accueil()

    def _section(self, lay, numero, titre, icone, tuiles):
        """Un titre « 01 — RAPIDE » puis ses tuiles, trois par rangée."""
        lay.addSpacing(4)
        lay.addWidget(ui.TitreSection(numero, titre, icone))
        grille = QGridLayout()
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setSpacing(6)
        for colonne in range(3):
            grille.setColumnStretch(colonne, 1)
        for i, (icone_tuile, texte, action) in enumerate(tuiles):
            tuile = self._tuiles[action] = ui.Tuile(icone_tuile, texte)
            tuile.clicked.connect(lambda _=False, a=action: self._tuile(a))
            grille.addWidget(tuile, i // 3, i % 3)
        lay.addLayout(grille)

    def _tuile(self, action):
        if self.occupee:
            return
        if action.startswith("champ:"):          # une phrase à finir : « Rappelle-moi dans … »
            self.champ.setText(action[6:])
            self.champ.setFocus()
        elif action.startswith("appli:"):
            self._ordre_direct(f"Ouvre {action[6:]}", ("outil", "ouvrir_application", {"nom": action[6:]}))
        elif action.startswith("_"):
            getattr(self, action)()
        else:
            self.envoyer(action)

    def _maj_applis_accueil(self):
        """La section « Mes applis » : « Mes jeux » en premier (seulement si des jeux sont détectés), puis une tuile
        par usage quand Windows a donné la liste des applications. 6 tuiles au plus en tout ; la section se refait
        si la liste change."""
        apps = [(icone, tools.USAGES_ICI[usage][0], "appli:" + tools.USAGES_ICI[usage][0])
                for usage, icone in USAGES_ACCUEIL if usage in tools.USAGES_ICI]
        if not hasattr(self, "_a_des_jeux"):
            self._a_des_jeux = bool(tools.catalogue_jeux())          # pas de jeu détecté : pas de tuile
        jeux = [("manette", "Mes jeux", "_mes_jeux")] if self._a_des_jeux else []
        tuiles = jeux + apps[:self._places_applis - len(jeux)]
        if not tuiles or tuiles == getattr(self, "_tuiles_applis", None):
            return
        self._tuiles_applis = tuiles
        lay = self.section_applis.layout()
        while lay.count():
            element = lay.takeAt(0)
            if element.widget():
                element.widget().deleteLater()
            elif element.layout():
                while element.layout().count():
                    w = element.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self._section(lay, 3, "Mes applis", "applis", tuiles)
        self.section_applis.show()

    def _construire_fichiers(self):
        self.page_fichiers = page = QWidget(self)
        page.hide()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 10, 12, 14)
        lay.setSpacing(10)

        tete, self.vue_fich, self.titre_fich = self._entete("")
        fermer = ui.Bouton("fermer", info="Annuler (Échap)")
        fermer.clicked.connect(self.fermer)
        tete.addWidget(fermer)
        lay.addLayout(tete)

        self.liste = QVBoxLayout()
        self.liste.setSpacing(6)
        lay.addLayout(self.liste)
        self.autres = ui.Etiquette("", 12, ui.TEXTE_3)
        self.autres.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(self.autres)

        # la proposition d'endroit (rangement méthodique TYPE / SOURCE)
        self.proposition = ui.Proposition()
        self.proposition.ranger.connect(lambda: self._action_directe("ranger"))
        lay.addWidget(self.proposition)

        puces = QHBoxLayout()
        puces.setSpacing(6)
        ouvrir = ui.Bouton("ouvrir", "Ouvrir", "puce")
        ouvrir.clicked.connect(lambda: self._action_directe("ouvrir"))
        deplacer = ui.Bouton("deplacer", "Déplacer…", "puce")
        deplacer.clicked.connect(self._deplacer)
        self.btn_suppr = ui.Bouton("supprimer", "Supprimer", "puce", info="Envoie à la corbeille")
        self.btn_suppr.clicked.connect(self._supprimer)
        montrer = ui.Bouton("explorateur", genre="puce", info="Afficher dans l'explorateur")
        montrer.clicked.connect(lambda: self._action_directe("afficher"))
        self.btn_resume = ui.Bouton("document", "Résumer", "puce", info="Lire le document et t'en faire un résumé")
        self.btn_resume.clicked.connect(self._resumer)
        for b in (self.btn_resume, ouvrir, deplacer, self.btn_suppr, montrer):
            puces.addWidget(b)
        puces.addStretch(1)
        lay.addLayout(puces)

        barre, self.champ_fich, micro, envoyer = ui.barre_saisie("Ou dis-moi quoi en faire…")
        self.champ_fich.returnPressed.connect(lambda: self._pour_fichiers(self.champ_fich.text()))
        self.champ_fich.textEdited.connect(self._frappe)
        envoyer.clicked.connect(lambda: self._pour_fichiers(self.champ_fich.text()))
        micro.pressed.connect(self._micro_debut)
        micro.released.connect(self._micro_fin)
        lay.addWidget(barre)

    def _construire_cle(self):
        self.page_cle = page = QWidget(self)
        page.hide()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 10, 12, 14)
        lay.setSpacing(8)

        tete, self.vue_cle, self.titre_cle = self._entete("")
        fermer = ui.Bouton("fermer", info="Annuler (Échap)")
        fermer.clicked.connect(self.fermer)
        tete.addWidget(fermer)
        lay.addLayout(tete)

        # les comptes déjà enregistrés pour ce site : un clic remplit
        self.comptes_cle = QVBoxLayout()
        self.comptes_cle.setSpacing(6)
        lay.addLayout(self.comptes_cle)
        self.chapeau_cle = ui.Etiquette("", 12, ui.TEXTE_3)
        self.chapeau_cle.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(self.chapeau_cle)

        self.champ_login = ui.Champ("Identifiant ou e-mail")
        self.champ_login.returnPressed.connect(lambda: self.champ_passe.setFocus())
        self.champ_login.textEdited.connect(self._frappe)
        lay.addWidget(self.champ_login)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.champ_passe = ui.Champ("Mot de passe")
        self.champ_passe.returnPressed.connect(self._enregistrer_cle)
        self.champ_passe.textEdited.connect(self._frappe)
        autre = ui.Bouton("regenerer", info="Un autre mot de passe")
        autre.clicked.connect(lambda: self.champ_passe.setText(coffre.generer(self._longueur_mdp)))
        copier = ui.Bouton("copier", info="Copier (effacé du presse-papiers au bout de 30 secondes)")
        copier.clicked.connect(self._copier_cle)
        ligne.addWidget(self.champ_passe, 1)
        ligne.addWidget(autre)
        ligne.addWidget(copier)
        lay.addLayout(ligne)
        aide = ui.Etiquette("Mot de passe robuste proposé. Déjà un compte ? Tape le tien à la place.", 11, ui.TEXTE_3)
        aide.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(aide)

        bas = QHBoxLayout()
        bas.addStretch(1)
        valider = ui.Bouton("ok", "Enregistrer et remplir", "accent")
        valider.clicked.connect(self._enregistrer_cle)
        bas.addWidget(valider)
        lay.addLayout(bas)

    def _construire_mail(self):
        self.page_mail = page = QWidget(self)
        page.hide()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 10, 12, 14)
        lay.setSpacing(8)
        largeur = LARGEUR_MAIL - 34

        tete, self.vue_mail, self.titre_mail = self._entete("Connecter ma messagerie")
        fermer = ui.Bouton("fermer", info="Fermer (Échap)")
        fermer.clicked.connect(self.fermer)
        tete.addWidget(fermer)
        lay.addLayout(tete)

        # l'état : « Connectée : … », « Je vérifie… » ou l'explication d'un échec
        self.etat_mail = ui.Etiquette("", 12, ui.TEXTE_2)
        self.etat_mail.setWordWrap(True)
        self.etat_mail.setFixedWidth(largeur)
        self.etat_mail.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(self.etat_mail)

        self.champ_adresse = ui.Champ("Ton adresse e-mail (Orange, Gmail, Free…)")
        self.champ_adresse.textEdited.connect(lambda _: self._maj_aide_mail())
        self.champ_adresse.returnPressed.connect(lambda: self.champ_mdp_mail.setFocus())
        lay.addWidget(self.champ_adresse)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.champ_mdp_mail = ui.Champ("Mot de passe")
        self.champ_mdp_mail.setEchoMode(ui.Champ.Password)
        self.champ_mdp_mail.returnPressed.connect(self._connecter_mail)
        voir = ui.Bouton("oeil", info="Montrer / cacher le mot de passe")
        voir.clicked.connect(lambda: self.champ_mdp_mail.setEchoMode(
            ui.Champ.Normal if self.champ_mdp_mail.echoMode() == ui.Champ.Password else ui.Champ.Password))
        ligne.addWidget(self.champ_mdp_mail, 1)
        ligne.addWidget(voir)
        lay.addLayout(ligne)
        self.champ_serveur = ui.Champ("Serveur de réception (IMAP) : trouvé tout seul")
        self.champ_serveur.textEdited.connect(lambda _: setattr(self, "_serveur_saisi", True))
        lay.addWidget(self.champ_serveur)

        # ce qu'il faut savoir pour ce fournisseur (mot de passe d'application de Gmail, etc.)
        self.aide_mail = ui.Etiquette("", 11, ui.TEXTE_3)
        self.aide_mail.setTextFormat(Qt.RichText)
        self.aide_mail.setWordWrap(True)
        self.aide_mail.setOpenExternalLinks(True)
        self.aide_mail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.aide_mail.setFixedSize(largeur, 50)       # trois lignes, toujours : le panneau ne saute pas pendant la saisie
        self.aide_mail.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(self.aide_mail)

        bas = QHBoxLayout()
        self.btn_deconnecter = ui.Bouton("fermer", "Déconnecter", "puce")
        self.btn_deconnecter.clicked.connect(self._deconnecter_mail)
        self.btn_connecter = ui.Bouton("ok", "Tester et connecter", "accent")
        self.btn_connecter.clicked.connect(self._connecter_mail)
        bas.addWidget(self.btn_deconnecter)
        bas.addStretch(1)
        bas.addWidget(self.btn_connecter)
        lay.addLayout(bas)
        self._serveur_saisi = False

    # ================================================================ écran et bord
    def _ecran_enregistre(self):
        nom = self.reglages.value("ecran", "")
        return next((e for e in QApplication.screens() if e.name() == nom), QApplication.primaryScreen())

    def _placer_sur_ecran(self, ecran):
        """La toile couvre la zone utile de l'écran ; le vide transparent laisse passer les clics."""
        self.ecran = ecran
        zone = ecran.availableGeometry()
        if zone == ecran.geometry():
            zone.adjust(0, 0, 0, -1)     # jamais tout l'écran : Windows croirait à un jeu en plein écran
        self.setGeometry(zone)
        self._geo = None
        self._cle_fond = None
        if ecran.name() not in self._ecrans_suivis:
            self._ecrans_suivis.add(ecran.name())
            ecran.availableGeometryChanged.connect(lambda _, e=ecran: e is self.ecran and self._placer_sur_ecran(e))

    def _position(self):
        longueur = self.width() if self.bord in ("haut", "bas") else self.height()
        return goutte.borne(self._fraction * longueur, MARGE + CERCLE / 2, longueur - MARGE - CERCLE / 2)

    def _centre_ancre(self):
        a, d = self._position(), ECART + CERCLE / 2
        return {"haut": QPointF(a, d), "bas": QPointF(a, self.height() - d),
                "gauche": QPointF(d, a), "droite": QPointF(self.width() - d, a)}[self.bord]

    def _rect_ancre(self, t):
        w, h, a = t.width(), t.height(), self._position()
        if self.bord in ("haut", "bas"):
            x = goutte.borne(a - w / 2, MARGE, self.width() - MARGE - w)
            y = ECART if self.bord == "haut" else self.height() - ECART - h
        else:
            y = goutte.borne(a - h / 2, MARGE, self.height() - MARGE - h)
            x = ECART if self.bord == "gauche" else self.width() - ECART - w
        return QRectF(x, y, w, h)

    def _enregistrer_position(self):
        self.reglages.setValue("bord", self.bord)
        self.reglages.setValue("position", self._fraction)
        self.reglages.setValue("ecran", self.ecran.name())

    # ================================================================ forme et animation
    def _rect_forme(self, taille=None):
        t = taille or self._taille
        if self._libre:
            return QRectF(self._cx.valeur - t.width() / 2, self._cy.valeur - t.height() / 2, t.width(), t.height())
        return self._rect_ancre(t)

    def _musique_visible(self):
        d = self._musique
        if not d or self._libre or self.statut:
            return False
        return d["joue"] or (self._pause_depuis is not None and time.monotonic() - self._pause_depuis < PAUSE_VISIBLE)

    def _texte_capsule(self):
        if self._libre:
            return ""
        if self.statut:
            return self.statut
        if self._minuteur_fin:
            reste = max(0, round(self._minuteur_fin - time.time()))
            return f"Minuteur  {reste // 60}:{reste % 60:02d}"
        return "Clique, tire-moi, ou dépose un fichier" if self._souris else ""

    def _taille_cible(self):
        if self.mode == "survol":
            return QSizeF(*SURVOL)
        if self.mode == "fichiers":
            return QSizeF(LARGEUR_FICHIERS, self.page_fichiers.sizeHint().height())
        if self.mode == "discussion":
            return QSizeF(*DISCUSSION)
        if self.mode == "cle":
            return QSizeF(LARGEUR_CLE, self.page_cle.sizeHint().height())
        if self.mode == "mail":
            return QSizeF(LARGEUR_MAIL, self.page_mail.sizeHint().height())
        if self._musique_visible():
            return QSizeF(LARGEUR_MUSIQUE, CERCLE)
        texte = self._texte_capsule()
        if not texte:
            return QSizeF(CERCLE, CERCLE)
        fm = QFontMetrics(ui.police(13))
        return QSizeF(min(fm.horizontalAdvance(texte) + CERCLE + 24, CAPSULE_MAX), CERCLE)

    def _centre_mascotte(self, rect):
        if self.mode == "survol":
            return QPointF(rect.left() + 62, rect.center().y() + 2)
        if self._libre or rect.width() <= CERCLE + 1:
            return rect.center()
        if self.bord == "droite":
            return QPointF(rect.right() - CERCLE / 2, rect.center().y())
        return QPointF(rect.left() + CERCLE / 2, rect.center().y())

    def _page(self, mode):
        return {"discussion": self.page_discussion, "fichiers": self.page_fichiers, "cle": self.page_cle,
                "mail": self.page_mail}.get(mode)

    def _aller(self, mode):
        self.mode = mode
        for m in PANNEAUX:
            if m != mode:
                self._page(m).hide()
        if mode != "cle":
            self.champ_passe.clear()         # un mot de passe ne reste jamais dans un panneau fermé
        if mode != "mail":
            self.champ_mdp_mail.clear()
        if mode == "discussion":
            self._maj_applis_accueil()
        if mode in PANNEAUX:
            self._veille.start()
        else:
            self._veille.stop()
        self._morph()

    def _morph(self):
        cible = self._taille_cible()
        page = self._page(self.mode)
        if page and page.isVisible():
            if cible.height() <= self._taille.height() and cible.width() <= self._taille.width():
                page.setGeometry(self._rect_forme(cible).toRect())   # rétrécit : le contenu reste visible
            else:
                page.hide()
        self._horloge.setInterval(16)
        if cible == self._cible and (self.anim.state() == QVariantAnimation.Running or self._taille == cible):
            if self.anim.state() != QVariantAnimation.Running:
                self._fin_anim()
            return
        self._cible = cible
        grandit = cible.width() * cible.height() > self._taille.width() * self._taille.height()
        courbe = QEasingCurve(QEasingCurve.OutBack)
        courbe.setOvershoot(1.25 if grandit else 0.7)
        self.anim.stop()
        self.anim.setStartValue(QSizeF(self._taille))
        self.anim.setEndValue(cible)
        self.anim.setDuration(440 if grandit else 340)
        self.anim.setEasingCurve(courbe)
        self.anim.start()

    def _sur_anim(self, taille):
        self._taille = taille

    def _fin_anim(self):
        page = self._page(self.mode)
        if page and not page.isVisible():
            rect = self._rect_forme()
            page.setGeometry(rect.toRect())
            page.show()
            self.voile.couvrir(rect, min(rect.height() / 2, RAYON_MAX))
            champ_cle = self.champ_passe if self.champ_login.text() else self.champ_login
            champ_mail = self.champ_mdp_mail if self.champ_adresse.text() else self.champ_adresse
            champ = {"discussion": self.champ, "cle": champ_cle, "mail": champ_mail}.get(self.mode, self.champ_fich)
            champ.setFocus()

    # ================================================================ la goutte : géométrie
    def _calculer_geo(self):
        rect = self._rect_forme()
        if rect.width() < 2:
            return None
        rayon = min(rect.height() / 2, rect.width() / 2, RAYON_MAX)
        bord_col = self._col_bord if self._libre else self.bord
        force = min(self._col_force.valeur, 1.15) if self._libre else 1.0
        ecrase = self._ecrase.valeur
        etire = self._etire if self._libre else 0.0
        cle = (round(rect.x() * 2), round(rect.y() * 2), round(rect.width() * 2), round(rect.height() * 2),
               self.mode, bord_col, round(force * 200), round(ecrase * 400), round(etire * 300),
               round(self._angle * 40) if etire > 0.005 else 0)
        if self._geo and self._geo["cle"] == cle:
            return self._geo

        n = goutte.NORMALES[bord_col or self.bord]
        if self.mode == "repos":
            pts = goutte.contour(rect, rayon)
            if abs(ecrase) > 0.002 or etire > 0.005:
                appui = abs(n[0]) * rect.width() / 2 + abs(n[1]) * rect.height() / 2
                pts = goutte.deformer(pts, rect.center(), etire, self._angle, ecrase, n, appui)
            chemin = goutte.lisse(pts)
        else:
            chemin = QPainterPath()
            chemin.addRoundedRect(rect, rayon, rayon)
        if bord_col and force > 0.02:
            repere = goutte.repere_local(bord_col, self.width(), self.height())
            local = repere.mapRect(rect)
            if local.top() > goutte.CASSE * 1.1:         # cassé et déjà loin : plus de fil du tout
                force = 0.0
            tension = (local.top() - ECART) / (goutte.RUPTURE - ECART)
            panneau = goutte.borne((min(local.width(), local.height()) / 2 - rayon) / 10, 0, 1)
            col = goutte.col(local, rayon, tension, force, panneau)
            if col is not None:
                chemin = chemin.united(repere.inverted()[0].map(col))
        bornes = chemin.boundingRect().adjusted(-26, -26, 26, 32) & QRectF(self.rect())
        return {"cle": cle, "chemin": chemin, "rect": rect, "rayon": rayon, "bornes": bornes}

    # ================================================================ boucle d'animation
    def _tic(self):
        maintenant = time.monotonic()
        dt = min(0.05, maintenant - self._t)
        self._t = maintenant
        curseur = QCursor.pos()
        if self._libre:
            self._physique(dt, curseur)
        self._ecrase.pas(dt)

        self.mascotte.base = self._humeur()
        self.mascotte.ecrase = goutte.borne(self._ecrase.valeur * 0.8, -0.3, 0.45)
        ancre = self._ancre_mascotte()
        self._chatouilles(curseur, ancre)
        self.mascotte.maj(dt, ancre, QPointF(curseur))

        ancienne, self._geo = self._geo, self._calculer_geo()
        if self._geo is None:
            return
        lueur = self._lueur_active()
        if ancienne is None or ancienne["cle"] != self._geo["cle"]:
            zone = self._geo["bornes"] if ancienne is None else self._geo["bornes"].united(ancienne["bornes"])
            self.update(zone.adjusted(-40, -40, 40, 40).toAlignedRect())
        elif lueur:
            self.update(self._geo["bornes"].toAlignedRect())
        elif self.mode in ("repos", "survol"):
            c = self._centre_mascotte(self._geo["rect"])
            self.update(QRectF(c.x() - 55, c.y() - 55, 110, 110).toAlignedRect())
        for vue in (self.vue_disc, self.vue_fich, self.vue_cle, self.vue_mail, self.vue_accueil):
            if vue.isVisible():
                vue.update()

        agite = (self._libre or self.anim.state() == QVariantAnimation.Running or not self._ecrase.calme()
                 or self.mascotte.agite() or self.mode == "survol" or lueur)
        # 60 images/s quand ça bouge, 20 au calme (Plop respire), 10 quand il dort : l'île reste légère
        self._horloge.setInterval(16 if agite else (100 if self.mascotte.humeur() == "dort" else 50))

    def _physique(self, dt, curseur):
        if self._glisse:
            pos = QPointF(self.mapFromGlobal(curseur)) - self._decalage
            demi = CERCLE / 2 + 2
            self._cx.cible = goutte.borne(pos.x(), demi, self.width() - demi)
            self._cy.cible = goutte.borne(pos.y(), demi, self.height() - demi)
        self._cx.pas(dt)
        self._cy.pas(dt)
        if self._glisse:
            self._chocs(dt)
        vx, vy = self._cx.vitesse, self._cy.vitesse
        vitesse = math.hypot(vx, vy)
        self._etire += (goutte.borne(vitesse / 2600, 0, 0.42) - self._etire) * (1 - math.exp(-dt * 14))
        if vitesse > 30:
            self._angle = math.atan2(vy, vx)
        self.mascotte.vent = vx

        # le col liquide : il s'étire, casse, et se reforme près d'un bord
        rect = self._rect_forme()
        ecarts = {"haut": rect.top(), "bas": self.height() - rect.bottom(),
                  "gauche": rect.left(), "droite": self.width() - rect.right()}
        if self._col_bord and self._col_force.cible > 0:
            if ecarts[self._col_bord] > goutte.CASSE:
                self._col_force.cible = 0.0
                self._col_force.valeur = min(self._col_force.valeur, 0.5)     # il casse net, sans traîner en long fil
                self._ecrase.vitesse -= 3.0
                self.mascotte.reagir("surpris", 0.5)
        else:
            proche = min(ecarts, key=ecarts.get)
            if ecarts[proche] < goutte.ACCROCHE and (self._col_force.valeur < 0.05 or self._col_bord == proche):
                if self._col_bord != proche:
                    self._col_force.valeur = 0.0
                self._col_bord = proche
                self._col_force.cible = 1.0
                self._ecrase.vitesse += 2.5
        self._col_force.pas(dt)
        if self._col_force.cible == 0 and self._col_force.valeur < 0.02:
            self._col_bord = None

        if not self._glisse:
            c = self._centre_ancre()
            if abs(self._cx.valeur - c.x()) < 0.6 and abs(self._cy.valeur - c.y()) < 0.6 and vitesse < 25:
                self._atterrir()

    def _chocs(self, dt):
        """Quand on promène la goutte : Plop se cogne aux bords de l'écran, et finit étourdi si on le secoue."""
        vx, vy = self._cx.vitesse, self._cy.vitesse
        self._elan = max(math.hypot(vx, vy), self._elan * math.exp(-dt * 2.5))    # l'élan qu'il avait juste avant
        demi = CERCLE / 2 + 2
        limites = ((self._cx, demi, self.width() - demi), (self._cy, demi, self.height() - demi))
        contre = any(r.valeur - mini < 6 or maxi - r.valeur < 6 for r, mini, maxi in limites)
        if contre and not self._contre and self._elan > 550:
            rebond = min(self._elan, 1800) * 0.5
            for r, mini, maxi in limites:
                if r.valeur - mini < 6:
                    r.vitesse = rebond
                elif maxi - r.valeur < 6:
                    r.vitesse = -rebond
            self._ecrase.vitesse += min(2.5 + self._elan / 500, 6.0)
            fort = self._elan > 1600
            self.mascotte.reagir("etourdi" if fort else "aie", 2.4 if fort else 1.0)
            self._elan = 0.0
        self._contre = contre
        # secoué : il change de sens vite et souvent
        if abs(vx) > 450 and (vx > 0) != self._sens:
            self._sens = vx > 0
            self._secousses = [t for t in self._secousses if self._t - t < 1.4] + [self._t]
            if len(self._secousses) >= 5:
                self._secousses = []
                self.mascotte.reagir("etourdi", 2.6)

    def _chatouilles(self, curseur, ancre):
        """La souris qui s'agite sur Plop le fait rire."""
        if self._libre or self.occupee or self.mode == "survol":
            return
        precedent, self._caresse_pos = self._caresse_pos, QPointF(curseur)
        if precedent is None or (QPointF(curseur) - ancre).manhattanLength() > 28:
            return
        distance = (QPointF(curseur) - precedent).manhattanLength()
        if distance:
            self._caresses = [(t, d) for t, d in self._caresses if self._t - t < 1.2] + [(self._t, distance)]
            if sum(d for _, d in self._caresses) > 240:
                self._caresses = []
                self.mascotte.reagir("rire", 1.6)

    def _ancre_mascotte(self):
        if self.mode == "discussion" and self.vue_disc.isVisible():
            return self.vue_disc.centre_global()
        if self.mode == "fichiers" and self.vue_fich.isVisible():
            return self.vue_fich.centre_global()
        if self.mode == "cle" and self.vue_cle.isVisible():
            return self.vue_cle.centre_global()
        if self.mode == "mail" and self.vue_mail.isVisible():
            return self.vue_mail.centre_global()
        if self._geo:
            return QPointF(self.mapToGlobal(self._centre_mascotte(self._geo["rect"])))
        return QPointF(QCursor.pos())

    def _humeur(self):
        if self._libre:
            return "surpris" if math.hypot(self._cx.vitesse, self._cy.vitesse) > 250 else "content"
        if self.mode == "survol":
            return "faim"
        if self.etat in ("ecoute", "erreur"):
            return self.etat
        if self.etat == "travail":
            return "reflechit"
        if self.etat == "succes":
            return "content"
        if self.mode == "fichiers":
            return "curieux"
        if time.monotonic() - self._derniere_frappe < 1.2:
            return "tape"
        if self._souris and self.mode == "repos":
            return "content"
        return "repos"

    def _lueur_active(self):
        return self.etat in ("travail", "ecoute") or 0 <= self.mascotte.t - self._etincelles < 1.0

    # ================================================================ dessin
    def paintEvent(self, _):
        geo = self._geo or self._calculer_geo()
        if not geo:
            return
        self._geo = geo
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if self._cle_fond != geo["cle"]:
            self._rendre_fond(geo)
        p.drawPixmap(self._origine_fond, self._pix_fond)
        self._dessiner_bord(p, geo)
        r = geo["rect"]
        if self.mode == "repos":
            self._dessiner_capsule(p, r)
        elif self.mode == "survol":
            self._dessiner_depot(p, r)

    def _rendre_fond(self, geo):
        """Ombre + remplissage, gardés en cache tant que la forme ne bouge pas."""
        zone = geo["bornes"].toAlignedRect()
        ratio = self.devicePixelRatioF()
        pix = QPixmap(max(1, round(zone.width() * ratio)), max(1, round(zone.height() * ratio)))
        pix.setDevicePixelRatio(ratio)
        pix.fill(Qt.transparent)
        q = QPainter(pix)
        q.setRenderHint(QPainter.Antialiasing)
        q.translate(-zone.x(), -zone.y())
        ui.dessiner_ombre(q, geo["chemin"])
        q.fillPath(geo["chemin"], ui.remplissage_ile(geo["rect"]))
        q.end()
        self._pix_fond, self._origine_fond, self._cle_fond = pix, QPointF(zone.topLeft()), geo["cle"]

    def _dessiner_bord(self, p, geo):
        chemin, r = geo["chemin"], geo["rect"]
        a = ui.accent()
        if self.mode == "survol":
            p.strokePath(chemin, QPen(QColor(a.red(), a.green(), a.blue(), 220), 1.5))
            return
        reflet = QLinearGradient(r.topLeft(), r.bottomLeft())
        reflet.setColorAt(0, QColor(255, 255, 255, 44))
        reflet.setColorAt(1, QColor(255, 255, 255, 12))
        p.strokePath(chemin, QPen(reflet, 1))
        t = self.mascotte.t
        if self.etat == "travail":
            # un reflet de lumière qui fait le tour de la goutte
            for largeur, alpha in ((5, 60), (1.7, 255)):
                g = QConicalGradient(r.center(), (-t * 240) % 360)
                g.setColorAt(0, QColor(a.red(), a.green(), a.blue(), alpha))
                g.setColorAt(0.18, QColor(a.red(), a.green(), a.blue(), 0))
                g.setColorAt(0.82, QColor(a.red(), a.green(), a.blue(), 0))
                g.setColorAt(1, QColor(a.red(), a.green(), a.blue(), alpha))
                p.strokePath(chemin, QPen(g, largeur))
        elif self.etat == "ecoute":
            pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.3)
            p.strokePath(chemin, QPen(QColor(240, 82, 79, round(90 + 140 * pulse)), 1.4 + 1.6 * pulse))
        elif self.etat == "erreur":
            p.strokePath(chemin, QPen(QColor(255, 153, 164, 200), 1.4))
        elif 0 <= t - self._etincelles < 1.0:
            p.strokePath(chemin, QPen(QColor(108, 203, 95, round(230 * (1 - (t - self._etincelles)))), 1.6))

    def _dessiner_capsule(self, p, r):
        if self._musique_visible():
            self._dessiner_musique(p, r)
            return
        centre = self._centre_mascotte(r)
        taille = min(1.0, r.height() / CERCLE)
        self.mascotte.dessiner(p, centre, R_MASCOTTE * taille)
        self._dessiner_extras(p, centre)
        texte = self._texte_capsule()
        if texte and r.width() > CERCLE + 10:
            p.save()
            p.setClipRect(r)
            p.setOpacity(min(1.0, (r.width() - CERCLE) / 60))
            p.setFont(ui.police(13))
            p.setPen(ui.TEXTE if self.statut else ui.TEXTE_2)
            largeur = int(max(self._cible.width() - CERCLE - 22, 10))
            texte = p.fontMetrics().elidedText(texte, Qt.ElideRight, largeur)
            if self.bord == "droite":
                zone = QRectF(r.right() - CERCLE - 4 - largeur, r.top(), largeur, r.height())
                p.drawText(zone, Qt.AlignVCenter | Qt.AlignRight, texte)
            else:
                zone = QRectF(r.left() + CERCLE + 4, r.top(), largeur, r.height())
                p.drawText(zone, Qt.AlignVCenter | Qt.AlignLeft, texte)
            p.restore()

    def _rect_cover(self, r):
        return QRectF(r.left() + 7, r.center().y() - 16, 32, 32)

    def _dessiner_musique(self, p, r):
        """Cover à gauche, titre et artiste au milieu, temps à droite."""
        d = self._musique
        p.save()
        cover = self._rect_cover(r)
        if self._pix_cover is not None:
            ui.peindre_image(p, self._pix_cover, cover, 8)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(ui.CARTE_SURVOL)
            p.drawRoundedRect(cover, 8, 8)
            p.setPen(ui.TEXTE_2)
            p.setFont(ui.police_icones(15))
            p.drawText(cover, Qt.AlignCenter, ui.ICONES["note"])
        if not d["joue"]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(cover, 8, 8)
            p.setPen(ui.TEXTE)
            p.setFont(ui.police_icones(13))
            p.drawText(cover, Qt.AlignCenter, ui.ICONES["pause"])
        visible = min(1.0, max(0.0, (r.width() - CERCLE) / 80))
        if visible > 0:
            p.setClipRect(r)
            p.setOpacity(visible * (1.0 if d["joue"] else 0.6))
            droite = r.right() - 16
            p.setFont(ui.police(12, gras=True))
            ecoule = musique.minutes(d["position"])
            largeur_temps = max(p.fontMetrics().horizontalAdvance(ecoule),
                                QFontMetrics(ui.police(10)).horizontalAdvance(musique.minutes(d["duree"])))
            p.setPen(ui.TEXTE)
            p.drawText(QRectF(droite - largeur_temps, r.top() + 7, largeur_temps, 17), Qt.AlignRight | Qt.AlignVCenter, ecoule)
            if d["duree"] > 0:
                p.setPen(ui.TEXTE_3)
                p.setFont(ui.police(10))
                p.drawText(QRectF(droite - largeur_temps, r.top() + 23, largeur_temps, 15),
                           Qt.AlignRight | Qt.AlignVCenter, musique.minutes(d["duree"]))
            gauche = cover.right() + 10
            largeur = int(droite - largeur_temps - 12 - gauche)
            p.setPen(ui.TEXTE)
            p.setFont(ui.police(13, gras=True))
            titre = p.fontMetrics().elidedText(d["titre"], Qt.ElideRight, largeur)
            ligne_titre = QRectF(gauche, r.top() + 6, largeur, 19) if d["artiste"] else \
                QRectF(gauche, r.top(), largeur, r.height())          # pas d'artiste : titre centré
            p.drawText(ligne_titre, Qt.AlignLeft | Qt.AlignVCenter, titre)
            p.setPen(ui.TEXTE_3)
            p.setFont(ui.police(11))
            artiste = p.fontMetrics().elidedText(d["artiste"], Qt.ElideRight, largeur)
            p.drawText(QRectF(gauche, r.top() + 24, largeur, 16), Qt.AlignLeft | Qt.AlignVCenter, artiste)
        p.restore()

    def _maj_musique(self, d):
        avant = self._musique_visible()
        self._musique = d
        if d:
            if d["piste"] != self._piste_cover or (d["cover"] and self._pix_cover is None):
                self._piste_cover = d["piste"]
                pix = QPixmap()
                self._pix_cover = pix if d["cover"] and pix.loadFromData(d["cover"]) else None
            if d["joue"]:
                self._pause_depuis = None
            elif self._pause_depuis is None:
                self._pause_depuis = time.monotonic()
        if self.mode == "repos" and avant != self._musique_visible():
            self._morph()
        if self._geo and self.mode == "repos":
            self.update(self._geo["bornes"].toAlignedRect())

    def _dessiner_extras(self, p, c):
        """Les petits « z » quand Plop dort, les étincelles quand c'est réussi."""
        t = self.mascotte.t
        p.save()
        if self.mascotte.humeur() == "dort":
            for k in range(3):
                phase = (t * 0.33 + k / 3) % 1
                p.setPen(QColor(255, 255, 255, round(200 * math.sin(math.pi * phase))))
                p.setFont(ui.police(round(8 + 6 * phase), gras=True))
                p.drawText(QPointF(c.x() + 12 + 16 * phase, c.y() - 6 - 12 * phase), "z")
        dt = t - self._etincelles
        if 0 <= dt < 0.9:
            s = 5 * math.sin(math.pi * dt / 0.9)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 230))
            for angle in (-60, -15, 200, 245):
                a = math.radians(angle)
                d = 21 + dt * 12
                x, y = c.x() + d * math.cos(a), c.y() + d * math.sin(a)
                etoile = QPainterPath(QPointF(x, y - s))
                for px, py in ((0.22, -0.22), (1, 0), (0.22, 0.22), (0, 1), (-0.22, 0.22), (-1, 0), (-0.22, -0.22)):
                    etoile.lineTo(x + px * s, y + py * s)
                etoile.closeSubpath()
                p.drawPath(etoile)
        p.restore()

    def _dessiner_depot(self, p, r):
        ecart = abs(r.width() - self._cible.width()) + abs(r.height() - self._cible.height())
        visibilite = max(0.0, 1 - ecart / 50)
        if visibilite <= 0:
            return
        p.save()
        p.setOpacity(visibilite)
        a = ui.accent()
        zone = r.adjusted(9, 9, -9, -9)
        stylo = QPen(QColor(a.red(), a.green(), a.blue(), 150), 1.3)
        stylo.setDashPattern([4, 3])
        p.setPen(stylo)
        p.setBrush(QColor(a.red(), a.green(), a.blue(), 20))
        p.drawRoundedRect(zone, RAYON_MAX - 9, RAYON_MAX - 9)
        self.mascotte.dessiner(p, QPointF(zone.left() + 52, zone.center().y() + 1), 21)
        texte = QRectF(zone.left() + 100, zone.top(), zone.width() - 112, zone.height())
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(15, gras=True))
        p.drawText(texte.adjusted(0, 0, 0, -texte.height() / 2 + 4), Qt.AlignLeft | Qt.AlignBottom, "Miam ! Lâche-le ici")
        p.setPen(ui.TEXTE_3)
        p.setFont(ui.police(12))
        apercu = p.fontMetrics().elidedText(self._apercu, Qt.ElideMiddle, int(texte.width()))
        p.drawText(texte.adjusted(0, texte.height() / 2 + 4, 0, 0), Qt.AlignLeft | Qt.AlignTop, apercu)
        p.restore()

    # ================================================================ statut
    def _statut(self, texte, etat="repos", duree=0):
        self.statut, self.etat = texte, etat
        self._toast_telechargement = self._toast_cle = self._toast_capture = self._toast_rappel = False
        self._fin_toast.stop()
        if duree:
            self._fin_toast.start(duree)
        self.titre_disc.setText(texte or "Dropi")
        self._maj_titre_fichiers()
        if self.mode == "repos":
            self._morph()
        if self._geo:
            self.update(self._geo["bornes"].toAlignedRect())

    def _statut_repos(self):
        if not self.occupee:
            self._statut("")

    def _toast(self, texte, etat="succes"):
        texte = " ".join(texte.split())
        if etat == "succes":
            self._etincelles = self.mascotte.t
            self.mascotte.reagir("content", 1.2)
        elif etat == "erreur":
            self.mascotte.reagir("erreur", 1.6)
        self._statut(texte, etat, duree=5000 if etat == "erreur" else 4000)

    def _maj_titre_fichiers(self):
        if self.statut:
            self.titre_fich.setText(self.statut)
        elif self._origine == "telechargement":
            self.titre_fich.setText("Tu viens de télécharger ça. Je le range ?" if len(self.fichiers) == 1
                                    else f"{len(self.fichiers)} nouveaux téléchargements. Je les range ?")
        elif len(self.fichiers) > 1:
            self.titre_fich.setText(f"Qu'est-ce que je fais avec ces {len(self.fichiers)} fichiers ?")
        else:
            self.titre_fich.setText("Qu'est-ce que je fais avec ça ?")

    def _frappe(self):
        self._derniere_frappe = time.monotonic()
        self.mascotte.hocher()

    # ================================================================ souris : clic et glisser
    def _dans_forme(self, pos):
        return self._rect_forme().contains(QPointF(pos))

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self.mode == "survol" or not self._dans_forme(e.position()):
            return
        if self.mode in PANNEAUX and e.position().y() > self._rect_forme().top() + 46:
            return      # un panneau ouvert ne s'attrape que par son en-tête
        self._appui = e.position()

    def mouseMoveEvent(self, e):
        if self._appui is not None and not self._glisse \
                and (e.position() - self._appui).manhattanLength() > 6:
            self._debut_glisse(self._appui)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._appui is None:
            return
        self._appui = None
        if self._glisse:
            self._fin_glisse()
        elif self.mode == "repos" and not self._libre and self._toast_telechargement:
            self._ouvrir_proposes()
        elif self.mode == "repos" and not self._libre and self._toast_cle:
            self._clic_cle()
        elif self.mode == "repos" and not self._libre and self._toast_capture:
            self._annuler_capture()
        elif self.mode == "repos" and not self._libre and self._toast_rappel:
            self._statut("")                 # rappel vu
        elif self.mode == "repos" and self._musique_visible() and \
                self._rect_cover(self._rect_forme()).adjusted(-4, -4, 4, 4).contains(e.position()):
            musique.commander("pause")
            self.mascotte.sauter(0.4)
        elif self.mode == "repos" and not self._libre:
            self._aller("discussion")
            self._premier_plan()
            self.mascotte.sauter(0.6)

    def _debut_glisse(self, pos):
        rect = self._rect_forme()
        depart = rect.center()
        self._rouvrir = self.mode if self.mode in PANNEAUX else None
        self._decalage = QPointF(pos) - depart if self.mode == "repos" else QPointF(0, 0)
        self._glisse = self._libre = True
        self._cx.valeur, self._cy.valeur = depart.x(), depart.y()
        self._cx.cible, self._cy.cible = depart.x(), depart.y()
        self._cx.vitesse = self._cy.vitesse = 0.0
        self._col_bord = self.bord
        self._col_force.valeur = self._col_force.cible = 1.0
        if self.mode != "repos":
            self._aller("repos")
        else:
            self._morph()
        self.mascotte.reagir("surpris", 0.4)

    def _fin_glisse(self):
        """On lâche la goutte : elle file se coller au bord le plus proche."""
        self._glisse = False
        c = QPointF(self._cx.valeur, self._cy.valeur)
        ecran = QApplication.screenAt(QCursor.pos())
        if ecran is not None and ecran is not self.ecran:
            self._placer_sur_ecran(ecran)
            c = QPointF(self.mapFromGlobal(QCursor.pos()))
            self._cx.valeur, self._cy.valeur = c.x(), c.y()
            self._col_bord, self._col_force.valeur = None, 0.0
        distances = {"haut": c.y(), "bas": self.height() - c.y(), "gauche": c.x(), "droite": self.width() - c.x()}
        self.bord = min(distances, key=distances.get)
        if self.bord in ("haut", "bas"):
            self._fraction = c.x() / self.width()
        else:
            self._fraction = c.y() / self.height()
        cible = self._centre_ancre()
        self._cx.cible, self._cy.cible = cible.x(), cible.y()
        self._enregistrer_position()

    def _atterrir(self):
        self._libre = False
        self._etire = 0.0
        self._cx.vitesse = self._cy.vitesse = 0.0
        self._col_bord = None
        self._ecrase.vitesse += 2.0
        self.mascotte.reagir("content", 0.8)
        if self._rouvrir:
            mode, self._rouvrir = self._rouvrir, None
            if mode == "fichiers" and not self.fichiers:
                mode = "discussion"
            elif mode == "cle" and not self._cle:
                mode = "repos"
            self._aller(mode)
            self._premier_plan()
        else:
            self._morph()

    def _replacer(self):
        """Remet la goutte en haut au centre (elle y vole)."""
        self.fermer()
        depart = self._rect_forme().center()
        self._col_bord = self.bord
        self._col_force.valeur = self._col_force.cible = 1.0
        self._libre = True
        self._cx.valeur, self._cy.valeur = depart.x(), depart.y()
        self.bord, self._fraction = "haut", 0.5
        cible = self._centre_ancre()
        self._cx.cible, self._cy.cible = cible.x(), cible.y()
        self._enregistrer_position()

    def enterEvent(self, e):
        self._souris = True
        if self.mode == "repos":
            self._morph()

    def leaveEvent(self, e):
        self._souris = False
        if self.mode == "repos":
            self._morph()

    def contextMenuEvent(self, e):
        if not self._dans_forme(e.pos()):
            return
        menu = QMenu(self)
        if self._ia_en_cours:
            menu.addAction("Arrêter la demande en cours", self._arreter)
            menu.addSeparator()
        menu.addAction("Nouvelle conversation", self._reset)
        menu.addAction("Replacer en haut", self._replacer)
        menu.addAction("Lire du texte à l'écran", self._capturer_texte)
        menu.addSeparator()
        menu.addAction("Ce que j'ai appris", self._montrer_memoire)
        menu.addAction("Oublier ce que j'ai appris", self._oublier_memoire)
        menu.addSeparator()
        if self._cle:
            menu.addAction(f"Mot de passe pour {self._cle['hote']}…", self._ouvrir_cle)
        menu.addAction("Mes mots de passe (coffre Windows)", self._montrer_coffre)
        menu.addAction("Messagerie…", self._ouvrir_mail)
        auto =menu.addAction("Lancer au démarrage de Windows")
        auto.setCheckable(True)
        auto.setChecked(demarrage.est_active())
        auto.toggled.connect(lambda oui: demarrage.activer() if oui else demarrage.desactiver())
        menu.addSeparator()
        menu.addAction("Quitter", QApplication.quit)
        self._dialogue = True
        menu.exec(e.globalPos())
        self._dialogue = False

    def _montrer_memoire(self):
        d = memoire.tout()
        souvenirs = d["souvenirs"][-15:]
        lignes = [f"- {s['texte']}" for s in reversed(souvenirs)]
        habitudes = memoire.habitudes()
        texte = ("**Ce que j'ai appris** (" + str(len(d["souvenirs"])) + " souvenirs)\n\n" + "\n".join(lignes)) \
            if lignes else "Je n'ai encore rien appris. Pose-moi des questions, dis-moi ce que tu préfères : je retiens."
        if habitudes:
            texte += "\n\n**Tu lances souvent :** " + ", ".join(habitudes)
        self.fil.ia(texte)
        self._maj_accueil()
        self._aller("discussion")
        self._premier_plan()

    def _oublier_memoire(self):
        memoire.oublier_tout()
        self._toast("J'ai tout oublié.", "repos")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.fermer()

    def changeEvent(self, e):
        if (e.type() == QEvent.ActivationChange and not self.isActiveWindow()
                and not self._dialogue and self.mode in PANNEAUX):
            self.fermer()
        super().changeEvent(e)

    def _verifier_clic_exterieur(self):
        """Referme l'île si on clique ailleurs, même quand Windows ne lui a pas donné le focus."""
        if self._dialogue or sys.platform != "win32":
            return
        etat_touche = ctypes.windll.user32.GetAsyncKeyState
        etat_touche.restype = ctypes.c_short
        if (etat_touche(0x01) & 0x8000 or etat_touche(0x02) & 0x8000) \
                and not self._dans_forme(self.mapFromGlobal(QCursor.pos())):
            self.fermer()

    def _premier_plan(self):
        """Passe devant et prend le clavier (Windows refuse souvent, d'où l'astuce AttachThreadInput)."""
        self.raise_()
        self.activateWindow()
        if sys.platform != "win32":
            return
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        u32.GetForegroundWindow.restype = wintypes.HWND
        u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        u32.SetForegroundWindow.argtypes = [wintypes.HWND]
        moi = int(self.winId())
        devant = u32.GetForegroundWindow()
        if not devant or devant == moi:
            return
        fil_devant, mon_fil = u32.GetWindowThreadProcessId(devant, None), k32.GetCurrentThreadId()
        u32.AttachThreadInput(mon_fil, fil_devant, True)
        u32.SetForegroundWindow(moi)
        u32.AttachThreadInput(mon_fil, fil_devant, False)
        self.activateWindow()

    def fermer(self):
        if self.mode == "repos":
            return
        self.fichiers = []
        self._origine = "depot"
        self._aller("repos")

    # ---------------------------------------------------------------- glisser-déposer de fichiers
    @staticmethod
    def _chemins(mime):
        return [str(Path(u.toLocalFile())) for u in mime.urls() if u.isLocalFile() and u.toLocalFile()]

    @staticmethod
    def _accepter_copie(e):
        # Toujours « copier » : si on répond « déplacer », l'explorateur pourrait effacer l'original.
        if e.possibleActions() & Qt.CopyAction:
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.acceptProposedAction()

    def dragEnterEvent(self, e):
        chemins = self._chemins(e.mimeData())
        if not chemins or self.occupee or self._libre:
            e.ignore()
            return
        self._accepter_copie(e)
        if self.mode != "survol":
            self._mode_avant = self.mode
        self._apercu = Path(chemins[0]).name if len(chemins) == 1 else f"{len(chemins)} fichiers"
        self._aller("survol")

    def dragMoveEvent(self, e):
        self._accepter_copie(e)

    def dragLeaveEvent(self, e):
        if self.mode == "survol":
            self._aller(self._mode_avant)

    def dropEvent(self, e):
        self._accepter_copie(e)
        if self._mode_avant != "fichiers":
            self._origine = "depot"
        for c in self._chemins(e.mimeData()):
            if c not in self.fichiers:
                self.fichiers.append(c)
        self._maj_fichiers()
        self._aller("fichiers")
        self.mascotte.reagir("miam", 0.9)
        QTimer.singleShot(80, self._premier_plan)

    # ---------------------------------------------------------------- fichiers déposés
    def _maj_fichiers(self):
        while self.liste.count():
            w = self.liste.takeAt(0).widget()
            if w:
                w.deleteLater()
        lieux = []
        for c in self.fichiers:
            try:
                lieux.append(classement.court_pour(c))
            except OSError:
                lieux.append("")
        for c, lieu in list(zip(self.fichiers, lieux))[:FICHIERS_VISIBLES]:
            ligne = ui.LigneFichier(c, lieu)
            ligne.retire.connect(self._retirer_fichier)
            self.liste.addWidget(ligne)
        self.proposition.montrer([l for l in lieux if l] or ["Classement"])
        reste = len(self.fichiers) - FICHIERS_VISIBLES
        self.autres.setVisible(reste > 0)
        self.autres.setText(f"+ {reste} autre{'s' if reste > 1 else ''}")
        self._annuler_suppr()
        self.btn_resume.setVisible(any(Path(c).suffix.lower() in tools.RESUMABLES for c in self.fichiers))
        self._maj_titre_fichiers()

    def _resumer(self):
        """Le bouton « Résumer » : l'IA lit les documents déposés (PDF, Word, texte) et en fait un résumé."""
        documents = [c for c in self.fichiers if Path(c).suffix.lower() in tools.RESUMABLES][:3]
        if not documents or self.occupee:
            return
        self.fermer()
        self.envoyer("Résume ce document" if len(documents) == 1 else "Résume ces documents", documents, resume=True)

    def _retirer_fichier(self, chemin):
        self.fichiers.remove(chemin)
        if not self.fichiers:
            self.fermer()
            return
        self._maj_fichiers()
        self._morph()

    @staticmethod
    def _noms(fichiers):
        noms = ", ".join(Path(c).name for c in fichiers[:3])
        return noms + (f" +{len(fichiers) - 3}" if len(fichiers) > 3 else "")

    def _pour_fichiers(self, consigne):
        """Envoie les fichiers déposés à l'IA avec ce qu'il faut en faire."""
        consigne = consigne.strip()
        if not consigne or not self.fichiers or self.occupee:
            return
        fichiers = list(self.fichiers)
        self.champ_fich.clear()
        self.fermer()
        self.envoyer(consigne, fichiers)

    def _action_directe(self, quoi, destination=None):
        """Actions immédiates, sans passer par l'IA."""
        if not self.fichiers or self.occupee:
            return
        fichiers = list(self.fichiers)
        if quoi == "afficher":
            fichiers = fichiers[:1]
        n = len(fichiers)
        actions = {
            "ouvrir": (tools.ouvrir_fichier, "Ouvrir", "J'ouvre", f"{n} fichiers ouverts"),
            "supprimer": (tools.supprimer_fichier, "Supprimer", "Je mets à la corbeille",
                          f"{n} fichiers à la corbeille"),
            "afficher": (tools.afficher_dans_explorateur, "Afficher dans l'explorateur", "J'ouvre l'explorateur", ""),
            "deplacer": (lambda c: tools.deplacer_fichier(c, destination),
                         f"Déplacer vers {destination}", "Je déplace", f"{n} fichiers déplacés"),
            "ranger": (tools.ranger_fichier, "Range-les à leur place", "Je range", f"{n} fichiers rangés"),
            "bureau": (lambda c: tools.deplacer_fichier(c, "~/Desktop"), "Mets-les sur le Bureau",
                       "Je les mets sur le Bureau", f"{n} fichiers sur le Bureau"),
        }
        fonction, demande, en_cours, pluriel = actions[quoi]
        self.fermer()
        self.fil.moi(demande, piece=self._noms(fichiers))
        self._maj_accueil()
        self.occupee = True
        self._statut(en_cours + "…", "travail")

        def travail():
            resultats = []
            for c in fichiers:
                try:
                    resultats.append(str(fonction(c)))
                except Exception as ex:
                    resultats.append(f"Erreur : {ex}")
            resume = resultats[0] if len(resultats) == 1 else pluriel
            self.pont.direct.emit(resume, resultats, f"{demande} : " + "\n".join(fichiers), fichiers)

        threading.Thread(target=travail, daemon=True).start()

    def _fin_directe(self, resume, resultats, demande, fichiers):
        self.occupee = False
        self.cerveau.noter(demande, "\n".join(resultats))
        erreurs = [r for r in resultats if est_erreur(r)]
        for i, (r, c) in enumerate(zip(resultats, fichiers)):
            if i == 6 and len(resultats) > 7:
                self.fil.action(f"… et {len(resultats) - 6} autres").terminer(True)
                break
            self.fil.action(sans_chemin(r), self._clic_dossier(c)).terminer(not est_erreur(r))
        resume = sans_chemin(resume)
        if erreurs:
            self._toast(erreurs[0] if len(erreurs) == 1 else f"{len(erreurs)} erreurs", "erreur")
        else:
            self._toast(resume, "succes")

    def _deplacer(self):
        self._dialogue = True
        dossier = QFileDialog.getExistingDirectory(self, "Déplacer vers…", str(Path.home()))
        self._dialogue = False
        if dossier:
            self._action_directe("deplacer", str(Path(dossier)))
        else:
            self._premier_plan()

    def _supprimer(self):
        if not self.btn_suppr.danger:
            self.btn_suppr.danger = True
            self.btn_suppr.setText("Confirmer ?")
            self.btn_suppr.updateGeometry()
            QTimer.singleShot(3500, self._annuler_suppr)
            return
        self._annuler_suppr()
        self._action_directe("supprimer")

    def _annuler_suppr(self):
        self.btn_suppr.danger = False
        self.btn_suppr.setText("Supprimer")
        self.btn_suppr.updateGeometry()
        self.btn_suppr.update()

    # ================================================================ jeux
    def _grille_jeux(self):
        grille = ui.GrilleJeux(tools.catalogue_jeux())
        grille.lancer.connect(self._lancer_jeu)
        self.fil.carte(grille)
        self._maj_accueil()
        self.mascotte.reagir("content", 1.0)

    def _mes_jeux(self):
        self.fil.moi("Montre-moi mes jeux")
        self._grille_jeux()
        self.cerveau.noter("Quels jeux j'ai ?", tools.lister_jeux())

    def _lancer_jeu(self, nom):
        jeu = tools.trouver_jeu(nom)
        resultat = tools.lancer_jeu(nom)
        self.cerveau.noter(f"Lance {nom}", resultat)
        if jeu and not est_erreur(resultat):
            self.fil.carte(ui.CarteLancement(jeu))
        self.fermer()
        self._toast(resultat, "erreur" if est_erreur(resultat) else "succes")

    # ================================================================ rangement et téléchargements
    def _clic_dossier(self, chemin):
        """Action pour une pastille : ouvre l'explorateur là où le fichier se trouve maintenant."""
        def ouvrir():
            actuel = classement.retrouver(chemin)
            if actuel.exists():
                tools.afficher_dans_explorateur(str(actuel))
        return ouvrir

    def _ranger_telechargements(self):
        if self.occupee:
            return
        fichiers = [str(p) for p in tools.fichiers_telechargements()]
        if not fichiers:
            self.fil.moi("Range mes téléchargements")
            self.fil.ia("Tes téléchargements sont déjà rangés.")
            self._maj_accueil()
            return
        self.fichiers = fichiers
        self._action_directe("ranger")

    def _verifier_plein_ecran(self):
        plein = plein_ecran_actif(int(self.winId()))
        if plein and not self._cachee_plein_ecran and self.mode == "repos" and not self._libre and not self._glisse:
            self._cachee_plein_ecran = True
            self._horloge.stop()
            self.hide()
        elif not plein and self._cachee_plein_ecran:
            self._cachee_plein_ecran = False
            self.show()
            self._horloge.start()

    def _verifier_telechargements(self):
        """Toutes les 2 s : un nouveau fichier dans Téléchargements dont la taille ne bouge plus = fini."""
        try:
            actuels = {str(p): p for p in tools.fichiers_telechargements()}
        except OSError:
            return
        remis = {e["apres"] for e in classement.derniers(20)}      # ceux qu'on vient d'y remettre soi-même
        for chemin, p in actuels.items():
            if chemin in self._connus or chemin in remis:
                continue
            try:
                taille = p.stat().st_size
            except OSError:
                continue
            if taille > 0 and self._tailles_en_cours.get(chemin) == taille:
                self._connus.add(chemin)
                self._tailles_en_cours.pop(chemin, None)
                self._nouveau_telechargement(chemin)
            else:
                self._tailles_en_cours[chemin] = taille
        self._connus &= set(actuels)

    def _nouveau_telechargement(self, chemin):
        try:
            lieu = classement.court_pour(chemin)
        except OSError:
            return
        nom = Path(chemin).name
        if self._mode_telechargements == "auto":
            QTimer.singleShot(10000, lambda: self._ranger_tout_seul(chemin))
            return
        self._proposes.append(chemin)
        self.mascotte.reagir("curieux", 3.0)
        if self._mode_telechargements == "ouvrir" and not self.occupee and not self._cachee_plein_ecran:
            if self.mode == "repos":
                self._ouvrir_proposes(clavier=False)         # le panneau s'ouvre tout seul, sans voler le clavier
                return
            if self.mode == "fichiers" and self._origine == "telechargement":
                self._proposes = []                          # un deuxième téléchargement : il s'ajoute au panneau
                if chemin not in self.fichiers:
                    self.fichiers.append(chemin)
                    self._maj_fichiers()
                return
        if self.mode == "repos" and not self.occupee:
            self._statut(f"Nouveau : {nom}  →  {lieu}", "repos", duree=15000)
            self._toast_telechargement = True
            self.mascotte.sauter(0.7)
        else:
            self.fil.action(f"Nouveau téléchargement : {nom}  →  {lieu} (clique pour ranger)",
                            self._ouvrir_proposes)

    def _ouvrir_proposes(self, clavier=True):
        fichiers = [c for c in self._proposes if Path(c).exists()]
        self._proposes = []
        self._toast_telechargement = False
        if not fichiers:
            return
        self._statut("")
        self.fichiers = fichiers
        self._origine = "telechargement"
        self._maj_fichiers()
        self._aller("fichiers")
        if clavier:
            self._premier_plan()

    def _ranger_tout_seul(self, chemin, essai=1):
        """Mode auto : range le téléchargement 10 s après la fin, un fichier à la fois. Si l'île est occupée ou si le
        fichier est encore ouvert (un lecteur PDF le verrouille), on réessaie un peu plus tard."""
        if not Path(chemin).exists():
            return
        resultat = None if self.occupee else tools.ranger_fichier(chemin)
        if resultat is None or est_erreur(resultat):
            if essai < 6:
                QTimer.singleShot(15000, lambda: self._ranger_tout_seul(chemin, essai + 1))
            return
        self.cerveau.noter(f"Range le téléchargement {chemin}", resultat)
        lieu = classement.court(classement.retrouver(chemin).parent)
        self.fil.action(f"{Path(chemin).name} rangé dans {lieu}", self._clic_dossier(chemin)).terminer(True)
        self._maj_accueil()
        if self.mode == "repos":
            self._toast(f"Rangé : {Path(chemin).name}  →  {lieu}", "succes")

    # ================================================================ mots de passe
    def _champ_mdp(self, champ):
        """Le guetteur signale un champ mot de passe sous le clavier (None quand on l'a quitté)."""
        self._cle = champ
        if champ is None:
            if self.mode == "cle":
                self.fermer()
            elif self._toast_cle:
                self._statut("")
            return
        if champ["numero"] == self._cle_faite or self.mode != "repos" or self.occupee or self._libre:
            return
        comptes = coffre.comptes(champ["hote"])
        if len(comptes) == 1:
            texte = f"Clique pour remplir {comptes[0]}" if comptes[0] else f"Clique pour remplir {champ['hote']}"
        elif comptes:
            texte = f"{len(comptes)} comptes pour {champ['hote']} : clique pour choisir"
        else:
            texte = f"Mot de passe pour {champ['hote']} ? Clique"
        self._statut(texte, "repos")
        self._toast_cle = True
        self.mascotte.reagir("curieux", 2.0)

    def _clic_cle(self):
        if not self._cle:
            return
        comptes = coffre.comptes(self._cle["hote"])
        if len(comptes) == 1:
            self._remplir(comptes[0])
        else:
            self._ouvrir_cle()

    def _ouvrir_cle(self):
        """Le panneau : les comptes connus pour ce site, et de quoi en enregistrer un nouveau."""
        if not self._cle:
            return
        hote = self._cle["hote"]
        comptes = coffre.comptes(hote)
        self._statut("")
        self.titre_cle.setText(f"Mot de passe pour {hote}")
        while self.comptes_cle.count():
            w = self.comptes_cle.takeAt(0).widget()
            if w:
                w.deleteLater()
        for login in comptes[:4]:
            bouton = ui.Bouton("cle", login or "Sans identifiant", "puce", info="Remplir avec ce compte")
            bouton.clicked.connect(lambda _=False, l=login: self._remplir(l))
            self.comptes_cle.addWidget(bouton)
        self.chapeau_cle.setText("Un autre compte, ou un nouveau mot de passe :" if comptes
                                 else "Je ne connais pas encore ce site. Je retiens :")
        self.champ_login.setText(self._cle["login"])
        self.champ_passe.setText(coffre.generer(self._longueur_mdp))
        self._aller("cle")
        self._premier_plan()

    def _enregistrer_cle(self):
        login, mdp = self.champ_login.text().strip(), self.champ_passe.text()
        if not self._cle or not mdp:
            return
        try:
            coffre.enregistrer(self._cle["hote"], login, mdp)
        except OSError:
            self._toast("Windows a refusé d'enregistrer ce mot de passe.", "erreur")
            return
        self._remplir(login)

    def _remplir(self, login):
        if not self._cle:
            return
        mdp = coffre.lire(self._cle["hote"], login)
        if mdp is None:
            self._toast("Je n'ai plus ce mot de passe.", "erreur")
            return
        if self.mode == "cle":
            self._aller("repos")
        self._statut("")
        guetteur.remplir(self._cle["numero"], login, mdp)

    def _fin_remplissage(self, ok, message):
        if not ok:
            self._toast(message, "erreur")
            return
        self._cle_faite = self._cle["numero"] if self._cle else None    # ne pas le reproposer dans la foulée
        self._toast(f"Rempli pour {message}", "succes")

    # ================================================================ messagerie
    def _mails(self):
        """La tuile de l'accueil : les mails importants si la boîte est connectée (liste immédiate, sans l'IA),
        sinon le panneau pour la connecter."""
        if messagerie.compte():
            self._ordre_direct("Mes mails importants", ("outil", "mails_recents", {"nombre": 8, "importants": True}))
        else:
            self._ouvrir_mail()

    def _maj_tuile_mail(self):
        self._tuiles["_mails"].setText("Mes mails importants" if messagerie.compte() else "Connecter mes mails")

    def _etat_mail(self, texte, erreur=False):
        pal = self.etat_mail.palette()
        pal.setColor(pal.ColorRole.WindowText, ui.ERREUR if erreur else ui.TEXTE_2)
        self.etat_mail.setPalette(pal)
        self.etat_mail.setText(texte)
        self.etat_mail.setFixedHeight(self.etat_mail.heightForWidth(self.etat_mail.width()) if texte else 0)
        if self.mode == "mail":
            self._morph()

    def _ouvrir_mail(self):
        fiche = messagerie.compte()
        self._serveur_saisi = False
        self.champ_adresse.setText(fiche["adresse"] if fiche else "")
        self.champ_serveur.setText(fiche["serveur"] if fiche else "")
        self.btn_deconnecter.setVisible(bool(fiche))
        self._maj_aide_mail(f"Connectée : {fiche['adresse']}. Pour changer de boîte, remplis ci-dessous." if fiche else "")
        self._statut("")
        self._aller("mail")
        self._premier_plan()

    def _maj_aide_mail(self, etat=""):
        serveur, aide, possible = messagerie.fournisseur(self.champ_adresse.text())
        if not self._serveur_saisi:
            self.champ_serveur.setText(serveur)
        self.aide_mail.setText(aide or "Tape ton adresse : je reconnais Orange, Gmail, Free, SFR, La Poste, Bouygues, "
                               "Yahoo, iCloud… et je cherche le serveur des autres.")
        self.btn_connecter.setEnabled(possible)
        self._etat_mail(etat)

    def _connecter_mail(self):
        if self.occupee or not self.btn_connecter.isEnabled():
            return
        adresse, mdp, serveur = self.champ_adresse.text(), self.champ_mdp_mail.text(), self.champ_serveur.text()
        self.occupee = True
        self._etat_mail("Je vérifie la connexion…")
        self.mascotte.reagir("reflechit", 20)

        def travail():
            try:
                self.pont.mail.emit(messagerie.connecter(adresse, mdp, serveur))
            except Exception as ex:
                self.pont.mail.emit(f"Connexion impossible : {ex}")

        threading.Thread(target=travail, daemon=True).start()

    def _fin_mail(self, erreur):
        self.occupee = False
        if erreur:
            self.mascotte.reagir("erreur", 1.8)
            self._etat_mail(erreur, erreur=True)
            return
        self._maj_tuile_mail()
        if self.mode == "mail":
            self._aller("repos")
        self.mascotte.reagir("eureka", 1.6)
        self._toast("Messagerie connectée", "succes")

    def _deconnecter_mail(self):
        messagerie.deconnecter()
        self._maj_tuile_mail()
        self.champ_adresse.clear()
        self.btn_deconnecter.hide()
        self._serveur_saisi = False
        self._maj_aide_mail("Messagerie déconnectée : son mot de passe est effacé du coffre.")

    def _message_extension(self, message):
        """L'extension du navigateur a vu une connexion : on retient le mot de passe s'il est nouveau."""
        if message.get("type") != "connexion":
            return {"ok": False}
        hote = guetteur.hote_de(str(message.get("url") or ""))
        login, mdp = str(message.get("login") or "").strip()[:200], str(message.get("mdp") or "")
        if not hote or not mdp or len(mdp) > 500:
            return {"ok": True, "etat": "ignore"}
        comptes = coffre.comptes(hote)
        if not login and len(comptes) == 1:
            login = comptes[0]               # identifiant pas vu dans la page : c'est le seul compte connu ici
        ancien = coffre.lire(hote, login)
        if ancien == mdp:
            return {"ok": True, "etat": "connu"}
        try:
            coffre.enregistrer(hote, login, mdp)
        except OSError:
            return {"ok": False}
        self._capture = (hote, login, ancien)
        if self.mode == "repos" and not self.occupee and not self._libre:
            verbe = "mis à jour" if ancien is not None else "enregistré"
            self._statut(f"Mot de passe {verbe} pour {hote}  ·  clique pour annuler", "repos", duree=8000)
            self._toast_capture = True
            self.mascotte.reagir("content", 1.2)
        return {"ok": True, "etat": "enregistre"}

    def _annuler_capture(self):
        if not self._capture:
            return
        (hote, login, ancien), self._capture = self._capture, None
        if ancien is None:
            coffre.supprimer(hote, login)
        else:
            coffre.enregistrer(hote, login, ancien)
        self._toast(f"Annulé pour {hote}", "repos")

    def _copier_cle(self):
        mdp = self.champ_passe.text()
        if not mdp:
            return
        contenu = QMimeData()
        contenu.setText(mdp)
        # demande à Windows de ne pas le garder dans l'historique du presse-papiers (Win + V) ni de le synchroniser
        contenu.setData('application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"', b"\x01")
        presse_papiers = QApplication.clipboard()
        presse_papiers.setMimeData(contenu)
        QTimer.singleShot(30000, lambda: presse_papiers.text() == mdp and presse_papiers.clear())
        self.mascotte.sauter(0.4)

    @staticmethod
    def _montrer_coffre():
        """Ouvre le Gestionnaire d'identifiants de Windows : les entrées « Dropi/… » s'y voient et s'y suppriment."""
        os.startfile("control.exe", arguments="/name Microsoft.CredentialManager")

    # ================================================================ faire de la place
    def _faire_de_la_place(self):
        if self.occupee:
            return
        self.fil.moi("Fais-moi de la place")
        self._maj_accueil()
        self.occupee = True
        self._statut("J'analyse ton disque…", "travail")

        def travail():
            menage.analyser()
            self.pont.analyse.emit()

        threading.Thread(target=travail, daemon=True).start()

    def _carte_menage(self):
        self.occupee = False
        if menage.derniere_analyse is None:
            return
        carte = ui.CarteMenage(menage.derniere_analyse)
        carte.nettoyer.connect(self._nettoyer)
        carte.vider.connect(self._vider_corbeille)
        self._carte_nettoyage = carte
        self.fil.carte(carte)
        self._maj_accueil()
        self._statut("")
        if self.mode != "discussion":
            self._aller("discussion")

    def _nettoyer(self, categories):
        self._statut("Je fais le ménage…", "travail")

        def travail():
            liberes, nombre, erreurs = menage.nettoyer(categories)
            self.pont.menage.emit(float(liberes), nombre, erreurs, "nettoyage")

        threading.Thread(target=travail, daemon=True).start()

    def _vider_corbeille(self):
        self._statut("Je vide la corbeille…", "travail")

        def travail():
            try:
                liberes = menage.vider_corbeille()
                self.pont.menage.emit(float(liberes), 0, 0, "corbeille")
            except OSError:
                self.pont.menage.emit(0.0, 0, 1, "corbeille")

        threading.Thread(target=travail, daemon=True).start()

    def _menage_fini(self, liberes, nombre, erreurs, quoi):
        taille = menage.taille_lisible(liberes)
        if quoi == "corbeille":
            message = f"Corbeille vidée : {taille} libérés pour de bon."
        else:
            message = f"{nombre} fichiers supprimés ou mis à la corbeille ({taille})."
            if erreurs:
                message += f" {erreurs} étaient utilisés par une appli, je les ai laissés."
            self.cerveau.noter("Fais-moi de la place", message)
        if self._carte_nettoyage is not None:
            self._carte_nettoyage.termine(liberes, menage.disque(), menage.corbeille()[0], message)
        self._toast(message, "succes")

    # ================================================================ discussion avec l'IA
    def _maj_accueil(self):
        vide = self.fil.vide()
        self.accueil.setVisible(vide)
        self.fil.setVisible(not vide)

    def envoyer(self, texte, fichiers=None, resume=False):
        texte = texte.strip()
        if self.occupee or not texte:
            return
        ordre = None if fichiers else ordres.reconnaitre(texte)
        if ordre:
            self._ordre_direct(texte, ordre)
            return
        if fichiers:
            requete = "Fichiers :\n" + "\n".join(fichiers) + f"\n\nConsigne : {texte}"
            self.fil.moi(texte, piece=self._noms(fichiers))
        else:
            requete = texte
            self.fil.moi(texte)
        self._maj_accueil()
        self.champ.clear()
        self._actions = []
        self.occupee = True
        self._ia(True)
        self._statut("Je réfléchis…", "travail")
        self.fil.attente()

        def resumer():
            """Un résumé par document ; avec plusieurs, ils s'écrivent l'un sous l'autre."""
            deja = []
            for c in fichiers:
                titre = f"**{Path(c).name}**\n" if len(fichiers) > 1 else ""
                try:
                    avant = "\n\n".join(deja) + ("\n\n" if deja else "")
                    rep = self.cerveau.resumer(c, lambda t: self.pont.partiel.emit(avant + titre + t))
                except ValueError as ex:
                    rep = str(ex)
                deja.append(titre + rep)
            return "\n\n".join(deja)

        def travail():
            try:
                if resume:
                    rep = resumer()
                else:
                    rep = self.cerveau.demander(
                        requete,
                        sur_action=lambda nom, args: self.pont.action.emit(decrire_action(nom, args)),
                        sur_resultat=lambda nom, args, res: self.pont.resultat.emit(nom, args, not est_erreur(res)),
                        sur_texte=self.pont.partiel.emit)
                self.pont.reponse.emit(rep, False)
            except Arrete:
                self.pont.reponse.emit("Demande arrêtée.", False)
            except Exception as ex:
                self.pont.reponse.emit(f"Oups : {ex}. Le moteur d'IA a un souci ? (réessaie, il redémarre tout seul)", True)

        threading.Thread(target=travail, daemon=True).start()

    def _ia(self, en_cours):
        """L'IA travaille (ou a fini) : le bouton d'envoi devient un carré « arrêter » (ou redevient une flèche)."""
        self._ia_en_cours = en_cours
        self.btn_envoyer.icone = ui.ICONES["arreter" if en_cours else "envoyer"]
        self.btn_envoyer.setToolTip("Arrêter la demande" if en_cours else "Envoyer")
        self.btn_envoyer.update()

    def _etat_moteur(self, texte):
        """Téléchargement du modèle (premier lancement) ou chargement de l'IA : on le montre sur la goutte."""
        if texte:
            self._statut(texte, "travail")
        elif not self.occupee:
            self._statut("")

    def _texte_partiel(self, texte):
        """La réponse s'écrit sous nos yeux, au fil de ce que le modèle produit."""
        if not self._ia_en_cours:
            return
        if self._vivant is None:
            self._vivant = self.fil.ia(texte, ecrire=True)
            self._maj_accueil()
        else:
            self._vivant.ecrire(texte)
        if self.mode == "repos":
            self._statut(" ".join(re.sub(r"[*_`#]", "", texte).split()), "travail")

    def _arreter(self):
        if not self._ia_en_cours:
            return
        self._statut("J'arrête…", "travail")
        self.cerveau.arreter()

    # ---------------------------------------------------------------- ordres directs (sans l'IA)
    def _ordre_direct(self, texte, ordre):
        """Une demande simple reconnue par ordres.py : on la fait tout de suite."""
        self.champ.clear()
        if ordre[0] == "ile":                # ces actions écrivent elles-mêmes dans le fil
            getattr(self, ordre[1])()
            return
        self.fil.moi(texte)
        self._maj_accueil()
        if ordre[0] == "rappel":
            fiche = ordre[1]
            rappels.ajouter(fiche["quand"], fiche["texte"], fiche["genre"])
            resultat = f"{fiche['texte']} lancé." if fiche["genre"] == "minuteur" \
                else f"Rappel {rappels.quand_lisible(fiche['quand'])} : {fiche['texte']}"
            self._actions = [resultat]
            self.cerveau.noter(texte, resultat)
            self._verifier_rappels()
            self._reponse(resultat, False)
            return
        nom, args = ordre[1], ordre[2]
        self._actions = [decrire_action(nom, args)]
        self.fil.action(self._actions[0])
        self.occupee = True
        self._statut(self._actions[0] + "…", "travail")

        def travail():
            try:
                resultat = str(tools.FONCTIONS[nom](**args))
            except Exception as ex:
                resultat = f"Erreur : {ex}"
            self.pont.instant.emit(texte, nom, args, resultat)

        threading.Thread(target=travail, daemon=True).start()

    def _fin_instant(self, texte, nom, args, resultat):
        ok = not est_erreur(resultat)
        self._resultat_ia(nom, args, ok)
        memoire.noter_usage(nom, args)
        self.cerveau.noter(texte, resultat)
        self._verifier_rappels()
        self._reponse(sans_chemin(resultat), not ok)

    # ---------------------------------------------------------------- rappels et minuteurs
    def _verifier_rappels(self):
        """Chaque seconde : fait sonner ce qui est échu, et tient le compte à rebours du minuteur."""
        for fiche in rappels.echus():
            self._sonner(fiche)
        minuteurs = [f["quand"] for f in rappels.a_venir() if f["genre"] == "minuteur"]
        avant, self._minuteur_fin = self._minuteur_fin, min(minuteurs) if minuteurs else None
        if self.mode != "repos" or self.statut:
            return
        if (avant is None) != (self._minuteur_fin is None):
            self._morph()
        elif self._minuteur_fin and self._geo:
            self.update(self._geo["bornes"].toAlignedRect())

    def _sonner(self, fiche):
        retard = time.time() - fiche["quand"]
        if fiche["genre"] == "minuteur":
            message = f"{fiche['texte']} : terminé !"
        else:
            prevu = time.strftime(" (prévu à %Hh%M)", time.localtime(fiche["quand"])) if retard > 120 else ""
            message = f"Rappel : {fiche['texte']}{prevu}"
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        self.fil.action(message).terminer(True)
        self._maj_accueil()
        self.mascotte.reagir("alerte", 2.5)
        if self._cachee_plein_ecran:         # même en plein écran, un rappel se montre
            self._cachee_plein_ecran = False
            self.show()
            self._horloge.start()
        if self.mode == "repos" and not self.occupee:
            self._etincelles = self.mascotte.t
            self._statut(message, "succes", duree=60000)
            self._toast_rappel = True

    # ---------------------------------------------------------------- lire du texte à l'écran
    def _capturer_texte(self):
        """On trace un cadre sur l'écran : le texte qu'il contient est lu et copié."""
        if self.occupee or self._selection:
            return
        self.fermer()
        QTimer.singleShot(450, self._choisir_zone)      # le temps que le panneau se referme : il ne sera pas sur l'image

    def _choisir_zone(self):
        ecran = QApplication.screenAt(QCursor.pos()) or self.ecran
        self._selection = ui.Selection(ecran)
        self._selection.choisie.connect(self._lire_zone)
        self._selection.destroyed.connect(lambda: setattr(self, "_selection", None))
        self._selection.show()
        self._selection.activateWindow()
        self._selection.setFocus()

    def _lire_zone(self, pixmap):
        image = pixmap.toImage()
        if image.height() < 900 and image.width() < 2400:      # les petits caractères se lisent mieux agrandis
            image = image.scaled(image.width() * 2, image.height() * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        tampon = QBuffer()
        tampon.open(QBuffer.WriteOnly)
        image.save(tampon, "PNG")
        png = bytes(tampon.data())
        self.occupee = True
        self._statut("Je lis le texte…", "travail")

        def travail():
            try:
                self.pont.texte_lu.emit(ocr.lire(png), "")
            except Exception as ex:
                self.pont.texte_lu.emit("", str(ex) or "inconnue")

        threading.Thread(target=travail, daemon=True).start()

    def _texte_lu(self, texte, erreur):
        self.occupee = False
        texte = texte.strip()
        if erreur:
            self._toast("Lecture impossible : " + erreur, "erreur")
            return
        if not texte:
            self._toast("Je n'ai pas trouvé de texte dans ce cadre", "repos")
            return
        self._copier(texte)
        self.fil.action("Texte lu à l'écran, copié dans le presse-papiers").terminer(True)
        self.fil.ia("```\n" + (texte if len(texte) <= 1500 else texte[:1500] + "\n…") + "\n```")
        self._maj_accueil()
        self.cerveau.noter("Voici un texte que je viens de capturer à l'écran :\n" + texte[:3000],
                           "Bien reçu, il est copié dans le presse-papiers.")
        self._toast(f"Texte copié ({len(texte)} caractères)", "succes")

    @staticmethod
    def _copier(texte):
        QApplication.clipboard().setText(texte)

    def _action_ia(self, texte):
        self._actions.append(texte)
        self.fil.action(texte)
        self._statut(texte + "…", "travail")

    def _resultat_ia(self, nom, args, ok):
        if self.fil.derniere_puce:
            self.fil.derniere_puce.terminer(ok)
        if self._ia_en_cours:
            self.fil.attente()               # l'IA relit le résultat de l'outil avant de répondre
        if not ok:
            return
        if nom == "lister_jeux":
            self._grille_jeux()
            if self.mode != "discussion":
                self._aller("discussion")
        elif nom == "lancer_jeu":
            jeu = tools.trouver_jeu(str(args.get("nom", "")))
            if jeu:
                self.fil.carte(ui.CarteLancement(jeu))
        elif nom == "analyser_espace":
            self._carte_menage()
            self.occupee = True               # l'IA n'a pas encore fini de répondre
        elif nom in ("ranger_fichier", "deplacer_fichier", "renommer_fichier") and self.fil.derniere_puce:
            puce = self.fil.derniere_puce
            puce.sur_clic = self._clic_dossier(str(args.get("chemin", "")))
            puce.setCursor(Qt.PointingHandCursor)

    def _reponse(self, rep, erreur):
        """Une action faite : juste une confirmation dans la bulle. Une vraie réponse : on l'affiche."""
        self.occupee = False
        trouve = self._ia_en_cours and not erreur and rep != "Demande arrêtée."
        self._ia(False)
        if trouve:                           # l'IA a trouvé : l'ampoule s'allume (après le reste, voir plus bas)
            QTimer.singleShot(0, lambda: self.mascotte.reagir("eureka", 1.8))
        vivant, self._vivant = self._vivant, None
        self.fil.fin_attente()
        if erreur:
            self.fil.erreur(rep)
        elif vivant is not None:
            vivant.ecrire(rep)               # la fin du texte finit de s'écrire, puis prend sa forme finale
        else:
            self.fil.ia(rep, ecrire=len(rep) > 60)
        self._maj_accueil()
        if self.mode == "discussion":
            self._statut("")
            self.mascotte.sauter(0.5)
        elif erreur:
            self._toast(rep, "erreur")
        elif len(rep) <= 70:
            self._toast(rep, "succes" if self._actions else "repos")
        else:
            self._statut("")
            self._aller("discussion")

    def _reset(self):
        self._vivant = None
        self.cerveau.oublier()
        self.fil.effacer()
        self._maj_accueil()
        self._statut_repos()

    # ---------------------------------------------------------------- micro
    def _micro_debut(self):
        if self.occupee:
            return
        try:
            self.micro.demarrer()
            self._statut("Je t'écoute…", "ecoute")
        except Exception as ex:
            self._toast(f"Micro indisponible : {ex}", "erreur")

    def _micro_fin(self):
        if self.etat != "ecoute":
            return
        self._statut("Je transcris…", "travail")

        def travail():
            try:
                self.pont.voix.emit(self.micro.arreter_et_transcrire(), "")
            except Exception as ex:
                self.pont.voix.emit("", str(ex) or "inconnue")

        threading.Thread(target=travail, daemon=True).start()

    def _voix_recue(self, texte, erreur):
        if erreur:
            self._toast("Erreur micro : " + erreur, "erreur")
        elif not texte:
            self._toast("Je n'ai rien entendu", "repos")
        else:
            self._statut("")
            if self.mode == "fichiers":
                self._pour_fichiers(texte)
            else:
                self.envoyer(texte)


def noter_erreur(type_, valeur, trace):
    """Sans fenêtre noire, les erreurs iraient nulle part : on les garde dans erreurs.log."""
    import traceback
    with open(donnees.DONNEES / "erreurs.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S]\n") + "".join(traceback.format_exception(type_, valeur, trace)))
    sys.__excepthook__(type_, valeur, trace)


if __name__ == "__main__":
    for flux in ("stdout", "stderr"):             # appli sans console : certaines barres de progression y écrivent
        if getattr(sys, flux) is None:
            setattr(sys, flux, open(os.devnull, "w", encoding="utf-8"))
    sys.excepthook = noter_erreur
    with open(donnees.DOSSIER_PROGRAMME / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tools.init(config)

    app = QApplication(sys.argv)
    app.setApplicationName("Dropi")

    # une seule goutte à la fois : si elle tourne déjà, on lui demande juste de s'ouvrir
    nom_instance = "AssistantIsland-" + os.environ.get("USERNAME", "")
    deja = QLocalSocket()
    deja.connectToServer(nom_instance)
    if deja.waitForConnected(300):
        deja.write(b"ouvrir")
        deja.waitForBytesWritten(300)
        sys.exit(0)
    QLocalServer.removeServer(nom_instance)
    serveur = QLocalServer()
    serveur.listen(nom_instance)

    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)   # menus et fenêtres Windows en sombre
    app.setWindowIcon(QIcon(QPixmap.fromImage(image_logo(256))))
    ile = Ile(config)
    ile.show()

    def autre_lancement():
        serveur.nextPendingConnection()
        if ile.mode == "repos":
            ile._aller("discussion")
            ile._premier_plan()

    serveur.newConnection.connect(autre_lancement)
    sys.exit(app.exec())
