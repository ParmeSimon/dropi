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
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedLayout, QAbstractButton,
                               QScrollArea, QMenu, QFrame, QSizePolicy)

import classement
import composants as ui
import donnees
import fichiers
import icones
import inventaire
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
    """Un thème : ce qui y est rangé, et ce qui l'attend encore sur le PC. Clic : ouvre le gestionnaire sur ce thème."""

    def __init__(self, dossier, parent=None):
        super().__init__(parent)
        self.dossier = dossier
        self.ranges, self.vrac, self.perso = None, 0, 0
        self.glyphe = ui.ICONES.get(themes.GLYPHES.get(dossier, "ouvrir"), "")
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def regler(self, ranges=None, vrac=None, perso=None):
        if ranges is not None:
            self.ranges = ranges
        if vrac is not None:
            self.vrac, self.perso = vrac, perso or 0
        self.update()

    def _texte(self):
        if self.ranges is None:
            return "…"
        morceaux = []
        if self.ranges:
            morceaux.append(f"{self.ranges} rangé{'s' if self.ranges > 1 else ''}")
        if self.vrac:
            morceaux.append(f"{self.vrac} à ranger")
        if self.perso:
            morceaux.append(f"{self.perso} dans tes dossiers")
        return "  ·  ".join(morceaux) or "vide"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        a = ui.accent()
        attend = bool(self.vrac) or (self.dossier.startswith("99") and bool(self.ranges))
        jaune = QColor(255, 196, 0)
        if self.underMouse():
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 190), 1.4))
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 30))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 30), 1))
            p.setBrush(ui.CARTE)
        p.drawRoundedRect(r, 14, 14)
        p.setPen(a)
        p.setFont(ui.police_icones(18))
        p.drawText(QRectF(12, 0, 28, self.height()), Qt.AlignCenter, self.glyphe)
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(13, True))
        p.drawText(QRectF(50, 9, self.width() - 58, 22), Qt.AlignLeft | Qt.AlignVCenter, themes.NOMS_THEMES.get(self.dossier, self.dossier))
        p.setPen(jaune if attend else ui.TEXTE_3)
        p.setFont(ui.police(11))
        p.drawText(QRectF(50, 30, self.width() - 58, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self._texte(), Qt.ElideRight, self.width() - 60))


class PuceFenetre(QAbstractButton):
    """Une fenêtre ouverte (ce que montrait la barre des tâches) : clic = la mettre devant, croix = la fermer."""
    fermer = Signal()
    HAUTEUR = 54

    def __init__(self, fenetre, parent=None):
        super().__init__(parent)
        self.fenetre = fenetre
        self.pix = icones.icone_fichier(fenetre["exe"], 48) if fenetre["exe"] else QPixmap()
        self.appli = os.path.splitext(os.path.basename(fenetre["exe"]))[0].replace("-", " ").replace("_", " ").title() if fenetre["exe"] else ""
        self.setFixedHeight(self.HAUTEUR)
        self.setMaximumWidth(270)
        self.setMinimumWidth(150)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self.setToolTip(fenetre["titre"])

    def sizeHint(self):
        largeur = QFontMetrics(ui.police(13, True)).horizontalAdvance(self.fenetre["titre"]) + 92
        return QSize(max(150, min(270, largeur)), self.HAUTEUR)

    def _croix(self):
        return QRectF(self.width() - 34, (self.height() - 26) / 2, 26, 26)

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
        r = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        survol = self.underMouse()
        a = ui.accent()
        if survol:
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 200), 1.4))
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 40))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
            p.setBrush(QColor(255, 255, 255, 24))
        p.drawRoundedRect(r, 14, 14)
        if not self.pix.isNull():
            p.setOpacity(0.55 if self.fenetre["reduite"] and not survol else 1.0)
            p.drawPixmap(QRectF(12, (self.height() - 30) / 2, 30, 30), self.pix, QRectF(self.pix.rect()))
            p.setOpacity(1.0)
        place = self.width() - 54 - (38 if survol else 12)
        p.setPen(ui.TEXTE)
        p.setFont(ui.police(13, True))
        p.drawText(QRectF(52, 8, place, 20), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.fenetre["titre"], Qt.ElideRight, int(place)))
        p.setPen(ui.TEXTE_3)
        p.setFont(ui.police(11))
        sous = self.appli + ("  ·  réduite" if self.fenetre["reduite"] else "")
        p.drawText(QRectF(52, 28, place, 18), Qt.AlignVCenter | Qt.AlignLeft, p.fontMetrics().elidedText(sous, Qt.ElideRight, int(place)))
        p.setPen(Qt.NoPen)                                   # le trait sous l'icône : fenêtre ouverte
        p.setBrush(QColor(a.red(), a.green(), a.blue(), 110 if self.fenetre["reduite"] else 255))
        p.drawRoundedRect(QRectF(20, self.height() - 6, 14, 3), 1.5, 1.5)
        if survol:
            croix = self._croix()
            sur_croix = croix.contains(QPointF(self.mapFromGlobal(self.cursor().pos())))
            p.setBrush(ui.ROUGE if sur_croix else QColor(255, 255, 255, 30))
            p.drawRoundedRect(croix, 8, 8)
            p.setPen(ui.TEXTE)
            p.setFont(ui.police_icones(9))
            p.drawText(croix, Qt.AlignCenter, ui.ICONES["fermer"])


