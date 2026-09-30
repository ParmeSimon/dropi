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
                            QEasingCurve, Signal, QObject, QSettings)
from PySide6.QtGui import (QPainter, QColor, QPen, QLinearGradient, QConicalGradient, QCursor,
                           QFontMetrics, QPainterPath, QPixmap, QIcon)
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QMenu, QFileDialog
from PySide6.QtNetwork import QLocalServer, QLocalSocket

import tools
import goutte
import menage
import musique
import memoire
import demarrage
import donnees
import classement
import composants as ui
from brain import Cerveau
from mascotte import Mascotte, VueMascotte, image_logo
from voice import Micro

CERCLE = 46             # la goutte au repos
ECART = 8               # espace entre le bord de l'écran et la bulle (comblé par le col liquide)
MARGE = 10              # distance minimale aux coins de l'écran
CAPSULE_MAX = 440
SURVOL = (350, 124)     # quand un fichier passe au-dessus
LARGEUR_FICHIERS = 500
DISCUSSION = (540, 540)
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
}

SUGGESTIONS = [("manette", "Mes jeux"), ("ranger", "Range mes téléchargements"),
               ("balai", "Fais-moi de la place"), ("mail", "Résume mes derniers mails")]


def decrire_action(nom, args):
    verbe = VERBES.get(nom, nom.replace("_", " ").capitalize())
    for cle in ("chemin", "nom", "streamer", "site", "requete", "dossier", "question", "information", "action"):
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


