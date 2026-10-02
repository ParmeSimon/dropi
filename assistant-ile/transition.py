"""L'animation entre la goutte et le tableau de bord.

Ouverture : la goutte file au milieu de l'écran, Plop saute, retombe, et le liquide s'étale : une tache ronde aux bords
qui ondulent gagne tout l'écran en révélant le tableau de bord, avec quelques gouttelettes projetées. Plop va se poser
dans la pastille « Réduire », en haut au milieu. Fermeture : le même film à l'envers, le liquide se rétracte en goutte.

C'est une fenêtre transparente posée par-dessus tout pendant une seconde, qui ne prend ni les clics ni le clavier.
Ce qu'on voit dans la tache est une photo du tableau de bord prise juste avant : la vraie fenêtre n'apparaît qu'à la fin.
"""
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QLinearGradient
from PySide6.QtWidgets import QWidget

import composants as ui
from tableau import Tableau

RAYON = 23.0                    # la goutte au repos
R_PLOP = 13.5
# durées en millisecondes
VOL, SAUT, ETALER, FONDU = 300, 340, 620, 150
POINTS = 96                     # finesse du contour de la tache
GOUTTELETTES = [(0.35, 1.00, 9), (1.25, 0.86, 6), (2.05, 1.08, 8), (2.95, 0.92, 5), (3.85, 1.04, 7), (4.75, 0.88, 6), (5.65, 0.97, 8)]


def _doux(t):
    """Départ et arrivée en douceur."""
    return t * t * (3 - 2 * t)


def _sortie(t):
    return 1 - (1 - t) ** 3


def _melange(a, b, t):
    return a + (b - a) * t


def tache(centre, rayon, u, temps):
    """Le contour du liquide : un cercle dont le bord ondule (de moins en moins à mesure qu'il s'étale)."""
    amplitude = min(0.16, 46.0 / max(rayon, 1.0)) * (1 - 0.75 * u)
    chemin = QPainterPath()
    for i in range(POINTS + 1):
        angle = 2 * math.pi * i / POINTS
        onde = (0.50 * math.sin(3 * angle + 5.0 * temps) + 0.32 * math.sin(5 * angle - 3.4 * temps + 1.3)
                + 0.18 * math.sin(8 * angle + 2.2 * temps + 0.6))
        r = rayon * (1 + amplitude * onde)
        point = QPointF(centre.x() + r * math.cos(angle), centre.y() + r * math.sin(angle))
        if i == 0:
            chemin.moveTo(point)
        else:
            chemin.lineTo(point)
    chemin.closeSubpath()
    return chemin


