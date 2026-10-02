"""Le tableau de bord : Dropi en grand, à la place du bureau et de la barre des tâches.

Un seul écran, sans rien à chercher : tes applis épinglées, tes jeux, tes fichiers rangés par thème, les fenêtres
ouvertes, et une barre de recherche qui lance tout (appli, jeu, fichier) ou pose la question à Dropi.

Léger : rien n'est animé en continu. L'horloge se met à jour toutes les 20 secondes, la liste des fenêtres toutes les
2 secondes, et seulement quand le tableau de bord est affiché ; tout s'arrête dès qu'il est réduit.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QSize, QTimer, Signal, QObject
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QRadialGradient, QPixmap, QFontMetrics
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedLayout, QAbstractButton,
                               QScrollArea, QMenu, QFrame, QSizePolicy)

import classement
import composants as ui
import donnees
import fichiers
import icones
import memoire
import systeme
import themes
import tools
from mascotte import image_logo, VueMascotte

FICHIER = donnees.fichier("tableau.json")
MARGE = 44
USAGES_EPINGLES = ["navigateur", "discussion", "mails", "code", "musique", "texte", "tableur", "présentation", "vidéo", "jeux"]
MAX_EPINGLES = 21


# ---------------------------------------------------------------- ce qui est épinglé
def lire_epingles():
    try:
        return list(json.loads(FICHIER.read_text("utf-8")).get("applis", []))
    except (OSError, ValueError):
        return None


def ecrire_epingles(applis):
    try:
        FICHIER.write_text(json.dumps({"applis": applis}, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass


def epingles_par_defaut(installees):
    """Au premier lancement : une appli par usage (navigateur, discussion, code…), celles que tu as vraiment."""
    choisies = []
    for usage in USAGES_EPINGLES:
        for nom in tools.USAGES_ICI.get(usage, [])[:1]:
            if nom in installees and nom not in choisies:
                choisies.append(nom)
    for nom in ("Explorateur de fichiers", "Calculatrice", "Paramètres"):
        if nom in installees and nom not in choisies:
            choisies.append(nom)
    return [{"nom": n, "id": installees[n]} for n in choisies[:12]]


def lancer_appli(nom, identifiant):
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + identifiant], creationflags=0x08000000)
    try:
        memoire.noter_usage("ouvrir_application", {"nom": nom})
    except Exception:
        pass


# ---------------------------------------------------------------- les éléments
class TuileAppli(QAbstractButton):
    """Une appli épinglée : son icône, son nom. Clic droit : retirer."""
    menu = Signal(object)

    def __init__(self, appli, parent=None):
        super().__init__(parent)
        self.appli, self.pix = appli, QPixmap()
        self.setFixedSize(104, 98)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setToolTip(appli["nom"])

    def contextMenuEvent(self, e):
        self.menu.emit(e.globalPos())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.underMouse() or self.isDown():
            a = ui.accent()
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 150), 1.2))
            p.setBrush(QColor(255, 255, 255, 12 if self.isDown() else 22))
            p.drawRoundedRect(r, 16, 16)
        cote = 46
        if not self.pix.isNull():
            p.drawPixmap(QRectF(r.center().x() - cote / 2, r.top() + 12, cote, cote), self.pix, QRectF(self.pix.rect()))
        else:                                              # l'icône arrive : en attendant, l'initiale
            p.setPen(Qt.NoPen)
            p.setBrush(ui.CARTE_SURVOL)
            p.drawRoundedRect(QRectF(r.center().x() - cote / 2, r.top() + 12, cote, cote), 12, 12)
            p.setPen(ui.TEXTE_2)
            p.setFont(ui.police(18, True))
            p.drawText(QRectF(r.center().x() - cote / 2, r.top() + 12, cote, cote), Qt.AlignCenter, self.appli["nom"][:1].upper())
        p.setPen(ui.TEXTE if self.underMouse() else ui.TEXTE_2)
        p.setFont(ui.police(11))
        p.drawText(QRectF(r.left() + 4, r.top() + 62, r.width() - 8, 32), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                   QFontMetrics(ui.police(11)).elidedText(self.appli["nom"], Qt.ElideRight, int(r.width() * 1.8)))


class TuilePlus(QAbstractButton):
    """Le « + » : épingler une autre appli."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(104, 98)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setToolTip("Épingler une appli")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        stylo = QPen(QColor(255, 255, 255, 90 if self.underMouse() else 40), 1.2, Qt.DashLine)
        p.setPen(stylo)
        p.setBrush(QColor(255, 255, 255, 14) if self.underMouse() else Qt.NoBrush)
        p.drawRoundedRect(QRectF(r.center().x() - 23, r.top() + 12, 46, 46), 12, 12)
        p.setPen(ui.TEXTE_2 if self.underMouse() else ui.TEXTE_3)
        p.setFont(ui.police(20))
        p.drawText(QRectF(r.center().x() - 23, r.top() + 10, 46, 46), Qt.AlignCenter, "+")
        p.setFont(ui.police(11))
        p.drawText(QRectF(r.left(), r.top() + 62, r.width(), 20), Qt.AlignHCenter | Qt.AlignTop, "Ajouter")