class Dock(QFrame):
    """La bande des fenêtres ouvertes, en bas : un fond à part pour qu'on la voie tout de suite."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dock")
        self.setStyleSheet("#dock { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,38); border-radius: 20px; }")
        self.setFixedHeight(PuceFenetre.HAUTEUR + 22)
        self.rangee = QHBoxLayout(self)
        self.rangee.setContentsMargins(12, 10, 12, 10)
        self.rangee.setSpacing(8)
        self.rangee.setAlignment(Qt.AlignLeft)


class Horloge(QWidget):
    """L'heure en grand et la date. Mise à jour toutes les 20 secondes, seulement quand elle est visible."""
    JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setMinimumWidth(200)
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
    """Dropi, la mascotte du tableau de bord : en grand, en haut à gauche. Il te regarde, réagit quand tu le survoles ou
    le chatouilles, sa bulle dit ce qu'il fait. Clic : le tchat. Double-clic : on joue. Clic droit : tout ce qu'il sait
    faire. Un fichier déposé sur lui est rangé. Sous la bulle, ses actions rapides."""
    interaction = Signal(str)             # "survol", "clic", "double", "depot_survol" : pour qu'il réagisse
    action = Signal(str)                  # "jouer", "ranger_pc", "nouvelle", "capture", "reduire"
    fichiers = Signal(list)               # des fichiers déposés sur lui
    menu = Signal(object)

    def __init__(self, mascotte=None, rayon=38, parent=None):
        super().__init__(parent)
        self.rayon = rayon
        self.cote = round(rayon * 4.2)
        self.setFixedHeight(self.cote + 4)
        self.setMinimumWidth(self.cote + 210)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setAcceptDrops(True)
        self.texte, self.etat = "", "repos"
        self._depot = False
        self.vue = None
        self.plop = QPixmap()
        if mascotte is not None:
            self.vue = VueMascotte(mascotte, rayon, halo=True, parent=self)
            self.vue.move(0, 0)
            self.vue.setAttribute(Qt.WA_TransparentForMouseEvents)
        else:
            self.plop = QPixmap.fromImage(image_logo(256))
        # les actions rapides, sous la bulle
        self.barre = QWidget(self)
        rangee = QHBoxLayout(self.barre)
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(6)
        self.b_discuter = ui.Bouton("message", "Discuter", "accent", info="Ouvrir le tchat avec Dropi")
        self.b_discuter.clicked.connect(self.click)
        self.b_micro = ui.Bouton("micro", "", "puce", info="Maintiens pour lui parler")
        self.b_jouer = ui.Bouton("manette", "Jouer", "puce", info="Mini-jeux en 1 contre 1 (ou double-clic sur Dropi)")
        self.b_jouer.clicked.connect(lambda: self.action.emit("jouer"))
        self.b_ranger = ui.Bouton("ranger", "Ranger mon PC", "puce", info="Dropi range tout ce qui traîne, par thème")
        self.b_ranger.clicked.connect(lambda: self.action.emit("ranger_pc"))
        for b in (self.b_discuter, self.b_micro, self.b_jouer, self.b_ranger):
            rangee.addWidget(b)
        rangee.addStretch(1)
        self._textes = {self.b_jouer: "Jouer", self.b_ranger: "Ranger mon PC"}
        self.dire("")

    # ---- où est Plop
    def _centre(self):
        return QPoint(self.cote // 2, self.cote // 2)

    def centre_plop(self):
        """Le centre de Plop, dans les coordonnées du tableau de bord."""
        return QPointF(self.mapTo(self.window(), self._centre()))

    def centre_global(self):
        return QPointF(self.mapToGlobal(self._centre()))

    def dire(self, texte, etat="repos"):
        self.texte, self.etat = texte or self._accueil(), etat
        self.update()

    @staticmethod
    def _accueil():
        heure = time.localtime().tm_hour
        salut = "Bonjour" if 5 <= heure < 18 else ("Bonsoir" if heure < 23 else "Encore debout")
        return f"{salut} ! On discute ?"

    def resizeEvent(self, e):
        large = self.width() - self.cote >= 400
        for bouton, texte in self._textes.items():        # écran étroit : les boutons gardent juste leur icône
            bouton.setText(texte if large else "")
        self.barre.setGeometry(self.cote + 14, self.cote // 2 + 14, self.width() - self.cote - 14, 34)
        super().resizeEvent(e)

    # ---- interactions
    def enterEvent(self, e):
        self.interaction.emit("survol")
        super().enterEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.interaction.emit("clic")
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.interaction.emit("double")
            self.action.emit("jouer")

    def contextMenuEvent(self, e):
        self.menu.emit(e.globalPos())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._depot = True
            self.interaction.emit("depot_survol")
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self.update()

    def dragLeaveEvent(self, e):
        self._depot = False
        self.update()

    def dropEvent(self, e):
        self._depot = False
        chemins = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.setDropAction(Qt.CopyAction)          # jamais « déplacer » : l'Explorateur pourrait effacer l'original
        e.accept()
        self.update()
        if chemins:
            self.fichiers.emit(chemins)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._depot:                                    # un fichier arrive : l'anneau « donne-le-moi »
            a = ui.accent()
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 220), 2, Qt.DashLine))
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 26))
            c = QPointF(self._centre())
            p.drawEllipse(c, self.rayon * 1.75, self.rayon * 1.75)
        if self.vue is None and not self.plop.isNull():
            cote = self.rayon * 3.0
            p.drawPixmap(QRectF(self.cote / 2 - cote / 2, self.cote / 2 - cote / 2, cote, cote), self.plop, QRectF(self.plop.rect()))
        texte = "Lâche, je le range !" if self._depot else self.texte
        fonte = ui.police(13)
        x = self.cote + 14
        largeur = min(self.width() - x - 4, QFontMetrics(fonte).horizontalAdvance(texte) + 32)
        bulle = QRectF(x, self.cote / 2 - 38, max(70, largeur), 42)
        couleur = {"erreur": ui.ERREUR, "succes": ui.SUCCES}.get(self.etat)
        survol = self.underMouse()
        p.setPen(QPen(QColor(255, 255, 255, 80 if survol else 42), 1))
        p.setBrush(QColor(255, 255, 255, 30 if survol else 18))
        p.drawRoundedRect(bulle, 16, 16)
        queue = [QPointF(bulle.left() + 1, bulle.center().y() - 7), QPointF(bulle.left() - 9, bulle.center().y() + 2),
                 QPointF(bulle.left() + 1, bulle.center().y() + 7)]
        p.setPen(Qt.NoPen)
        p.drawPolygon(queue)
        p.setPen(couleur or ui.TEXTE)
        p.setFont(fonte)
        p.drawText(bulle.adjusted(16, 0, -14, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(fonte).elidedText(texte, Qt.ElideRight, int(bulle.width() - 30)))


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
    inventaire = Signal(dict)
    comptes = Signal(dict)
    applis = Signal(dict)
    index = Signal(list)


# ---------------------------------------------------------------- le tableau de bord
class Tableau(QWidget):
    reduire = Signal()                    # retour à la goutte
    demande = Signal(str)                 # une phrase pour Dropi (tapée dans la recherche ou dans le tchat)
    veut_fil = Signal()                   # le tchat s'ouvre : il lui faut le fil de la conversation
    actif = Signal(bool)                  # le tableau de bord passe devant / derrière
    action = Signal(str)                  # une action de Dropi : "jouer", "nouvelle", "capture"…
    ranger_pc = Signal(list)              # « Ranger mon PC » : les fichiers en vrac que l'inventaire a trouvés
    fichiers_deposes = Signal(list)       # des fichiers lâchés sur Dropi
    jeu = Signal(str)                     # lancer un jeu
    dossier = Signal(str)                 # ouvrir le gestionnaire de fichiers sur ce dossier

    def __init__(self, mascotte=None, hauteur=None, parent=None):
        """hauteur : celle de l'écran où il s'affichera (un petit écran a droit à un Dropi un peu moins grand)."""
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
        self._pont.inventaire.connect(self._inventaire_pret)
        self._inventaire, self._inventaire_en_cours = {"fichiers": [], "dossiers": [], "date": 0.0}, False
        self._a_charger = []
        self._chargeur = QTimer(self, interval=0, timeout=self._charger_une_icone)
        self._veille = QTimer(self, interval=2000, timeout=self._maj_fenetres)
        self._signature_fenetres = None

        racine = QVBoxLayout(self)
        racine.setContentsMargins(MARGE, 18, MARGE, 22)
        racine.setSpacing(0)

        # ---- le haut : Dropi à gauche, « Réduire » et la recherche au milieu, l'heure à droite
        ecran = QApplication.primaryScreen()
        if hauteur is None and ecran is not None:
            hauteur = ecran.geometry().height()
        petit = (hauteur or 900) < 800
        haut = QHBoxLayout()
        haut.setSpacing(0)
        self.coin = CoinDropi(mascotte, 28 if petit else 38)
        self.coin.clicked.connect(self.basculer_chat)
        self.coin.action.connect(self._action_dropi)
        self.coin.fichiers.connect(self.fichiers_deposes.emit)
        self.coin.menu.connect(self._menu_dropi)
        haut.addWidget(self.coin, 0, Qt.AlignLeft | Qt.AlignTop)
        haut.addStretch(1)
        centre = QVBoxLayout()
        centre.setSpacing(14)
        self.pastille = PastilleReduire()
        self.pastille.clicked.connect(self.reduire.emit)
        centre.addWidget(self.pastille, 0, Qt.AlignHCenter)
        self.champ = ui.Champ("Lance une appli, un jeu, un fichier… ou demande à Dropi")
        self.champ.setFixedHeight(46)
        self.champ.setFont(ui.police(14))
        self.champ.textChanged.connect(self._chercher)
        self.champ.returnPressed.connect(self._valider)
        self.champ.installEventFilter(self)
        centre.addWidget(self.champ)
        centre.addStretch(1)
        haut.addLayout(centre)
        haut.addStretch(1)
        self.horloge = Horloge()
        haut.addWidget(self.horloge, 0, Qt.AlignRight | Qt.AlignTop)
        racine.addLayout(haut)
        racine.addSpacing(14)
        self.pile = QStackedLayout()
        racine.addLayout(self.pile, 1)
        accueil = QWidget()
        corps = QVBoxLayout(accueil)
        corps.setContentsMargins(0, 0, 0, 0)
        corps.setSpacing(0)
        self.pile.addWidget(accueil)
        self.gestionnaire = fichiers.Gestionnaire()
        self.gestionnaire.retour.connect(self.montrer_accueil)
        self.gestionnaire.change.connect(lambda: self.inventorier(force=True))
        self.pile.addWidget(self.gestionnaire)

        # ---- le milieu : deux colonnes, dans une zone qui ne pousse jamais la bande du bas hors de l'écran
        self.zone_milieu = QWidget()
        self.zone_milieu.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        milieu = QHBoxLayout(self.zone_milieu)
        milieu.setContentsMargins(0, 0, 0, 0)
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
        self.btn_ranger = ui.Bouton("ranger", "Ranger mon PC", "accent", info="Dropi range tout ce qui traîne, par thème (rien ne bouge avant ton accord)")
        self.btn_ranger.clicked.connect(self.demander_rangement)
        self.btn_ranger.hide()
        entete_fichiers.addWidget(self.btn_ranger)
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
        self.titre_recents = ui.TitreSection(4, "Rangés récemment", "horloge")
        colonne.addWidget(self.titre_recents)
        self.recents = QVBoxLayout()
        self.recents.setSpacing(4)
        colonne.addLayout(self.recents)
        colonne.addStretch(1)
        milieu.addLayout(colonne, 2)
        corps.addWidget(self.zone_milieu, 1)

        # ---- le bas : les fenêtres ouvertes (ce que montrait la barre des tâches), dans une bande bien visible
        corps.addSpacing(10)
        self.titre_fenetres = ui.TitreSection(5, "Fenêtres ouvertes", "pc")
        corps.addWidget(self.titre_fenetres)
        corps.addSpacing(8)
        self.dock = Dock()
        self.bande = self.dock.rangee
        corps.addWidget(self.dock)

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
        haut = 18 + self.coin.height() + 6
        hauteur = max(300, min(680, self.height() - haut - 28))
        self.chat.setGeometry(MARGE, haut, ui.LARGEUR_FIL + 36, hauteur)

    def _action_dropi(self, quoi):
        if quoi == "ranger_pc":
            self.demander_rangement()
        else:
            self.action.emit(quoi)

    def _menu_dropi(self, position):
        """Clic droit sur Dropi : tout ce qu'on peut lui demander d'ici."""
        menu = QMenu(self)
        menu.addAction("Discuter", self.ouvrir_chat)
        menu.addAction("Jouer avec Dropi", lambda: self.action.emit("jouer"))
        menu.addSeparator()
        menu.addAction("Ranger mon PC", self.demander_rangement)
        menu.addAction("Ranger mes téléchargements", lambda: self.demande.emit("range mes téléchargements"))
        menu.addAction("Faire de la place sur le disque", lambda: self.demande.emit("fais de la place"))
        menu.addAction("Lire du texte à l'écran", lambda: self.action.emit("capture"))
        menu.addSeparator()
        menu.addAction("Minuteur 5 minutes", lambda: self.demande.emit("minuteur 5 minutes"))
        menu.addAction("Verrouiller le PC", lambda: self.demande.emit("verrouille le pc"))
        menu.addSeparator()
        menu.addAction("Nouvelle conversation", lambda: self.action.emit("nouvelle"))
        menu.addAction("Réduire en goutte", self.reduire.emit)
        menu.exec(position)

    # ------------------------------------------------------------ l'inventaire du PC
    def inventorier(self, force=False):
        """Regarde ce qu'il y a vraiment sur le PC (dans un fil de fond), au plus toutes les 5 minutes."""
        if self._inventaire_en_cours or (not force and time.time() - self._inventaire.get("date", 0) < 300):
            return
        self._inventaire_en_cours = True

        def travail():
            try:
                resultat = inventaire.faire()
            except Exception:
                resultat = {"fichiers": [], "dossiers": [], "date": time.time()}
            self._pont.inventaire.emit(resultat)

        threading.Thread(target=travail, daemon=True).start()

    def _inventaire_pret(self, resultat):
        self._inventaire, self._inventaire_en_cours = resultat, False
        comptes = inventaire.comptes(resultat)
        for dossier, (vrac, perso) in comptes.items():
            if dossier in self.cartes:
                self.cartes[dossier].regler(vrac=vrac, perso=perso)
        en_vrac = sum(v for v, _ in comptes.values())
        self.btn_ranger.setVisible(en_vrac > 0)
        self.btn_ranger.setText(f"Ranger mon PC ({en_vrac})")
        self.btn_ranger.updateGeometry()
        self.gestionnaire.regler_inventaire(resultat)
        # la recherche trouve aussi ces fichiers-là, où qu'ils soient
        deja = {c for _, c in self._index}
        self._index += [(themes.simple(os.path.basename(f["chemin"])), f["chemin"]) for f in resultat["fichiers"] if f["chemin"] not in deja]

    def en_vrac(self):
        return [f["chemin"] for f in self._inventaire.get("fichiers", []) if f["vrac"]]

    def demander_rangement(self):
        """« Ranger mon PC » : Dropi prépare le plan et le montre dans le tchat. Rien ne bouge avant ton accord."""
        chemins = self.en_vrac()
        if chemins:
            self.ranger_pc.emit(chemins)
        else:
            self.dire("Rien ne traîne : tout est déjà rangé.", "succes")

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
        # Dropi à gauche et l'heure à droite ont la même largeur : la recherche reste au milieu de l'écran
        cote = max(self.coin.minimumWidth(), min(560, (self.width() - 2 * MARGE - 640) // 2))
        self.coin.setFixedWidth(cote)
        self.horloge.setFixedWidth(cote)
        self.champ.setFixedWidth(max(300, min(620, self.width() - 2 * MARGE - 2 * cote - 20)))
        super().resizeEvent(e)
        self._placer_resultats()
        if hasattr(self, "chat"):
            self._placer_chat()
        QTimer.singleShot(0, self._adapter)

    def _adapter(self):
        """Petit écran : on montre moins de lignes plutôt que de laisser le bas sortir de l'écran."""
        self._construire_recents()
        self._signature_fenetres = None
        self._maj_fenetres()

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
        self.inventorier()
        threading.Thread(target=self._compter, daemon=True).start()
        if time.monotonic() - self._index_date > 120:
            threading.Thread(target=self._indexer, daemon=True).start()

    def montrer_fichiers(self, dossier=None):
        """Passe au gestionnaire de fichiers (sur un thème, ou sur tous les fichiers)."""
        self._fin_recherche()
        self.fermer_chat()
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
        rangees = 3 if self.height() >= 980 else 2
        self._tuiles = []
        for i, appli in enumerate(self._epingles[:colonnes * rangees - 1]):
            tuile = TuileAppli(appli)
            tuile.clicked.connect(lambda _=False, a=appli: lancer_appli(a["nom"], a["id"]))
            tuile.menu.connect(lambda pos, a=appli: self._menu_appli(a, pos))
            self.grille_applis.addWidget(tuile, i // colonnes, i % colonnes)
            self._tuiles.append(tuile)
            if icones.deja_prete(appli["id"], 64):         # déjà en cache : tout de suite (l'animation d'ouverture la montre)
                tuile.pix = icones.icone_appli(appli["id"], 64)
        if len(self._tuiles) < colonnes * rangees:
            plus = TuilePlus()
            plus.clicked.connect(self._choisir_appli)
            n = len(self._tuiles)
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
                self.cartes[dossier].regler(ranges=n)

    def _construire_recents(self):
        while self.recents.count():
            w = self.recents.takeAt(0).widget()
            if w:
                w.deleteLater()
        # la place qui reste sous les 8 cartes de thèmes (4 rangées de 58 + titres) : 46 px par ligne
        place = max(0, min(6, (self.zone_milieu.height() - 366) // 46)) if self.zone_milieu.height() > 50 else 4
        self.titre_recents.setVisible(place > 0)
        if not place:
            return
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
            if lignes >= place:
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
        self.titre_fenetres.texte = f"05 — FENÊTRES OUVERTES  ·  {len(liste)}"
        self.titre_fenetres.update()
        if not liste:
            vide = ui.Etiquette("Aucune fenêtre ouverte. Lance une appli : elle apparaîtra ici, un clic la ramènera devant.", 12, ui.TEXTE_3)
            self.bande.addWidget(vide)
            return
        place = self.width() - 2 * MARGE - 24
        montrees = 0
        for f in liste:
            puce = PuceFenetre(f)
            largeur = puce.sizeHint().width() + 8
            if place - largeur < (70 if montrees < len(liste) - 1 else 0):      # on garde la place du « +N »
                puce.deleteLater()
                break
            place -= largeur
            puce.clicked.connect(lambda _=False, h=f["hwnd"]: systeme.activer(h))
            puce.fermer.connect(lambda h=f["hwnd"]: (systeme.fermer(h), QTimer.singleShot(400, self._maj_fenetres)))
            self.bande.addWidget(puce)
            montrees += 1
        if montrees < len(liste):
            reste = ui.Etiquette(f"+ {len(liste) - montrees}", 13, ui.TEXTE_2, gras=True)
            reste.setToolTip("\n".join(f["titre"] for f in liste[montrees:]))
            self.bande.addWidget(reste)

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