class Transition(QWidget):
    def __init__(self, mascotte):
        super().__init__(None)
        self.mascotte = mascotte
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._t = 0.0                           # 0 = goutte à sa place, 1 = tableau de bord affiché
        self._goutte = self._plop = QPointF()
        self._image = None                      # la photo du tableau de bord (ou None : on dessine juste son fond)
        self._r_plop = R_PLOP                   # la taille de Plop à l'arrivée (il est plus grand dans le tableau de bord)
        self._au_plein = self._a_la_fin = None
        self._plein_fait = False
        self._ouvre = True
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=VOL + SAUT + ETALER + FONDU)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._avancer)
        self._anim.finished.connect(self._fini)

    def en_cours(self):
        return self._anim.state() == QVariantAnimation.Running

    def jouer(self, zone, goutte, plop, ouvrir, au_plein, a_la_fin, image=None, rayon_plop=R_PLOP):
        """zone : le rectangle de l'écran ; goutte : le centre de la goutte ; plop : là où Plop se pose dans le tableau
        de bord (coordonnées de l'écran) ; image : la photo du tableau de bord. au_plein() est appelé quand le liquide
        couvre tout l'écran (c'est le moment d'afficher ou de cacher la vraie fenêtre, on ne voit rien) ; a_la_fin()
        quand tout est terminé."""
        self._anim.stop()
        self.setGeometry(zone)
        self._goutte = QPointF(goutte) - QPointF(zone.topLeft())
        self._plop = QPointF(plop) - QPointF(zone.topLeft())
        self._image = image
        self._r_plop = rayon_plop
        self._ouvre, self._au_plein, self._a_la_fin, self._plein_fait = ouvrir, au_plein, a_la_fin, False
        self._t = 0.0 if ouvrir else 1.0
        self._anim.setDirection(QVariantAnimation.Forward if ouvrir else QVariantAnimation.Backward)
        self.show()
        self.raise_()
        self._anim.start()

    def _avancer(self, valeur):
        self._t = float(valeur)
        total = VOL + SAUT + ETALER + FONDU
        seuil = (VOL + SAUT + ETALER) / total
        # à l'ouverture, l'écran est couvert quand on arrive au fondu ; à la fermeture, dès que le fondu est passé
        if not self._plein_fait and ((self._ouvre and self._t >= seuil) or (not self._ouvre and self._t <= seuil)):
            self._plein_fait = True
            if self._au_plein:
                self._au_plein()
        self.update()

    def _fini(self):
        self.hide()
        self._image = None
        if not self._plein_fait and self._au_plein:
            self._au_plein()
        if self._a_la_fin:
            self._a_la_fin()

    # ------------------------------------------------------------ dessin
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        total = VOL + SAUT + ETALER + FONDU
        ms = self._t * total
        plein = QRectF(self.rect())
        centre = plein.center()
        if ms <= VOL:                                           # la goutte vole vers le milieu
            u = _doux(ms / VOL)
            c = QPointF(_melange(self._goutte.x(), centre.x(), u), _melange(self._goutte.y(), centre.y(), u))
            self._goutte_ronde(p, c, RAYON + 5 * u)
        elif ms <= VOL + SAUT:                                  # Plop saute, puis s'écrase un peu en retombant
            u = (ms - VOL) / SAUT
            hauteur = math.sin(math.pi * min(1.0, u / 0.82)) * 52 if u < 0.82 else 0.0
            if u < 0.82:
                etire = 1 + 0.12 * math.sin(2 * math.pi * u / 0.82)
            else:                                               # l'impact : la goutte s'aplatit
                etire = 1 - 0.30 * math.sin(math.pi * (u - 0.82) / 0.36)
            self._goutte_ronde(p, QPointF(centre.x(), centre.y() - hauteur), RAYON + 5, etire)
        elif ms <= VOL + SAUT + ETALER:                         # le liquide s'étale
            lineaire = (ms - VOL - SAUT) / ETALER
            u = _sortie(lineaire)
            r_max = math.hypot(plein.width(), plein.height()) / 2 * 1.12
            rayon = _melange(RAYON + 5, r_max, u)
            contour = tache(centre, rayon, u, lineaire)
            self._interieur(p, contour, plein, 1.0)
            # le bord du liquide : un liseré clair, et une lueur de la couleur d'accent juste devant
            a = ui.accent()
            force = 1 - lineaire
            p.strokePath(contour, QPen(QColor(a.red(), a.green(), a.blue(), round(120 * force)), 7))
            p.strokePath(contour, QPen(QColor(255, 255, 255, round(110 * force + 30)), 1.4))
            self._gouttelettes(p, centre, rayon, lineaire)
            # Plop rejoint sa pastille, puis s'efface (il est déjà sur la photo du tableau de bord)
            c = QPointF(_melange(centre.x(), self._plop.x(), u), _melange(centre.y(), self._plop.y(), u))
            p.setOpacity(max(0.0, min(1.0, (0.86 - lineaire) / 0.22)))
            self.mascotte.dessiner(p, c, _melange(R_PLOP, self._r_plop, u), False)
            p.setOpacity(1.0)
        else:                                                   # la vraie fenêtre est là : la photo s'efface
            u = (ms - VOL - SAUT - ETALER) / FONDU
            chemin = QPainterPath()
            chemin.addRect(plein)
            self._interieur(p, chemin, plein, 1 - u)

    def _interieur(self, p, contour, plein, opacite):
        """Ce qu'on voit dans le liquide : le tableau de bord (sa photo), ou à défaut son fond."""
        p.save()
        p.setOpacity(opacite)
        p.setClipPath(contour)
        if self._image is not None and not self._image.isNull():
            p.drawPixmap(plein, self._image, QRectF(self._image.rect()))
        else:
            Tableau.peindre_fond(p, plein)
        p.restore()

    @staticmethod
    def _gouttelettes(p, centre, rayon, u):
        """Quelques gouttes projetées devant le liquide, qui retombent dedans."""
        if u > 0.62:
            return
        vie = u / 0.62
        for angle, portee, taille in GOUTTELETTES:
            distance = rayon * (1.0 + 0.34 * portee * math.sin(math.pi * vie))
            r = taille * (1 - vie) ** 0.8
            if r < 0.6:
                continue
            c = QPointF(centre.x() + distance * math.cos(angle), centre.y() + distance * math.sin(angle))
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(ui.remplissage_ile(rect))
            p.drawEllipse(rect)

    def _goutte_ronde(self, p, centre, rayon, etire=1.0):
        rect = QRectF(centre.x() - rayon / etire, centre.y() - rayon * etire, 2 * rayon / etire, 2 * rayon * etire)
        chemin = QPainterPath()
        chemin.addEllipse(rect)
        ui.dessiner_ombre(p, chemin)
        p.fillPath(chemin, ui.remplissage_ile(rect))
        reflet = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        reflet.setColorAt(0, QColor(255, 255, 255, 44))
        reflet.setColorAt(1, QColor(255, 255, 255, 12))
        p.strokePath(chemin, QPen(reflet, 1))
        self.mascotte.dessiner(p, centre, R_PLOP, False)
