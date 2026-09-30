"""Les briques visuelles de l'île, style Windows 11 (Fluent).

Tout est dessiné à la main avec l'anticrénelage : les coins arrondis
des feuilles de style Qt sont crénelés (bords « en escalier »).
"""
import math
from pathlib import Path

from PySide6.QtCore import (Qt, QRectF, QPointF, QSize, Signal, QFileInfo, QVariantAnimation,
                            QEasingCurve)
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QFont, QPen, QBrush, QPalette,
                           QLinearGradient, QPixmap, QTextDocument, QImageReader, QTransform,
                           QTextCursor, QTextBlockFormat, QIcon, QImage)
from PySide6.QtWidgets import (QApplication, QAbstractButton, QLineEdit, QWidget, QLabel,
                               QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QFileIconProvider, QTextBrowser)

# ------------------------------------------------------------------ Couleurs (thème sombre Fluent)

TEXTE = QColor(255, 255, 255)
TEXTE_2 = QColor(255, 255, 255, 200)
TEXTE_3 = QColor(255, 255, 255, 135)
CARTE = QColor(255, 255, 255, 14)
CARTE_SURVOL = QColor(255, 255, 255, 24)
CARTE_APPUI = QColor(255, 255, 255, 9)
CONTOUR = QColor(255, 255, 255, 20)
SUCCES = QColor("#6CCB5F")
ERREUR = QColor("#FF99A4")
ROUGE = QColor("#F0524F")


def accent():
    """Couleur d'accentuation choisie dans les paramètres Windows."""
    c = QApplication.palette().color(QPalette.Accent)
    return c if c.isValid() and c.lightness() > 60 else QColor("#60CDFF")


def teinte(couleur, decalage):
    h, s, v, a = couleur.getHsv()
    return QColor.fromHsv((max(h, 0) + decalage) % 360, s, v, a)


# ------------------------------------------------------------------ Polices et icônes

ICONES = {
    "micro": "", "envoyer": "", "fermer": "", "ok": "",
    "ranger": "", "ouvrir": "", "deplacer": "", "supprimer": "",
    "explorateur": "", "deposer": "", "erreur": "", "reduire": "",
    "nouveau": "", "reglage": "", "jouer": "", "manette": "", "mail": "", "web": "",
    "disque": "", "balai": "", "horloge": "", "doublon": "", "paquet": "",
    "annuler": "", "dossier_ouvert": "", "telechargement": "", "bureau": "",
}
ICONES.update(note=chr(0xEC4F), pause=chr(0xE769))


def police(taille, gras=False, famille="Segoe UI Variable Text"):
    f = QFont()
    f.setFamilies([famille, "Segoe UI"])
    f.setPixelSize(taille)
    f.setWeight(QFont.DemiBold if gras else QFont.Normal)
    return f


def police_icones(taille):
    f = QFont()
    f.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
    f.setPixelSize(taille)
    return f


def forme_arrondie(rect, rayon):
    chemin = QPainterPath()
    chemin.addRoundedRect(rect, rayon, rayon)
    return chemin


# ------------------------------------------------------------------ Dessins partagés

def dessiner_ombre(p, chemin, etendue=16.0, decalage=5.0, opacite=0.42, couches=9):
    """Ombre douce façon Fluent sous n'importe quelle forme : couches de plus en plus serrées."""
    alpha = 1 - (1 - opacite) ** (1 / couches)
    couleur = QColor(0, 0, 0, round(alpha * 255))
    p.save()
    p.translate(0, decalage)
    p.setBrush(couleur)
    for i in range(couches):
        s = etendue * (1 - i / couches) ** 1.6
        stylo = QPen(couleur, 2 * s)
        stylo.setJoinStyle(Qt.RoundJoin)
        p.setPen(stylo)
        p.drawPath(chemin)
    p.restore()


def remplissage_ile(rect):
    """Le dégradé du fond de l'île (partagé avec le voile de fondu)."""
    fond = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    fond.setColorAt(0, QColor(38, 38, 41, 250))
    fond.setColorAt(1, QColor(23, 23, 26, 250))
    return fond