class CarteTheme(QAbstractButton):
    """Un thème de rangement : nom, nombre de fichiers. Clic : ouvre le gestionnaire sur ce thème."""

    def __init__(self, dossier, parent=None):
        super().__init__(parent)
        self.dossier, self.nombre = dossier, None
        self.glyphe = ui.ICONES.get(themes.GLYPHES.get(dossier, "ouvrir"), "")
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def regler(self, nombre):
        self.nombre = nombre
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        a = ui.accent()
        a_trier = self.dossier.startswith("99") and bool(self.nombre)
        if self.underMouse():
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 190), 1.4))
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 30))
        else:
            p.setPen(QPen(QColor(255, 196, 0, 120) if a_trier else QColor(255, 255, 255, 30), 1))
            p.setBrush(ui.CARTE)
        p.drawRoundedRect(r, 14, 14)
        p.setPen(QColor(255, 196, 0) if a_trier else a)
        p.setFont(ui.police_icones(18))
        p.drawText(QRectF(12, 0, 28, self.height()), Qt.AlignCenter, self.glyphe)
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(13, True))
        p.drawText(QRectF(50, 9, self.width() - 58, 22), Qt.AlignLeft | Qt.AlignVCenter, themes.NOMS_THEMES.get(self.dossier, self.dossier))
        p.setPen(ui.TEXTE_3)
        p.setFont(ui.police(11))
        texte = "…" if self.nombre is None else ("vide" if not self.nombre else f"{self.nombre} fichier{'s' if self.nombre > 1 else ''}")
        p.drawText(QRectF(50, 30, self.width() - 58, 18), Qt.AlignLeft | Qt.AlignVCenter, texte)


class PuceFenetre(QAbstractButton):
    """Une fenêtre ouverte (ce que montrait la barre des tâches) : clic = la mettre devant, croix = la fermer."""
    fermer = Signal()

    def __init__(self, fenetre, parent=None):
        super().__init__(parent)
        self.fenetre = fenetre
        self.pix = icones.icone_fichier(fenetre["exe"], 32) if fenetre["exe"] else QPixmap()
        self.setFixedHeight(40)
        self.setMaximumWidth(230)
        self.setMinimumWidth(120)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self.setToolTip(fenetre["titre"])

    def sizeHint(self):
        largeur = QFontMetrics(ui.police(12)).horizontalAdvance(self.fenetre["titre"]) + 74
        return QSize(max(120, min(230, largeur)), 40)

    def _croix(self):
        return QRectF(self.width() - 30, 8, 24, 24)

    def mouseMoveEvent(self, e):
        self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._croix().contains(e.position())):
            self.setDown(False)
            self.fermer.emit()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        survol = self.underMouse()
        p.setPen(QPen(ui.CONTOUR, 1))
        p.setBrush(ui.CARTE_SURVOL if survol else ui.CARTE)
        p.drawRoundedRect(r, 12, 12)
        if not self.pix.isNull():
            p.drawPixmap(QRectF(11, 10, 20, 20), self.pix, QRectF(self.pix.rect()))
        p.setPen(ui.TEXTE if survol else ui.TEXTE_2)
        p.setFont(ui.police(12))
        place = self.width() - 42 - (30 if survol else 8)
        p.drawText(QRectF(40, 0, place, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.fenetre["titre"], Qt.ElideRight, int(place)))
        if self.fenetre["reduite"]:
            p.setPen(Qt.NoPen)
            p.setBrush(ui.TEXTE_3)
            p.drawEllipse(QPointF(21, 35), 1.6, 1.6)
        if survol:
            croix = self._croix()
            sur_croix = croix.contains(QPointF(self.mapFromGlobal(self.cursor().pos())))
            if sur_croix:
                p.setPen(Qt.NoPen)
                p.setBrush(ui.ROUGE)
                p.drawRoundedRect(croix, 7, 7)
            p.setPen(ui.TEXTE if sur_croix else ui.TEXTE_3)
            p.setFont(ui.police_icones(9))
            p.drawText(croix, Qt.AlignCenter, ui.ICONES["fermer"])


class Horloge(QWidget):
    """L'heure en grand et la date. Mise à jour toutes les 20 secondes, seulement quand elle est visible."""
    JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(330, 80)
        self._minuteur = QTimer(self, interval=20000, timeout=self.update)

    def showEvent(self, _):
        self._minuteur.start()

    def hideEvent(self, _):
        self._minuteur.stop()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        m = time.localtime()
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(34, True, "Segoe UI Variable Display"))
        heure = f"{m.tm_hour:02d}:{m.tm_min:02d}"
        p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignRight | Qt.AlignVCenter, heure)
        largeur = p.fontMetrics().horizontalAdvance(heure)
        p.setPen(ui.TEXTE_2)
        p.setFont(ui.police(13))
        p.drawText(QRectF(0, 4, self.width() - largeur - 16, self.height()), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.JOURS[m.tm_wday]} {m.tm_mday} {self.MOIS[m.tm_mon - 1]}")