class Ile(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)

        self.cerveau = Cerveau(config)
        self.micro = Micro(config.get("whisper_modele", "small"), config.get("langue", "fr"))
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
        self._mode_telechargements = str((config.get("telechargements") or {}).get("mode", "proposer"))
        self._tailles_en_cours = {}
        try:
            self._connus = {str(p) for p in tools.fichiers_telechargements()}
        except OSError:
            self._connus = set()

        self._construire_discussion()
        self._construire_fichiers()
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

        tete, self.vue_disc, self.titre_disc = self._entete("Assistant")
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
        acc.addStretch(1)
        self.vue_accueil = VueMascotte(self.mascotte, 24, halo=True)
        acc.addWidget(self.vue_accueil, 0, Qt.AlignHCenter)
        acc.addSpacing(6)
        titre = ui.Etiquette("Qu'est-ce que je peux faire pour toi ?", 18, gras=True)
        titre.setAlignment(Qt.AlignCenter)
        sous = ui.Etiquette("Écris, parle, ou dépose un fichier sur la goutte.", 12, ui.TEXTE_3)
        sous.setAlignment(Qt.AlignCenter)
        acc.addWidget(titre)
        acc.addWidget(sous)
        acc.addSpacing(16)
        for i in range(0, len(SUGGESTIONS), 2):
            rangee = QHBoxLayout()
            rangee.setSpacing(8)
            rangee.addStretch(1)
            for icone, texte in SUGGESTIONS[i:i + 2]:
                puce = ui.Bouton(icone, texte, "puce")
                puce.clicked.connect(lambda _=False, t=texte: self._suggestion(t))
                rangee.addWidget(puce)
            rangee.addStretch(1)
            acc.addLayout(rangee)
        acc.addStretch(2)
        lay.addWidget(self.accueil, 1)

        barre, self.champ, micro, envoyer = ui.barre_saisie("Demande-moi quelque chose…")
        self.champ.returnPressed.connect(lambda: self.envoyer(self.champ.text()))
        self.champ.textEdited.connect(self._frappe)
        envoyer.clicked.connect(lambda: self.envoyer(self.champ.text()))
        micro.pressed.connect(self._micro_debut)
        micro.released.connect(self._micro_fin)
        lay.addWidget(barre)
        self._maj_accueil()

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
        bureau = ui.Bouton("bureau", "Bureau", "puce", info="Le mettre sur le Bureau")
        bureau.clicked.connect(lambda: self._action_directe("bureau"))
        self.btn_suppr = ui.Bouton("supprimer", "Supprimer", "puce", info="Envoie à la corbeille")
        self.btn_suppr.clicked.connect(self._supprimer)
        montrer = ui.Bouton("explorateur", genre="puce", info="Afficher dans l'explorateur")
        montrer.clicked.connect(lambda: self._action_directe("afficher"))
        for b in (ouvrir, deplacer, bureau, self.btn_suppr, montrer):
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
        return "Clique, tire-moi, ou dépose un fichier" if self._souris else ""

    def _taille_cible(self):
        if self.mode == "survol":
            return QSizeF(*SURVOL)
        if self.mode == "fichiers":
            return QSizeF(LARGEUR_FICHIERS, self.page_fichiers.sizeHint().height())
        if self.mode == "discussion":
            return QSizeF(*DISCUSSION)
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
        return {"discussion": self.page_discussion, "fichiers": self.page_fichiers}.get(mode)

    def _aller(self, mode):
        self.mode = mode
        for m in ("discussion", "fichiers"):
            if m != mode:
                self._page(m).hide()
        if mode in ("discussion", "fichiers"):
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
            champ = self.champ if self.mode == "discussion" else self.champ_fich
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
        self.mascotte.ecrase = self._ecrase.valeur * 0.8
        self.mascotte.maj(dt, self._ancre_mascotte(), QPointF(curseur))

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
        for vue in (self.vue_disc, self.vue_fich, self.vue_accueil):
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
            if ecarts[self._col_bord] > goutte.RUPTURE:
                self._col_force.cible = 0.0
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

    def _ancre_mascotte(self):
        if self.mode == "discussion" and self.vue_disc.isVisible():
            return self.vue_disc.centre_global()
        if self.mode == "fichiers" and self.vue_fich.isVisible():
            return self.vue_fich.centre_global()
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
        self._toast_telechargement = False
        self._fin_toast.stop()
        if duree:
            self._fin_toast.start(duree)
        self.titre_disc.setText(texte or "Assistant")
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
        if self.mode in ("discussion", "fichiers") and e.position().y() > self._rect_forme().top() + 46:
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
        self._rouvrir = self.mode if self.mode in ("discussion", "fichiers") else None
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
        menu.addAction("Nouvelle conversation", self._reset)
        menu.addAction("Replacer en haut", self._replacer)
        menu.addSeparator()
        menu.addAction("Ce que j'ai appris", self._montrer_memoire)
        menu.addAction("Oublier ce que j'ai appris", self._oublier_memoire)
        auto = menu.addAction("Lancer au démarrage de Windows")
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
                and not self._dialogue and self.mode in ("discussion", "fichiers")):
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
        self._maj_titre_fichiers()

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

    def _suggestion(self, texte):
        if texte == "Mes jeux":
            self._mes_jeux()
        elif texte == "Range mes téléchargements":
            self._ranger_telechargements()
        elif texte == "Fais-moi de la place":
            self._faire_de_la_place()
        else:
            self.envoyer(texte)

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
            QTimer.singleShot(20000, lambda: self._ranger_tout_seul(chemin))
            return
        self._proposes.append(chemin)
        self.mascotte.reagir("curieux", 3.0)
        if self.mode == "repos" and not self.occupee:
            self._statut(f"Nouveau : {nom}  →  {lieu}", "repos", duree=15000)
            self._toast_telechargement = True
            self.mascotte.sauter(0.7)
        else:
            self.fil.action(f"Nouveau téléchargement : {nom}  →  {lieu} (clique pour ranger)",
                            self._ouvrir_proposes)

    def _ouvrir_proposes(self):
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
        self._premier_plan()

    def _ranger_tout_seul(self, chemin):
        """Mode auto : range le téléchargement 20 s après la fin (s'il est toujours là)."""
        if not Path(chemin).exists() or self.occupee:
            return
        resultat = tools.ranger_fichier(chemin)
        self.cerveau.noter(f"Range le téléchargement {chemin}", resultat)
        if est_erreur(resultat):
            return
        lieu = classement.court(classement.retrouver(chemin).parent)
        self.fil.action(f"{Path(chemin).name} rangé dans {lieu}", self._clic_dossier(chemin)).terminer(True)
        self._maj_accueil()
        if self.mode == "repos":
            self._toast(f"Rangé : {Path(chemin).name}  →  {lieu}", "succes")

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

    def envoyer(self, texte, fichiers=None):
        texte = texte.strip()
        if self.occupee or not texte:
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
        self._statut("Je réfléchis…", "travail")

        def travail():
            try:
                rep = self.cerveau.demander(
                    requete,
                    sur_action=lambda nom, args: self.pont.action.emit(decrire_action(nom, args)),
                    sur_resultat=lambda nom, args, res: self.pont.resultat.emit(nom, args, not est_erreur(res)))
                self.pont.reponse.emit(rep, False)
            except Exception as ex:
                self.pont.reponse.emit(f"Oups : {ex}. Ollama est bien lancé ?", True)

        threading.Thread(target=travail, daemon=True).start()

    def _action_ia(self, texte):
        self._actions.append(texte)
        self.fil.action(texte)
        self._statut(texte + "…", "travail")

    def _resultat_ia(self, nom, args, ok):
        if self.fil.derniere_puce:
            self.fil.derniere_puce.terminer(ok)
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
        if erreur:
            self.fil.erreur(rep)
        else:
            self.fil.ia(rep)
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
    app.setApplicationName("Assistant Island")

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