class Voile(QWidget):
    """Recouvre un panneau qui apparaît puis s'efface : un fondu propre.

    (QGraphicsOpacityEffect rendait le panneau transparent une fraction de seconde :
    on voyait l'écran derrière.)
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()
        self.opacite = 1.0
        self.forme = QRectF()
        self.rayon = 20
        self.anim = QVariantAnimation(self, duration=190, startValue=1.0, endValue=0.0,
                                      easingCurve=QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._valeur)
        self.anim.finished.connect(self.hide)

    def couvrir(self, rect, rayon):
        self.forme, self.rayon = QRectF(rect), rayon
        self.setGeometry(rect.toAlignedRect())
        self.opacite = 1.0
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.start()

    def _valeur(self, v):
        self.opacite = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self.opacite)
        r = QRectF(self.forme).translated(-self.x(), -self.y()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(Qt.NoPen)
        p.setBrush(remplissage_ile(QRectF(self.forme).translated(-self.x(), -self.y())))
        p.drawRoundedRect(r, self.rayon - 1.5, self.rayon - 1.5)


# ------------------------------------------------------------------ Boutons

class Bouton(QAbstractButton):
    """Bouton Fluent dessiné à la main.

    genre : "icone" (rond), "puce" (icône + texte), "accent" (rempli de la couleur d'accent).
    """

    def __init__(self, icone="", texte="", genre="icone", info="", parent=None):
        super().__init__(parent)
        self.icone = ICONES.get(icone, icone)
        self.setText(texte)
        self.genre = genre
        self.danger = False
        self.setToolTip(info)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setFont(police(13))

    def sizeHint(self):
        if self.genre == "icone":
            return QSize(34, 34)
        if not self.text():
            return QSize(32, 32)
        largeur = self.fontMetrics().horizontalAdvance(self.text()) + 26
        if self.icone:
            largeur += 22
        return QSize(largeur, 32)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        survol = self.underMouse() and self.isEnabled()
        appui = self.isDown()

        if self.danger:
            fond, encre = (ROUGE.darker(115) if appui else ROUGE), QColor(255, 255, 255)
        elif self.genre == "accent":
            a = accent()
            fond = a.darker(112) if appui else (a.lighter(108) if survol else a)
            encre = QColor(0, 0, 0)
        else:
            fond = CARTE_APPUI if appui else (CARTE_SURVOL if survol else CARTE)
            if self.genre == "icone" and not survol and not appui:
                fond = QColor(0, 0, 0, 0)
            encre = TEXTE_2 if appui else TEXTE

        p.setPen(QPen(CONTOUR, 1) if self.genre == "puce" and not self.danger else Qt.NoPen)
        p.setBrush(fond)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if not self.isEnabled():
            encre = TEXTE_3

        p.setPen(encre)
        if self.genre == "icone" or not self.text():
            p.setFont(police_icones(15 if self.genre == "icone" else 14))
            p.drawText(r, Qt.AlignCenter, self.icone)
            return
        x = 13
        if self.icone:
            p.setFont(police_icones(14))
            p.drawText(QRectF(x, 0, 16, self.height()), Qt.AlignCenter, self.icone)
            x += 22
        p.setFont(self.font())
        p.drawText(QRectF(x, 0, self.width() - x, self.height()), Qt.AlignVCenter, self.text())


# ------------------------------------------------------------------ Zone de saisie

class Champ(QLineEdit):
    def __init__(self, indication="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(indication)
        self.setFont(police(13))
        self.setFixedHeight(38)
        self.setTextMargins(14, 0, 14, 0)
        self.setAttribute(Qt.WA_Hover)
        pal = self.palette()
        pal.setColor(QPalette.PlaceholderText, TEXTE_3)
        pal.setColor(QPalette.Text, TEXTE)
        pal.setColor(QPalette.Highlight, accent())
        pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        self.setPalette(pal)
        self.setStyleSheet("QLineEdit { background: transparent; border: none; }")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        focus = self.hasFocus()
        p.setBrush(QColor(0, 0, 0, 90) if focus else (CARTE_SURVOL if self.underMouse() else CARTE))
        a = accent()
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 170) if focus else CONTOUR, 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.end()
        super().paintEvent(e)


def barre_saisie(indication, parent=None):
    """Champ + micro + envoyer, en ligne."""
    barre = QWidget(parent)
    lay = QHBoxLayout(barre)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    champ = Champ(indication)
    micro = Bouton("micro", info="Maintiens pour parler")
    envoyer = Bouton("envoyer", genre="icone", info="Envoyer")
    lay.addWidget(champ, 1)
    lay.addWidget(micro)
    lay.addWidget(envoyer)
    return barre, champ, micro, envoyer


# ------------------------------------------------------------------ Textes

class Etiquette(QLabel):
    def __init__(self, texte="", taille=13, couleur=TEXTE, gras=False, parent=None):
        super().__init__(texte, parent)
        self.setFont(police(taille, gras))
        pal = self.palette()
        pal.setColor(QPalette.WindowText, couleur)
        pal.setColor(QPalette.Text, couleur)
        pal.setColor(QPalette.Link, accent())
        self.setPalette(pal)


class EtiquetteCoupee(Etiquette):
    """Une ligne de texte qui se termine par « … » si elle est trop longue."""

    def __init__(self, texte="", **kw):
        super().__init__(texte, **kw)
        self._complet = texte

    def setText(self, texte):
        self._complet = texte
        self._couper()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._couper()

    def _couper(self):
        QLabel.setText(self, self.fontMetrics().elidedText(self._complet, Qt.ElideMiddle, self.width()))

    def minimumSizeHint(self):
        return QSize(20, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self._complet), super().sizeHint().height())


# ------------------------------------------------------------------ Fichiers déposés

def taille_lisible(octets):
    for unite in ("o", "Ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}".replace(".", ",")
        octets /= 1024


def vignette(chemin, cote=36):
    """Aperçu arrondi pour une image, sinon l'icône Windows du fichier."""
    src = QPixmap()
    lecteur = QImageReader(chemin)
    if Path(chemin).is_file() and Path(chemin).stat().st_size < 40_000_000 and lecteur.canRead():
        taille = lecteur.size()
        if taille.isValid():
            taille.scale(cote * 2, cote * 2, Qt.KeepAspectRatioByExpanding)
            lecteur.setScaledSize(taille)
        image = lecteur.read()
        if not image.isNull():
            src = QPixmap.fromImage(image)
    if src.isNull():
        return QFileIconProvider().icon(QFileInfo(chemin)).pixmap(32, 32)

    ratio = 2.0
    sortie = QPixmap(round(cote * ratio), round(cote * ratio))
    sortie.fill(Qt.transparent)
    p = QPainter(sortie)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    echelle = max(sortie.width() / src.width(), sortie.height() / src.height())
    pinceau = QBrush(src)
    pinceau.setTransform(QTransform().translate((sortie.width() - src.width() * echelle) / 2,
                                                (sortie.height() - src.height() * echelle) / 2)
                         .scale(echelle, echelle))
    p.setPen(Qt.NoPen)
    p.setBrush(pinceau)
    p.drawRoundedRect(QRectF(sortie.rect()), 7 * ratio, 7 * ratio)
    p.end()
    sortie.setDevicePixelRatio(ratio)
    return sortie


class LigneFichier(QWidget):
    retire = Signal(str)

    def __init__(self, chemin, destination="", parent=None):
        super().__init__(parent)
        self.chemin = chemin
        self.setFixedHeight(50)
        info = Path(chemin)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 7, 6, 7)
        lay.setSpacing(10)

        icone = QLabel()
        icone.setFixedSize(36, 36)
        icone.setAlignment(Qt.AlignCenter)
        icone.setPixmap(vignette(chemin))
        lay.addWidget(icone)

        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(EtiquetteCoupee(info.name, taille=13, gras=True))
        try:
            details = "Dossier" if info.is_dir() else taille_lisible(info.stat().st_size)
        except OSError:
            details = "Introuvable"
        suite = f"→ {destination}" if destination else str(info.parent)
        textes.addWidget(EtiquetteCoupee(f"{details}  ·  {suite}", taille=12, couleur=TEXTE_3))
        lay.addLayout(textes, 1)

        retirer = Bouton("fermer", info="Retirer")
        retirer.setFixedSize(28, 28)
        retirer.clicked.connect(lambda: self.retire.emit(self.chemin))
        lay.addWidget(retirer)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(CONTOUR, 1))
        p.setBrush(CARTE)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)