class PastilleReduire(QAbstractButton):
    """En haut au milieu : Plop dans sa capsule. Un clic et le tableau de bord redevient une goutte."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(128, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setToolTip("Réduire : revenir à la goutte (Échap)")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 60 if self.underMouse() else 34), 1))
        p.setBrush(ui.remplissage_ile(r))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(ui.TEXTE if self.underMouse() else ui.TEXTE_2)
        p.setFont(ui.police(12, True))
        p.drawText(QRectF(20, 0, 70, self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Réduire")
        p.setFont(ui.police_icones(10))
        p.drawText(QRectF(self.width() - 40, 0, 28, self.height()), Qt.AlignCenter, ui.ICONES["reduire"])


class CoinDropi(QAbstractButton):
    """Dropi, la mascotte du tableau de bord : en haut à gauche, avec une bulle où il te parle. Un clic ouvre le tchat."""

    def __init__(self, mascotte=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(430, 80)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setToolTip("Parler à Dropi")
        self.texte, self.etat = "Clique sur moi pour discuter.", "repos"
        self.vue = None
        self.plop = QPixmap()
        if mascotte is not None:
            self.vue = VueMascotte(mascotte, 19, halo=True, parent=self)
            self.vue.move(0, 0)
            self.vue.setAttribute(Qt.WA_TransparentForMouseEvents)
        else:
            self.plop = QPixmap.fromImage(image_logo(128))

    def centre_plop(self):
        """Le centre de Plop, dans les coordonnées du tableau de bord."""
        return QPointF(self.mapTo(self.window(), QPoint(40, 40)))

    def centre_global(self):
        return QPointF(self.mapToGlobal(QPoint(40, 40)))

    def dire(self, texte, etat="repos"):
        self.texte, self.etat = texte or "Clique sur moi pour discuter.", etat
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.vue is None and not self.plop.isNull():
            p.drawPixmap(QRectF(8, 8, 64, 64), self.plop, QRectF(self.plop.rect()))
        fonte = ui.police(12)
        largeur = min(self.width() - 96, QFontMetrics(fonte).horizontalAdvance(self.texte) + 28)
        bulle = QRectF(88, 22, max(60, largeur), 36)
        couleur = {"erreur": ui.ERREUR, "succes": ui.SUCCES}.get(self.etat)
        p.setPen(QPen(QColor(255, 255, 255, 70 if self.underMouse() else 36), 1))
        p.setBrush(QColor(255, 255, 255, 26 if self.underMouse() else 16))
        p.drawRoundedRect(bulle, 14, 14)
        queue = [QPointF(bulle.left() + 1, bulle.center().y() - 6), QPointF(bulle.left() - 8, bulle.center().y()),
                 QPointF(bulle.left() + 1, bulle.center().y() + 6)]
        p.setPen(Qt.NoPen)
        p.drawPolygon(queue)
        p.setPen(couleur or (ui.TEXTE if self.underMouse() else ui.TEXTE_2))
        p.setFont(fonte)
        p.drawText(bulle.adjusted(14, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(fonte).elidedText(self.texte, Qt.ElideRight, int(bulle.width() - 26)))


class PanneauChat(QFrame):
    """Le tchat avec Dropi, sous la mascotte. Le fil de la conversation est celui de la goutte (même mémoire)."""
    message = Signal(str)
    arreter = Signal()
    nouvelle = Signal()
    ferme = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat")
        self.setStyleSheet("#chat { background: #202024; border: 1px solid rgba(255,255,255,40); border-radius: 18px; }")
        self._occupe = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 12, 12)
        lay.setSpacing(8)
        tete = QHBoxLayout()
        tete.setSpacing(4)
        tete.addWidget(ui.Etiquette("Discussion avec Dropi", 14, ui.TEXTE, gras=True), 1)
        nouveau = ui.Bouton("nouveau", info="Nouvelle conversation")
        nouveau.clicked.connect(self.nouvelle.emit)
        fermer = ui.Bouton("fermer", info="Fermer le tchat (Échap)")
        fermer.clicked.connect(self.ferme.emit)
        tete.addWidget(nouveau)
        tete.addWidget(fermer)
        lay.addLayout(tete)
        self.zone = QVBoxLayout()
        self.zone.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.zone, 1)
        self.vide = ui.Etiquette("Écris-moi ci-dessous, ou maintiens le micro pour parler.\n\n"
                                 "« ouvre Discord », « range mes téléchargements », « on joue ? », ou n'importe quelle question.",
                                 13, ui.TEXTE_3)
        self.vide.setAlignment(Qt.AlignCenter)
        self.vide.setWordWrap(True)
        self.zone.addWidget(self.vide, 1)
        barre, self.champ, self.micro, self.envoyer = ui.barre_saisie("Écris à Dropi…")
        self.champ.returnPressed.connect(self._envoyer)
        self.envoyer.clicked.connect(lambda: self.arreter.emit() if self._occupe else self._envoyer())
        lay.addWidget(barre)
        self.fil = None

    def _envoyer(self):
        texte = self.champ.text().strip()
        if texte:
            self.champ.clear()
            self.message.emit(texte)

    def occuper(self, oui):
        """L'IA répond : le bouton d'envoi devient un carré « arrêter »."""
        self._occupe = oui
        self.envoyer.icone = ui.ICONES["arreter" if oui else "envoyer"]
        self.envoyer.setToolTip("Arrêter la demande" if oui else "Envoyer")
        self.envoyer.update()

    def accueillir(self, fil):
        self.fil = fil
        self.zone.insertWidget(0, fil, 1)
        self.maj()

    def rendre(self):
        fil, self.fil = self.fil, None
        if fil is not None:
            self.zone.removeWidget(fil)
        self.vide.show()
        return fil

    def maj(self):
        """Fil vide : on montre le mot d'accueil ; sinon la conversation."""
        vide = self.fil is None or self.fil.vide()
        self.vide.setVisible(vide)
        if self.fil is not None:
            self.fil.setVisible(not vide)