# ------------------------------------------------------------------ Conversation

LARGEUR_BULLE = 360
LARGEUR_FIL = 492          # largeur utile du fil de discussion (cartes, grilles)


def largeur_ideale(texte, fonte, markdown, maxi=LARGEUR_BULLE):
    """Largeur qu'un texte occupe vraiment (sinon Qt coupe les lignes beaucoup trop tôt)."""
    doc = QTextDocument()
    doc.setDefaultFont(fonte)
    doc.setDocumentMargin(0)
    doc.setMarkdown(texte) if markdown else doc.setPlainText(texte)
    doc.setTextWidth(maxi)
    return min(math.ceil(doc.idealWidth()) + 4, maxi)


def ligne_icone(glyphe, texte, couleur, taille=12, largeur=None):
    """Une icône Fluent suivie d'un texte (chacun dans sa police)."""
    ligne = QWidget()
    lay = QHBoxLayout(ligne)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(7)
    icone = Etiquette(glyphe, couleur=couleur)
    icone.setFont(police_icones(taille))
    icone.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
    icone.setContentsMargins(0, 2, 0, 0)
    lay.addWidget(icone)
    corps = Etiquette(texte, taille, couleur)
    corps.setWordWrap(True)
    if largeur:
        corps.setFixedWidth(largeur_ideale(texte, corps.font(), False, largeur))
    lay.addWidget(corps, 1)
    return ligne


class Bulle(QWidget):
    """Ton message : bulle de la couleur d'accentuation, à droite."""

    def __init__(self, texte, piece="", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 8, 13, 9)
        lay.setSpacing(4)
        if piece:
            lay.addWidget(ligne_icone(ICONES["ouvrir"], piece, QColor(0, 0, 0, 170), largeur=LARGEUR_BULLE - 20))
        if texte:
            corps = Etiquette(texte, couleur=QColor(0, 0, 0))
            corps.setWordWrap(True)
            corps.setTextFormat(Qt.PlainText)
            corps.setFixedWidth(largeur_ideale(texte, corps.font(), False))
            corps.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(corps)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        grand, petit = 16.0, 5.0
        c = QPainterPath(QPointF(r.left() + grand, r.top()))
        c.lineTo(r.right() - grand, r.top())
        c.quadTo(r.right(), r.top(), r.right(), r.top() + grand)
        c.lineTo(r.right(), r.bottom() - petit)
        c.quadTo(r.right(), r.bottom(), r.right() - petit, r.bottom())
        c.lineTo(r.left() + grand, r.bottom())
        c.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - grand)
        c.lineTo(r.left(), r.top() + grand)
        c.quadTo(r.left(), r.top(), r.left() + grand, r.top())
        a = accent()
        fond = QLinearGradient(r.topLeft(), r.bottomRight())
        fond.setColorAt(0, a.lighter(106))
        fond.setColorAt(1, a.darker(104))
        p.fillPath(c, fond)