class LigneResultat(QAbstractButton):
    def __init__(self, resultat, parent=None):
        super().__init__(parent)
        self.resultat, self.choisi = resultat, False
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        if self.choisi or self.underMouse():
            a = ui.accent()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 46 if self.choisi else 24))
            p.drawRoundedRect(r, 10, 10)
        pix = self.resultat.get("pix")
        if pix is not None and not pix.isNull():
            p.drawPixmap(QRectF(14, 9, 24, 24), pix, QRectF(pix.rect()))
        else:
            p.setPen(ui.accent())
            p.setFont(ui.police_icones(14))
            p.drawText(QRectF(12, 0, 28, self.height()), Qt.AlignCenter, ui.ICONES.get(self.resultat.get("glyphe", "ouvrir"), ""))
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(13))
        place = self.width() - 200
        p.drawText(QRectF(50, 0, place, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.resultat["nom"], Qt.ElideMiddle, int(place)))
        p.setPen(ui.TEXTE_3)
        p.setFont(ui.police(11))
        p.drawText(QRectF(self.width() - 150, 0, 136, self.height()), Qt.AlignVCenter | Qt.AlignRight, self.resultat["genre"])


class _Pont(QObject):
    comptes = Signal(dict)
    applis = Signal(dict)
    index = Signal(list)