class TexteRiche(QTextBrowser):
    """Réponse de l'assistant : Markdown mis en page (listes, gras, liens), sans bulle."""

    def __init__(self, texte, largeur_max=LARGEUR_FIL - 20, couleur=TEXTE, parent=None):
        super().__init__(parent)
        self.setFrameShape(QTextBrowser.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self.viewport().setAutoFillBackground(False)
        pal = self.palette()
        pal.setColor(QPalette.Text, couleur)
        pal.setColor(QPalette.Link, accent())
        pal.setColor(QPalette.Highlight, accent())
        pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        self.setPalette(pal)

        doc = self.document()
        doc.setDocumentMargin(0)
        doc.setIndentWidth(18)
        doc.setDefaultFont(police(13))
        doc.setDefaultStyleSheet(f"a {{ color: {accent().name()}; text-decoration: none; }}")
        self.setMarkdown(texte.strip())
        curseur = QTextCursor(doc)
        curseur.select(QTextCursor.Document)
        interligne = QTextBlockFormat()
        interligne.setLineHeight(138, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        curseur.mergeBlockFormat(interligne)

        doc.setTextWidth(largeur_max)
        largeur = min(math.ceil(doc.idealWidth()) + 4, largeur_max)
        doc.setTextWidth(largeur)
        self.setFixedSize(largeur, math.ceil(doc.size().height()) + 2)

    def wheelEvent(self, e):
        e.ignore()          # laisse défiler le fil


class PuceAction(QWidget):
    """Ce que l'assistant est en train de faire : engrenage en cours, coche finie, ! ratée."""

    def __init__(self, texte, sur_clic=None, parent=None):
        super().__init__(parent)
        self.texte = texte
        self.etat = "encours"
        self.sur_clic = sur_clic
        if sur_clic:
            self.setCursor(Qt.PointingHandCursor)
        self.setFont(police(12))
        self.setToolTip(texte)
        largeur = min(self.fontMetrics().horizontalAdvance(texte) + 44, LARGEUR_FIL)
        self.setFixedSize(largeur, 26)

    def terminer(self, ok=True):
        self.etat = "ok" if ok else "erreur"
        self.update()
        return self

    def mouseReleaseEvent(self, e):
        if self.sur_clic and self.rect().contains(e.position().toPoint()):
            self.sur_clic()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(CONTOUR, 1))
        p.setBrush(CARTE)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        glyphe, couleur = {"encours": (ICONES["reglage"], TEXTE_3), "ok": (ICONES["ok"], SUCCES),
                           "erreur": (ICONES["erreur"], ERREUR)}[self.etat]
        p.setPen(couleur)
        p.setFont(police_icones(12))
        p.drawText(QRectF(10, 0, 16, self.height()), Qt.AlignCenter, glyphe)
        p.setPen(TEXTE_2 if self.etat != "erreur" else ERREUR)
        p.setFont(self.font())
        texte = self.fontMetrics().elidedText(self.texte, Qt.ElideRight, self.width() - 44)
        p.drawText(QRectF(32, 0, self.width() - 40, self.height()), Qt.AlignVCenter, texte)


# ------------------------------------------------------------------ Jeux

_images = {}


def image_couverte(chemin, largeur, hauteur):
    """Charge une image recadrée pour remplir exactement largeur x hauteur (mise en cache)."""
    cle = (str(chemin), largeur, hauteur)
    if cle not in _images:
        ratio = 2
        lecteur = QImageReader(str(chemin))
        taille = lecteur.size()
        if taille.isValid():
            taille.scale(largeur * ratio, hauteur * ratio, Qt.KeepAspectRatioByExpanding)
            lecteur.setScaledSize(taille)
        image = lecteur.read()
        if image.isNull():
            _images[cle] = None
        else:
            x = (image.width() - largeur * ratio) // 2
            y = (image.height() - hauteur * ratio) // 2
            _images[cle] = QPixmap.fromImage(image.copy(x, y, largeur * ratio, hauteur * ratio))
    return _images[cle]


def pixmap_icone(chemin, taille):
    if not chemin:
        return QPixmap()
    if str(chemin).lower().endswith(".ico"):
        icone = QIcon(str(chemin))
    else:
        icone = QFileIconProvider().icon(QFileInfo(str(chemin)))
    return icone.pixmap(taille, taille)


def couleur_moyenne(pixmap):
    if pixmap.isNull():
        return accent()
    c = QColor(pixmap.toImage().scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixel(0, 0))
    h, s, v, _ = c.getHsv()
    return QColor.fromHsv(max(h, 0), min(255, s + 40), max(90, min(v, 170)))


def peindre_image(p, pixmap, rect, rayon):
    """Dessine une image dans un rectangle aux coins arrondis, bords lisses."""
    pinceau = QBrush(pixmap)
    pinceau.setTransform(QTransform().translate(rect.x(), rect.y())
                         .scale(rect.width() / pixmap.width(), rect.height() / pixmap.height()))
    p.setPen(Qt.NoPen)
    p.setBrush(pinceau)
    p.drawRoundedRect(rect, rayon, rayon)


class TuileJeu(QAbstractButton):
    """Une jaquette de jeu cliquable (au survol elle se soulève et affiche « Jouer »)."""

    def __init__(self, jeu, largeur, parent=None):
        super().__init__(parent)
        self.jeu = jeu
        self.l, self.h = largeur, round(largeur * 1.5)
        self.setFixedSize(self.l, self.h + 22)
        self.setAttribute(Qt.WA_Hover)
        self.setToolTip(f"Lancer {jeu['nom']}")
        self.jaquette = image_couverte(jeu["jaquette"], self.l, self.h) if jeu.get("jaquette") else None
        self.icone = QPixmap() if self.jaquette else pixmap_icone(jeu.get("icone"), 128)
        self.teinte = couleur_moyenne(self.icone)
        self.survol = 0.0
        self.anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._sur_anim)

    def _sur_anim(self, v):
        self.survol = v
        self.update()

    def _animer(self, vers):
        self.anim.stop()
        self.anim.setStartValue(self.survol)
        self.anim.setEndValue(vers)
        self.anim.start()

    def enterEvent(self, e):
        self._animer(1.0)

    def leaveEvent(self, e):
        self._animer(0.0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        marge = 3 * (1 - self.survol)
        r = QRectF(marge, marge, self.l - 2 * marge, self.h - 2 * marge)
        rayon = 9
        if self.jaquette:
            peindre_image(p, self.jaquette, r, rayon)
        else:
            fond = QLinearGradient(r.topLeft(), r.bottomRight())
            fond.setColorAt(0, self.teinte.lighter(115))
            fond.setColorAt(1, self.teinte.darker(260))
            p.setPen(Qt.NoPen)
            p.setBrush(fond)
            p.drawRoundedRect(r, rayon, rayon)
            if not self.icone.isNull():
                cote = r.width() * 0.5
                p.drawPixmap(QRectF(r.center().x() - cote / 2, r.top() + r.height() * 0.32 - cote / 2, cote, cote),
                             self.icone, QRectF(self.icone.rect()))
            p.setPen(TEXTE)
            p.setFont(police(12, gras=True))
            p.drawText(r.adjusted(8, r.height() * 0.58, -8, -8), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       self.jeu["nom"])
        if self.survol > 0.01:
            voile = QLinearGradient(r.topLeft(), r.bottomLeft())
            voile.setColorAt(0.35, QColor(0, 0, 0, 0))
            voile.setColorAt(1, QColor(0, 0, 0, round(190 * self.survol)))
            p.setBrush(voile)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, rayon, rayon)
            a = accent()
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), round(255 * self.survol)), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), rayon, rayon)
            centre = QPointF(r.center().x(), r.bottom() - 26)
            p.setPen(Qt.NoPen)
            couleur = QColor(a)
            couleur.setAlphaF(self.survol)
            p.setBrush(couleur)
            p.drawEllipse(centre, 15 * self.survol, 15 * self.survol)
            p.setPen(QColor(0, 0, 0, round(230 * self.survol)))
            p.setFont(police_icones(13))
            p.drawText(QRectF(centre.x() - 14, centre.y() - 15, 30, 30), Qt.AlignCenter, ICONES["jouer"])
        p.setPen(TEXTE if self.survol > 0.5 else TEXTE_2)
        p.setFont(police(11, gras=self.survol > 0.5))
        nom = p.fontMetrics().elidedText(self.jeu["nom"], Qt.ElideRight, self.l - 4)
        p.drawText(QRectF(0, self.h + 3, self.l, 18), Qt.AlignHCenter | Qt.AlignVCenter, nom)