# ---------------------------------------------------------------- le tableau de bord
class Tableau(QWidget):
    reduire = Signal()                    # retour à la goutte
    demande = Signal(str)                 # une phrase pour Dropi (tapée dans la recherche ou dans le tchat)
    veut_fil = Signal()                   # le tchat s'ouvre : il lui faut le fil de la conversation
    actif = Signal(bool)                  # le tableau de bord passe devant / derrière
    jeu = Signal(str)                     # lancer un jeu
    dossier = Signal(str)                 # ouvrir le gestionnaire de fichiers sur ce dossier

    def __init__(self, mascotte=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dropi")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._fond = None
        self._installees, self._epingles, self._tuiles = {}, [], []
        self._index, self._index_date = [], 0.0
        self._resultats, self._choix = [], 0
        self._pont = _Pont()
        self._pont.comptes.connect(self._maj_comptes)
        self._pont.applis.connect(self._applis_pretes)
        self._pont.index.connect(self._index_pret)
        self._a_charger = []
        self._chargeur = QTimer(self, interval=0, timeout=self._charger_une_icone)
        self._veille = QTimer(self, interval=2000, timeout=self._maj_fenetres)
        self._signature_fenetres = None

        racine = QVBoxLayout(self)
        racine.setContentsMargins(MARGE, 18, MARGE, 22)
        racine.setSpacing(0)

        # ---- le haut : heure, pastille « Réduire », recherche
        haut = QHBoxLayout()
        haut.setSpacing(0)
        self.coin = CoinDropi(mascotte)
        self.coin.clicked.connect(self.basculer_chat)
        haut.addWidget(self.coin, 0, Qt.AlignLeft | Qt.AlignTop)
        haut.addStretch(1)
        self.pastille = PastilleReduire()
        self.pastille.clicked.connect(self.reduire.emit)
        haut.addWidget(self.pastille, 0, Qt.AlignTop)
        haut.addStretch(1)
        self.horloge = Horloge()
        haut.addWidget(self.horloge, 0, Qt.AlignRight | Qt.AlignTop)
        racine.addLayout(haut)
        racine.addSpacing(10)
        self.pile = QStackedLayout()
        racine.addLayout(self.pile, 1)
        accueil = QWidget()
        corps = QVBoxLayout(accueil)
        corps.setContentsMargins(0, 0, 0, 0)
        corps.setSpacing(0)
        self.pile.addWidget(accueil)
        self.gestionnaire = fichiers.Gestionnaire()
        self.gestionnaire.retour.connect(self.montrer_accueil)
        self.pile.addWidget(self.gestionnaire)

        self.champ = ui.Champ("Lance une appli, un jeu, un fichier… ou demande à Dropi")
        self.champ.setFixedHeight(46)
        self.champ.setFont(ui.police(14))
        self.champ.setFixedWidth(620)
        self.champ.textChanged.connect(self._chercher)
        self.champ.returnPressed.connect(self._valider)
        self.champ.installEventFilter(self)
        corps.addWidget(self.champ, 0, Qt.AlignHCenter)
        corps.addSpacing(26)

        # ---- le milieu : deux colonnes
        milieu = QHBoxLayout()
        milieu.setSpacing(56)
        gauche = QVBoxLayout()
        gauche.setSpacing(10)
        gauche.addWidget(ui.TitreSection(1, "Mes applis", "applis"))
        self.grille_applis = QGridLayout()
        self.grille_applis.setSpacing(6)
        self.grille_applis.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        gauche.addLayout(self.grille_applis)
        gauche.addSpacing(18)
        self.titre_jeux = ui.TitreSection(2, "Mes jeux", "manette")
        gauche.addWidget(self.titre_jeux)
        self.rangee_jeux = QHBoxLayout()
        self.rangee_jeux.setSpacing(12)
        self.rangee_jeux.setAlignment(Qt.AlignLeft)
        gauche.addLayout(self.rangee_jeux)
        gauche.addStretch(1)
        milieu.addLayout(gauche, 3)

        colonne = QVBoxLayout()
        colonne.setSpacing(10)
        entete_fichiers = QHBoxLayout()
        entete_fichiers.addWidget(ui.TitreSection(3, "Mes fichiers", "ouvrir"), 1)
        tout = ui.Bouton("dossier_ouvert", "Tout voir", "puce", info="Ouvrir le gestionnaire de fichiers")
        tout.clicked.connect(lambda: self.montrer_fichiers())
        entete_fichiers.addWidget(tout)
        colonne.addLayout(entete_fichiers)
        grille = QGridLayout()
        grille.setSpacing(8)
        self.cartes = {}
        for i, (dossier, _) in enumerate(themes.ARBORESCENCE):
            carte = CarteTheme(dossier)
            carte.clicked.connect(lambda _=False, d=dossier: self.montrer_fichiers(d))
            self.cartes[dossier] = carte
            grille.addWidget(carte, i // 2, i % 2)
        colonne.addLayout(grille)
        colonne.addSpacing(18)
        colonne.addWidget(ui.TitreSection(4, "Rangés récemment", "horloge"))
        self.recents = QVBoxLayout()
        self.recents.setSpacing(4)
        colonne.addLayout(self.recents)
        colonne.addStretch(1)
        milieu.addLayout(colonne, 2)
        corps.addLayout(milieu, 1)

        # ---- le bas : les fenêtres ouvertes (ce que montrait la barre des tâches)
        corps.addSpacing(10)
        corps.addWidget(ui.TitreSection(5, "Fenêtres ouvertes", "pc"))
        corps.addSpacing(8)
        self.bande = QHBoxLayout()
        self.bande.setSpacing(8)
        self.bande.setAlignment(Qt.AlignLeft)
        conteneur = QWidget()
        conteneur.setLayout(self.bande)
        conteneur.setFixedHeight(44)
        self.bande.setContentsMargins(0, 0, 0, 0)
        corps.addWidget(conteneur)

        # ---- les résultats de recherche, par-dessus
        self.resultats = QFrame(self)
        self.resultats.setObjectName("resultats")
        self.resultats.setStyleSheet("#resultats { background: #26262a; border: 1px solid rgba(255,255,255,40); border-radius: 16px; }")
        self.liste_resultats = QVBoxLayout(self.resultats)
        self.liste_resultats.setContentsMargins(6, 6, 6, 6)
        self.liste_resultats.setSpacing(2)
        self.resultats.hide()

        # ---- le tchat avec Dropi, sous la mascotte
        self.chat = PanneauChat(self)
        self.chat.message.connect(self.demande.emit)
        self.chat.ferme.connect(self.fermer_chat)
        self.chat.hide()

    # ------------------------------------------------------------ Dropi et son tchat
    def centre_plop(self):
        return self.coin.centre_plop()

    def dire(self, texte, etat="repos"):
        """Ce que Dropi a à dire (« Je réfléchis… », « Rangé dans Études »…) : dans sa bulle."""
        self.coin.dire(texte, etat)

    def _placer_chat(self):
        hauteur = max(320, min(660, self.height() - 150))
        self.chat.setGeometry(MARGE, 104, ui.LARGEUR_FIL + 36, hauteur)

    def ouvrir_chat(self):
        if not self.chat.isVisible():
            self.veut_fil.emit()
            self._placer_chat()
            self.chat.show()
            self.chat.raise_()
        self.chat.maj()
        self.chat.champ.setFocus()

    def fermer_chat(self):
        self.chat.hide()
        if self.pile.currentIndex() == 0:
            self.champ.setFocus()

    def basculer_chat(self):
        self.fermer_chat() if self.chat.isVisible() else self.ouvrir_chat()

    # ------------------------------------------------------------ fond
    def resizeEvent(self, e):
        self._fond = None
        self._placer_resultats()
        if hasattr(self, "chat"):
            self._placer_chat()
        super().resizeEvent(e)

    @staticmethod
    def peindre_fond(p, rect):
        """Le fond du tableau de bord (partagé avec l'animation d'ouverture)."""
        fond = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fond.setColorAt(0, QColor(30, 30, 34))
        fond.setColorAt(1, QColor(17, 17, 20))
        p.fillRect(rect, fond)
        a = ui.accent()
        lueur = QRadialGradient(QPointF(rect.left() + rect.width() * 0.18, rect.top()), rect.width() * 0.6)
        lueur.setColorAt(0, QColor(a.red(), a.green(), a.blue(), 34))
        lueur.setColorAt(1, QColor(a.red(), a.green(), a.blue(), 0))
        p.fillRect(rect, lueur)
        violet = QRadialGradient(QPointF(rect.right(), rect.bottom()), rect.width() * 0.5)
        violet.setColorAt(0, QColor(160, 130, 255, 22))
        violet.setColorAt(1, QColor(160, 130, 255, 0))
        p.fillRect(rect, violet)

    def paintEvent(self, _):
        if self._fond is None or self._fond.size() != self.size() * self.devicePixelRatioF():
            self._fond = QPixmap(self.size() * self.devicePixelRatioF())
            self._fond.setDevicePixelRatio(self.devicePixelRatioF())
            q = QPainter(self._fond)
            self.peindre_fond(q, QRectF(self.rect()))
            q.end()
        QPainter(self).drawPixmap(0, 0, self._fond)

    # ------------------------------------------------------------ vie
    def showEvent(self, e):
        super().showEvent(e)
        self.rafraichir()
        self._veille.start()
        self.champ.setFocus()

    def hideEvent(self, e):
        self._veille.stop()
        self._chargeur.stop()
        super().hideEvent(e)

    def changeEvent(self, e):
        if e.type() == e.Type.ActivationChange:
            self.actif.emit(self.isActiveWindow())
            if self.isActiveWindow():
                self._maj_fenetres()
        super().changeEvent(e)

    def rafraichir(self):
        """Tout remettre à jour (à l'ouverture) : applis, jeux, compteurs de fichiers, récents, fenêtres."""
        self._installees = dict(tools._applis_windows)
        if self._installees:
            self._construire_applis()
        else:                                              # Windows n'a pas encore donné la liste : on la demande
            threading.Thread(target=lambda: self._pont.applis.emit(dict(tools._applis_installees())), daemon=True).start()
        self._construire_jeux()
        self._construire_recents()
        self._maj_fenetres()
        threading.Thread(target=self._compter, daemon=True).start()
        if time.monotonic() - self._index_date > 120:
            threading.Thread(target=self._indexer, daemon=True).start()

    def montrer_fichiers(self, dossier=None):
        """Passe au gestionnaire de fichiers (sur un thème, ou sur tous les fichiers)."""
        self._fin_recherche()
        self.gestionnaire.aller(dossier or classement.racine())
        self.pile.setCurrentWidget(self.gestionnaire)
        self.gestionnaire.liste.setFocus()

    def montrer_accueil(self):
        self.pile.setCurrentIndex(0)
        self._construire_recents()
        threading.Thread(target=self._compter, daemon=True).start()
        self.champ.setFocus()

    # ------------------------------------------------------------ applis
    def _applis_pretes(self, installees):
        self._installees = installees
        self._construire_applis()

    def _construire_applis(self):
        epingles = lire_epingles()
        if epingles is None:
            if not tools.USAGES_ICI:
                try:
                    tools.USAGES_ICI = tools.applis_par_usage()
                except Exception:
                    pass
            epingles = epingles_par_defaut(self._installees)
            ecrire_epingles(epingles)
        self._epingles = [e for e in epingles if e.get("id")]
        while self.grille_applis.count():
            w = self.grille_applis.takeAt(0).widget()
            if w:
                w.deleteLater()
        colonnes = max(4, min(9, (self.width() * 3 // 5 - MARGE) // 110))
        self._tuiles = []
        for i, appli in enumerate(self._epingles):
            tuile = TuileAppli(appli)
            tuile.clicked.connect(lambda _=False, a=appli: lancer_appli(a["nom"], a["id"]))
            tuile.menu.connect(lambda pos, a=appli: self._menu_appli(a, pos))
            self.grille_applis.addWidget(tuile, i // colonnes, i % colonnes)
            self._tuiles.append(tuile)
            if icones.deja_prete(appli["id"], 64):         # déjà en cache : tout de suite (l'animation d'ouverture la montre)
                tuile.pix = icones.icone_appli(appli["id"], 64)
        if len(self._epingles) < MAX_EPINGLES:
            plus = TuilePlus()
            plus.clicked.connect(self._choisir_appli)
            n = len(self._epingles)
            self.grille_applis.addWidget(plus, n // colonnes, n % colonnes)
        self._a_charger = [t for t in self._tuiles if t.pix.isNull()]
        self._chargeur.start()

    def _charger_une_icone(self):
        """Une icône par tour de boucle : la fenêtre reste fluide même au tout premier affichage."""
        if not self._a_charger:
            self._chargeur.stop()
            return
        tuile = self._a_charger.pop(0)
        try:
            tuile.pix = icones.icone_appli(tuile.appli["id"], 64)
            tuile.update()
        except RuntimeError:
            pass                                           # la tuile a été détruite entre-temps

    def _menu_appli(self, appli, pos):
        menu = QMenu(self)
        menu.addAction("Ouvrir", lambda: lancer_appli(appli["nom"], appli["id"]))
        menu.addAction("Mettre en premier", lambda: self._deplacer_epingle(appli, 0))
        menu.addAction("Retirer du tableau de bord", lambda: self._retirer_epingle(appli))
        menu.exec(pos)

    def _retirer_epingle(self, appli):
        self._epingles = [e for e in self._epingles if e["id"] != appli["id"]]
        ecrire_epingles(self._epingles)
        self._construire_applis()

    def _deplacer_epingle(self, appli, position):
        self._epingles = [e for e in self._epingles if e["id"] != appli["id"]]
        self._epingles.insert(position, appli)
        ecrire_epingles(self._epingles)
        self._construire_applis()

    def epingler(self, nom):
        if nom in self._installees and all(e["id"] != self._installees[nom] for e in self._epingles):
            self._epingles.append({"nom": nom, "id": self._installees[nom]})
            ecrire_epingles(self._epingles)
            self._construire_applis()

    def _choisir_appli(self):
        """Le « + » : on tape le nom de l'appli dans la recherche, et Entrée (ou clic) l'épingle."""
        self._mode_epingle = True
        self.champ.setPlaceholderText("Quelle appli épingler ? Tape son nom…")
        self.champ.clear()
        self.champ.setFocus()
        self._chercher("")

    # ------------------------------------------------------------ jeux
    def _construire_jeux(self):
        while self.rangee_jeux.count():
            w = self.rangee_jeux.takeAt(0).widget()
            if w:
                w.deleteLater()
        try:
            jeux = tools.catalogue_jeux()
        except Exception:
            jeux = []
        self.titre_jeux.setVisible(bool(jeux))
        place = max(3, (self.width() * 3 // 5 - MARGE) // 126)
        for jeu in jeux[:place]:
            tuile = ui.TuileJeu(jeu, 112)
            tuile.clicked.connect(lambda _=False, n=jeu["nom"]: self.jeu.emit(n))
            self.rangee_jeux.addWidget(tuile)
        self._jeux = jeux

    # ------------------------------------------------------------ fichiers
    def _compter(self):
        racine = classement.racine()
        comptes = {}
        for dossier, _ in themes.ARBORESCENCE:
            total = 0
            for _, _, fichiers in os.walk(racine / dossier):
                total += len(fichiers)
            comptes[dossier] = total
        self._pont.comptes.emit(comptes)

    def _maj_comptes(self, comptes):
        for dossier, n in comptes.items():
            if dossier in self.cartes:
                self.cartes[dossier].regler(n)

    def _construire_recents(self):
        while self.recents.count():
            w = self.recents.takeAt(0).widget()
            if w:
                w.deleteLater()
        vus, lignes = set(), 0
        for e in reversed(classement.derniers(60)):
            chemin = e.get("apres", "")
            if chemin in vus or chemin == "Corbeille" or e.get("annule") or not Path(chemin).is_file():
                continue
            vus.add(chemin)
            resultat = {"nom": Path(chemin).name, "genre": classement.court(Path(chemin).parent), "glyphe": "document",
                        "pix": icones.icone_fichier(chemin, 32), "action": lambda c=chemin: os.startfile(c)}
            ligne = LigneResultat(resultat)
            ligne.clicked.connect(resultat["action"])
            self.recents.addWidget(ligne)
            lignes += 1
            if lignes >= 6:
                break
        if not lignes:
            vide = ui.Etiquette("Rien pour l'instant : ce que tu télécharges arrive ici, déjà rangé.", 12, ui.TEXTE_3)
            vide.setWordWrap(True)
            self.recents.addWidget(vide)

    def _indexer(self):
        """La liste des fichiers rangés (nom, chemin), pour la recherche. Dans un fil de fond."""
        index = []
        try:
            for dossier, _, fichiers in os.walk(classement.racine()):
                for f in fichiers:
                    index.append((themes.simple(f), os.path.join(dossier, f)))
                    if len(index) >= 40000:
                        break
        except OSError:
            pass
        self._pont.index.emit(index)

    def _index_pret(self, index):
        self._index, self._index_date = index, time.monotonic()

    # ------------------------------------------------------------ fenêtres ouvertes
    def _maj_fenetres(self):
        liste = systeme.fenetres()
        signature = [(f["hwnd"], f["titre"], f["reduite"]) for f in liste]
        if signature == self._signature_fenetres:
            return
        self._signature_fenetres = signature
        while self.bande.count():
            w = self.bande.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not liste:
            self.bande.addWidget(ui.Etiquette("Aucune fenêtre ouverte.", 12, ui.TEXTE_3))
            return
        place = self.width() - 2 * MARGE
        for f in liste:
            puce = PuceFenetre(f)
            place -= puce.sizeHint().width() + 8
            if place < 0:
                puce.deleteLater()
                break
            puce.clicked.connect(lambda _=False, h=f["hwnd"]: systeme.activer(h))
            puce.fermer.connect(lambda h=f["hwnd"]: (systeme.fermer(h), QTimer.singleShot(400, self._maj_fenetres)))
            self.bande.addWidget(puce)

    # ------------------------------------------------------------ recherche
    def _placer_resultats(self):
        if hasattr(self, "champ"):
            g = QRect(self.champ.mapTo(self, QPoint(0, 0)), self.champ.size())
            self.resultats.setGeometry(g.left(), g.bottom() + 8, g.width(), self.resultats.height())

    def _chercher(self, texte):
        mots = themes.simple(texte).split()
        epingle = getattr(self, "_mode_epingle", False)
        trouves = []
        if mots or epingle:
            for nom, identifiant in self._installees.items():
                n = themes.simple(nom)
                if all(m in n for m in mots):
                    rang = 0 if mots and any(mot.startswith(mots[0]) for mot in n.split()) else 1
                    if epingle:
                        trouves.append((rang, len(nom), {"nom": nom, "genre": "épingler", "glyphe": "applis",
                                                         "action": lambda n=nom: self.epingler(n)}))
                    else:
                        trouves.append((rang, len(nom), {"nom": nom, "genre": "application", "glyphe": "applis", "id": identifiant,
                                                         "action": lambda n=nom, i=identifiant: lancer_appli(n, i)}))
            if mots and not epingle:
                for jeu in getattr(self, "_jeux", []):
                    n = themes.simple(jeu["nom"])
                    if all(m in n for m in mots):
                        trouves.append((0, len(n), {"nom": jeu["nom"], "genre": "jeu", "glyphe": "manette",
                                                    "action": lambda n=jeu["nom"]: self.jeu.emit(n)}))
                fichiers = 0
                for n, chemin in self._index:
                    if all(m in n for m in mots):
                        trouves.append((2, len(n), {"nom": os.path.basename(chemin), "glyphe": "document", "chemin": chemin,
                                                    "genre": classement.court(Path(chemin).parent),
                                                    "action": lambda c=chemin: os.startfile(c)}))
                        fichiers += 1
                        if fichiers >= 5:
                            break
        trouves.sort(key=lambda t: (t[0], t[1]))
        self._resultats = [t[2] for t in trouves[:8]]
        if mots and not epingle:
            self._resultats.append({"nom": f"Demander à Dropi : « {texte.strip()} »", "genre": "Dropi", "glyphe": "message",
                                    "action": lambda t=texte.strip(): self.demande.emit(t)})
        self._choix = 0
        self._afficher_resultats()

    def _afficher_resultats(self):
        while self.liste_resultats.count():
            w = self.liste_resultats.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self._resultats:
            self.resultats.hide()
            return
        for i, r in enumerate(self._resultats):
            if "pix" not in r:
                if r.get("id") and i < 5:
                    r["pix"] = icones.icone_appli(r["id"], 64)
                elif r.get("chemin"):
                    r["pix"] = icones.icone_fichier(r["chemin"], 32)
            ligne = LigneResultat(r)
            ligne.choisi = i == self._choix
            ligne.clicked.connect(lambda _=False, n=i: self._lancer_resultat(n))
            self.liste_resultats.addWidget(ligne)
        self.resultats.setFixedHeight(len(self._resultats) * 44 + 12)
        self._placer_resultats()
        self.resultats.show()
        self.resultats.raise_()

    def _lancer_resultat(self, n):
        if 0 <= n < len(self._resultats):
            action = self._resultats[n]["action"]
            self._fin_recherche()
            action()

    def _valider(self):
        if self._resultats:
            self._lancer_resultat(self._choix)

    def _fin_recherche(self):
        self._mode_epingle = False
        self.champ.setPlaceholderText("Lance une appli, un jeu, un fichier… ou demande à Dropi")
        self.champ.blockSignals(True)
        self.champ.clear()
        self.champ.blockSignals(False)
        self._resultats = []
        self.resultats.hide()

    def eventFilter(self, objet, e):
        if objet is self.champ and e.type() == e.Type.KeyPress and self._resultats:
            if e.key() in (Qt.Key_Down, Qt.Key_Up):
                pas = 1 if e.key() == Qt.Key_Down else -1
                self._choix = (self._choix + pas) % len(self._resultats)
                self._afficher_resultats()
                return True
        return super().eventFilter(objet, e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self.chat.isVisible():
                self.fermer_chat()
            elif self.pile.currentIndex() == 1:
                self.montrer_accueil()
            elif self.champ.text() or getattr(self, "_mode_epingle", False):
                self._fin_recherche()
            else:
                self.reduire.emit()
            return
        if e.text() and e.text().isprintable() and not self.champ.hasFocus() and self.pile.currentIndex() == 0 \
                and not self.chat.isVisible():
            self.champ.setFocus()
            self.champ.insert(e.text())
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if self.resultats.isVisible() and not self.resultats.geometry().contains(e.position().toPoint()):
            self._fin_recherche()
        super().mousePressEvent(e)