class GrilleJeux(QWidget):
    """Ta bibliothèque de jeux, façon lanceur."""
    lancer = Signal(str)

    def __init__(self, jeux, largeur=LARGEUR_FIL, colonnes=5, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)
        lay.addWidget(ligne_icone(ICONES["manette"], f"Ta bibliothèque  ·  {len(jeux)} jeux", TEXTE_2, taille=12))
        grille = QGridLayout()
        grille.setContentsMargins(0, 0, 0, 0)
        espace = 8
        grille.setHorizontalSpacing(espace)
        grille.setVerticalSpacing(10)
        largeur_tuile = (largeur - espace * (colonnes - 1)) // colonnes
        for i, jeu in enumerate(jeux):
            tuile = TuileJeu(jeu, largeur_tuile)
            tuile.clicked.connect(lambda _=False, n=jeu["nom"]: self.lancer.emit(n))
            grille.addWidget(tuile, i // colonnes, i % colonnes)
        lay.addLayout(grille)
        self.setFixedWidth(largeur)


class CarteLancement(QWidget):
    """Grande bannière quand un jeu se lance."""

    def __init__(self, jeu, largeur=LARGEUR_FIL, parent=None):
        super().__init__(parent)
        self.jeu = jeu
        self.setFixedSize(largeur, round(largeur * 0.3))
        r = self.rect()
        self.fond = image_couverte(jeu["fond"], r.width(), r.height()) if jeu.get("fond") else None
        self.logo = QPixmap(str(jeu["logo"])) if jeu.get("logo") else QPixmap()
        self.icone = QPixmap() if self.fond else pixmap_icone(jeu.get("icone"), 96)
        self.teinte = couleur_moyenne(self.icone)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        if self.fond:
            peindre_image(p, self.fond, r, 12)
        else:
            fond = QLinearGradient(r.topLeft(), r.bottomRight())
            fond.setColorAt(0, self.teinte)
            fond.setColorAt(1, self.teinte.darker(300))
            p.setPen(Qt.NoPen)
            p.setBrush(fond)
            p.drawRoundedRect(r, 12, 12)
            if not self.icone.isNull():
                cote = r.height() * 0.7
                p.drawPixmap(QRectF(r.right() - cote - 18, r.center().y() - cote / 2, cote, cote),
                             self.icone, QRectF(self.icone.rect()))
        ombre = QLinearGradient(r.topLeft(), r.topRight())
        ombre.setColorAt(0, QColor(0, 0, 0, 200))
        ombre.setColorAt(0.65, QColor(0, 0, 0, 0))
        p.setBrush(ombre)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 12, 12)
        p.setPen(QPen(CONTOUR, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

        zone = QRectF(18, 14, r.width() * 0.5, r.height() - 52)
        if not self.logo.isNull():
            taille = self.logo.size().scaled(zone.size().toSize(), Qt.KeepAspectRatio)
            p.drawPixmap(QRectF(zone.left(), zone.center().y() - taille.height() / 2, taille.width(), taille.height()),
                         self.logo, QRectF(self.logo.rect()))
        else:
            p.setPen(TEXTE)
            p.setFont(police(20, gras=True, famille="Segoe UI Variable Display"))
            p.drawText(zone, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.jeu["nom"])
        pastille = QRectF(18, r.height() - 36, 118, 24)
        p.setPen(Qt.NoPen)
        p.setBrush(accent())
        p.drawRoundedRect(pastille, 12, 12)
        p.setPen(QColor(0, 0, 0))
        p.setFont(police_icones(11))
        p.drawText(QRectF(pastille.left() + 9, pastille.top(), 14, pastille.height()), Qt.AlignCenter, ICONES["jouer"])
        p.setFont(police(12, gras=True))
        p.drawText(pastille.adjusted(27, 0, 0, 0), Qt.AlignVCenter, "Lancement…")


# ------------------------------------------------------------------ Rangement et ménage

class Proposition(QWidget):
    """« Je le range ici : PDF › Gmail  [Ranger ici] » au-dessus des fichiers déposés."""
    ranger = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(46, 8, 8, 8)
        lay.setSpacing(8)
        textes = QVBoxLayout()
        textes.setSpacing(0)
        self.chapeau = Etiquette("Je le range ici", 11, TEXTE_3)
        self.lieu = EtiquetteCoupee("", taille=13, gras=True)
        textes.addWidget(self.chapeau)
        textes.addWidget(self.lieu)
        lay.addLayout(textes, 1)
        self.bouton = Bouton("ranger", "Ranger ici", "accent")
        self.bouton.clicked.connect(self.ranger)
        lay.addWidget(self.bouton)

    def montrer(self, lieux):
        """lieux : la destination de chaque fichier (ex. ['PDF › Gmail', 'Images › Discord'])."""
        uniques = list(dict.fromkeys(lieux))
        if len(lieux) == 1:
            self.chapeau.setText("Je le range ici")
            self.bouton.setText("Ranger ici")
        else:
            self.chapeau.setText("Je range chacun à sa place")
            self.bouton.setText("Tout ranger")
        self.lieu.setText(", ".join(uniques[:3]) + (" …" if len(uniques) > 3 else ""))
        self.bouton.updateGeometry()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        a = accent()
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 110), 1))
        p.setBrush(QColor(a.red(), a.green(), a.blue(), 26))
        p.drawRoundedRect(r, 12, 12)
        p.setPen(a)
        p.setFont(police_icones(18))
        p.drawText(QRectF(10, 0, 28, self.height()), Qt.AlignCenter, ICONES["dossier_ouvert"])


class LigneMenage(QAbstractButton):
    """Une catégorie de fichiers à supprimer, qu'on coche ou décoche."""

    def __init__(self, categorie, parent=None):
        super().__init__(parent)
        self.categorie = categorie
        self.setCheckable(True)
        self.setChecked(categorie.coche)
        self.setAttribute(Qt.WA_Hover)
        self.setFixedHeight(54)
        noms = [Path(c).name for c, _ in categorie.fichiers[:3]]
        self.detail = categorie.description if categorie.cle == "temp" else ", ".join(noms) + \
            (f" et {len(categorie.fichiers) - 3} autres" if len(categorie.fichiers) > 3 else "")
        self.setToolTip("\n".join(str(c) for c, _ in categorie.fichiers[:12]))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(CARTE)
            p.drawRoundedRect(r, 10, 10)
        a = accent()
        case = QRectF(10, r.center().y() - 9, 18, 18)
        if not self.isEnabled():            # déjà nettoyé
            p.setPen(SUCCES)
            p.setFont(police_icones(13))
            p.drawText(case, Qt.AlignCenter, ICONES["ok"])
            p.setOpacity(0.45)
        elif self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(a)
            p.drawEllipse(case)
            p.setPen(QColor(0, 0, 0))
            p.setFont(police_icones(10))
            p.drawText(case, Qt.AlignCenter, ICONES["ok"])
        else:
            p.setPen(QPen(TEXTE_3, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(case.adjusted(0.7, 0.7, -0.7, -0.7))
        p.setPen(TEXTE_2)
        p.setFont(police_icones(15))
        p.drawText(QRectF(38, 0, 22, self.height()), Qt.AlignCenter, ICONES.get(self.categorie.icone, ""))
        taille = taille_lisible(self.categorie.total)
        p.setFont(police(13, gras=True))
        largeur_taille = p.fontMetrics().horizontalAdvance(taille) + 12
        p.setPen(TEXTE)
        p.drawText(QRectF(68, 8, r.width() - 68 - largeur_taille, 20), Qt.AlignVCenter, self.categorie.titre)
        p.drawText(QRectF(r.right() - largeur_taille, 0, largeur_taille - 8, self.height()),
                   Qt.AlignVCenter | Qt.AlignRight, taille)
        p.setPen(TEXTE_3)
        p.setFont(police(11))
        detail = p.fontMetrics().elidedText(self.detail, Qt.ElideRight, int(r.width() - 68 - largeur_taille))
        p.drawText(QRectF(68, 28, r.width() - 68 - largeur_taille, 18), Qt.AlignVCenter, detail)


class CarteMenage(QWidget):
    """« Faire de la place » : état du disque, ce qui peut partir, et les boutons pour le faire."""
    nettoyer = Signal(list)
    vider = Signal()

    def __init__(self, analyse, largeur=LARGEUR_FIL, parent=None):
        super().__init__(parent)
        self.setFixedWidth(largeur)
        self.disque = analyse["disque"]
        self.taille_corbeille = analyse["corbeille"][0]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(4)
        lay.addSpacing(52)            # l'en-tête et la barre du disque sont dessinés dans paintEvent
        self.lignes = []
        for c in analyse["categories"]:
            ligne = LigneMenage(c)
            ligne.toggled.connect(self._maj)
            self.lignes.append(ligne)
            lay.addWidget(ligne)
        if not self.lignes:
            lay.addWidget(Etiquette("Rien à nettoyer, ton disque est déjà propre.", 12, TEXTE_2))
        lay.addSpacing(6)
        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        self.bouton = Bouton("balai", "", "accent")
        self.bouton.clicked.connect(self._nettoyer)
        self.bouton_corbeille = Bouton("supprimer", "", "puce", info="Supprime pour de bon ce qui est dans la corbeille")
        self.bouton_corbeille.clicked.connect(self._vider)
        boutons.addWidget(self.bouton)
        boutons.addWidget(self.bouton_corbeille)
        boutons.addStretch(1)
        lay.addLayout(boutons)
        self.note = Etiquette("Tes fichiers partent à la corbeille (récupérables). La place est vraiment "
                              "libérée quand tu vides la corbeille.", 11, TEXTE_3)
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self._maj()

    def _choisies(self):
        return [l.categorie for l in self.lignes if l.isChecked() and l.isEnabled()]

    def _maj(self):
        total = sum(c.total for c in self._choisies())
        self.bouton.setText(f"Libérer {taille_lisible(total)}" if total else "Rien de coché")
        self.bouton.setEnabled(total > 0)
        self.bouton_corbeille.setText(f"Vider la corbeille · {taille_lisible(self.taille_corbeille)}")
        self.bouton_corbeille.setVisible(self.taille_corbeille > 0)
        for b in (self.bouton, self.bouton_corbeille):
            b.updateGeometry()
            b.update()

    def _nettoyer(self):
        choisies = self._choisies()
        if choisies:
            self.bouton.setEnabled(False)
            self.bouton.setText("Je nettoie…")
            self.nettoyer.emit(choisies)

    def _vider(self):
        if not self.bouton_corbeille.danger:          # deux clics : c'est définitif
            self.bouton_corbeille.danger = True
            self.bouton_corbeille.setText("Sûr ? C'est définitif")
            self.bouton_corbeille.updateGeometry()
            return
        self.bouton_corbeille.danger = False
        self.bouton_corbeille.setEnabled(False)
        self.vider.emit()

    def termine(self, liberes, disque, corbeille, message):
        """Après le ménage : on grise ce qui est parti et on met le disque à jour."""
        for l in self.lignes:
            if l.isChecked():
                l.setEnabled(False)
                l.setChecked(False)
        self.disque = disque
        self.taille_corbeille = corbeille
        self.bouton_corbeille.setEnabled(True)
        self.note.setText(message)
        self._maj()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(CONTOUR, 1))
        p.setBrush(CARTE)
        p.drawRoundedRect(r, 14, 14)
        total, utilise, libre = self.disque
        a = accent()
        p.setPen(a)
        p.setFont(police_icones(16))
        p.drawText(QRectF(16, 12, 22, 22), Qt.AlignCenter, ICONES["disque"])
        p.setPen(TEXTE)
        p.setFont(police(14, gras=True))
        p.drawText(QRectF(44, 12, 200, 22), Qt.AlignVCenter, "Faire de la place")
        p.setPen(TEXTE_2)
        p.setFont(police(12))
        p.drawText(QRectF(r.width() - 260, 12, 244, 22), Qt.AlignVCenter | Qt.AlignRight,
                   f"{taille_lisible(libre)} libres sur {taille_lisible(total)}")
        barre = QRectF(16, 42, r.width() - 32, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(barre, 4, 4)
        part = utilise / total if total else 0
        rempli = QRectF(barre.left(), barre.top(), max(8, barre.width() * part), barre.height())
        couleur = ROUGE if part > 0.92 else (QColor("#FCB040") if part > 0.8 else a)
        p.setBrush(couleur)
        p.drawRoundedRect(rempli, 4, 4)


# ------------------------------------------------------------------ Le fil

class Fil(QScrollArea):
    """Le fil de la conversation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 2px 0; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,55); border-radius: 3px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: rgba(255,255,255,110); }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: none; }
        """)
        contenu = QWidget()
        contenu.setAutoFillBackground(False)
        self.pile = QVBoxLayout(contenu)
        self.pile.setContentsMargins(0, 4, 8, 6)
        self.pile.setSpacing(10)
        self.pile.addStretch(1)
        self.setWidget(contenu)
        self.derniere_puce = None
        self._viser = None
        self.verticalScrollBar().rangeChanged.connect(self._defiler)

    def _defiler(self, _, fin):
        """Descend en bas du fil, sauf pour une grande carte : on montre son début."""
        if self._viser is not None:
            haut = self._viser.mapTo(self.widget(), QPointF(0, 0)).y() - 8
            self.verticalScrollBar().setValue(min(fin, max(0, round(haut))))
        else:
            self.verticalScrollBar().setValue(fin)

    def vide(self):
        return self.pile.count() <= 1

    def _ajouter(self, widget, a_droite=False, espace_avant=0):
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, espace_avant, 0, 0)
        if a_droite:
            ligne.addStretch(1)
        ligne.addWidget(widget)
        if not a_droite:
            ligne.addStretch(1)
        self.pile.insertLayout(self.pile.count() - 1, ligne)
        return widget

    def moi(self, texte, piece=""):
        self.derniere_puce = None
        self._viser = None
        self._ajouter(Bulle(texte, piece), a_droite=True, espace_avant=0 if self.vide() else 6)

    def ia(self, texte):
        self._ajouter(TexteRiche(texte))

    def action(self, texte, sur_clic=None):
        self.derniere_puce = self._ajouter(PuceAction(texte, sur_clic))
        return self.derniere_puce

    def erreur(self, texte):
        self._ajouter(ligne_icone(ICONES["erreur"], texte, ERREUR, largeur=LARGEUR_FIL - 30))

    def carte(self, w):
        self._viser = w if w.sizeHint().height() > 300 else None
        return self._ajouter(w)

    def effacer(self):
        self.derniere_puce = None
        while self.pile.count() > 1:
            element = self.pile.takeAt(0)
            if element.layout():
                while element.layout().count():
                    w = element.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
                element.layout().deleteLater()
