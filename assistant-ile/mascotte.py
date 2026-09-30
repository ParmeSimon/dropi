"""Plop, la mascotte : une petite goutte d'eau blanche et violette qui vit dans la bulle.

Rendu « 3D » en temps réel : un corps éclairé (dégradés, reflets, lumière de contour)
et un visage projeté sur une sphère, qui tourne la tête vers ta souris.
Ses expressions changent selon ce que tu fais (voir EXPRESSIONS et Ile._humeur()).
"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QRadialGradient, QLinearGradient,
                           QPen, QImage, QPolygonF)
from PySide6.QtWidgets import QWidget

from goutte import Ressort, borne

BLANC = QColor(255, 255, 255)
LAVANDE = QColor("#F1ECFF")
MAUVE = QColor("#C9B8FB")
VIOLET = QColor("#9373F2")
VIOLET_FONCE = QColor("#6B4BD6")
ENCRE = QColor("#221938")
JOUE = QColor("#FF8FC4")
BOUCHE = QColor("#3E1C43")
LANGUE = QColor("#FF7FA8")

# ouvert : yeux ouverts | taille : taille des yeux | joie : yeux en ^^ | triste : paupières tombantes
# sourire : -1 (moue) à 1 | bouche : ouverture | largeur : largeur de bouche | joues : rougeur
# incl : penche la tête | haut : regarde vers le haut (négatif = vers le bas)
EXPRESSIONS = {
    "repos":     dict(ouvert=1, taille=1.0, joie=0, triste=0, sourire=.55, bouche=0, largeur=1.0, joues=.45, incl=0, haut=0),
    "content":   dict(ouvert=1, taille=1.0, joie=1, triste=0, sourire=1.0, bouche=.35, largeur=1.05, joues=.95, incl=0, haut=.05),
    "reflechit": dict(ouvert=.8, taille=.95, joie=0, triste=0, sourire=.1, bouche=0, largeur=.7, joues=.35, incl=.14, haut=.38),
    "ecoute":    dict(ouvert=1, taille=1.15, joie=0, triste=0, sourire=.3, bouche=.28, largeur=.6, joues=.5, incl=-.12, haut=.05),
    "erreur":    dict(ouvert=.9, taille=.95, joie=0, triste=1, sourire=-.75, bouche=0, largeur=.8, joues=.2, incl=0, haut=-.05),
    "faim":      dict(ouvert=1, taille=1.28, joie=0, triste=0, sourire=.5, bouche=1.0, largeur=1.15, joues=1, incl=0, haut=0),
    "miam":      dict(ouvert=1, taille=1.0, joie=.85, triste=0, sourire=.8, bouche=.3, largeur=1.1, joues=1, incl=0, haut=0),
    "curieux":   dict(ouvert=1, taille=1.12, joie=0, triste=0, sourire=.35, bouche=.12, largeur=.75, joues=.55, incl=.2, haut=0),
    "surpris":   dict(ouvert=1, taille=1.3, joie=0, triste=0, sourire=0, bouche=.7, largeur=.55, joues=.3, incl=0, haut=0),
    "dort":      dict(ouvert=0, taille=1.0, joie=0, triste=0, sourire=.3, bouche=0, largeur=.8, joues=.55, incl=.1, haut=-.12),
    "tape":      dict(ouvert=.95, taille=1.0, joie=0, triste=0, sourire=.45, bouche=0, largeur=.9, joues=.5, incl=0, haut=-.42),
    "logo":      dict(ouvert=1, taille=1.08, joie=0, triste=0, sourire=.95, bouche=.32, largeur=1.05, joues=.85, incl=0, haut=.02),
}

SOMMEIL = 150        # secondes sans bouger la souris avant qu'elle s'endorme


class Mascotte:
    def __init__(self):
        self.t = 0.0
        self.base = "repos"
        self._passagere, self._fin_passagere = None, 0.0
        self.p = dict(EXPRESSIONS["repos"])
        self.lacet = Ressort(0, 8, .8)       # tête : gauche / droite
        self.tangage = Ressort(0, 8, .8)     # tête : haut / bas
        self.saut = Ressort(0, 15, .3)       # petits bonds
        self.pointe = Ressort(0, 10, .2)     # la pointe de la goutte qui balance
        self.tremble = 0.0
        self.ecrase = 0.0                    # écrasement imposé par la bulle (effet goutte)
        self.vent = 0.0                      # vitesse horizontale de la bulle quand on la tire
        self._clin, self._prochain_clin = 0.0, 2.5
        self._souris, self._souris_t = None, time.monotonic()
        self.dodo = False

    # ---------------------------------------------------------------- réactions
    def humeur(self):
        if self._passagere and self.t < self._fin_passagere:
            return self._passagere
        return "dort" if self.dodo and self.base == "repos" else self.base

    def reagir(self, humeur, duree=1.0):
        self._passagere, self._fin_passagere = humeur, self.t + duree
        if humeur in ("content", "miam", "surpris"):
            self.sauter(0.7 if humeur != "content" else 1.0)
        if humeur == "erreur":
            self.tremble = 1.0

    def sauter(self, force=1.0):
        self.saut.vitesse -= 4.8 * force

    def hocher(self):
        self.tangage.vitesse -= 2.2

    def reveiller(self):
        self._souris_t = time.monotonic()
        if self.dodo:
            self.dodo = False
            self.reagir("surpris", 0.6)

    # ---------------------------------------------------------------- animation
    def maj(self, dt, ancre, curseur):
        """ancre : centre de la mascotte à l'écran ; curseur : position de la souris (écran)."""
        self.t += dt
        maintenant = time.monotonic()
        if self._souris is None or (curseur - self._souris).manhattanLength() > 2:
            self._souris = QPointF(curseur)
            self.reveiller()
        elif maintenant - self._souris_t > SOMMEIL:
            self.dodo = True
        immobile = maintenant - self._souris_t

        humeur = self.humeur()
        cible = EXPRESSIONS.get(humeur, EXPRESSIONS["repos"])
        k = 1 - math.exp(-dt * 11)
        for cle, v in cible.items():
            self.p[cle] += (v - self.p[cle]) * k
        if humeur == "miam":
            self.p["bouche"] = 0.12 + 0.4 * (0.5 + 0.5 * math.sin(self.t * 15))

        # où regarder
        if humeur == "reflechit":
            lacet, tangage = 0.4 * math.sin(self.t * 0.9), 0.0
        elif humeur in ("tape", "dort"):
            lacet, tangage = 0.0, 0.0
        elif immobile > 5 and humeur == "repos":
            lacet = 0.45 * math.sin(self.t * 0.37) * math.sin(self.t * 0.13 + 1)
            tangage = 0.12 * math.sin(self.t * 0.51)
        else:
            d = curseur - ancre
            lacet = borne(d.x() / 260, -1, 1) * 0.62
            tangage = borne(-d.y() / 260, -1, 1) * 0.45
        self.lacet.cible, self.tangage.cible = lacet, tangage + self.p["haut"]
        self.lacet.pas(dt)
        self.tangage.pas(dt)
        self.saut.pas(dt)
        self.pointe.cible = 0.1 * math.sin(self.t * 1.6) - self.lacet.valeur * 0.35 - borne(self.vent / 1500, -0.6, 0.6)
        self.pointe.pas(dt)
        self.tremble = max(0.0, self.tremble - dt * 1.6)

        # clignements
        self._prochain_clin -= dt
        if self._prochain_clin <= 0 and self.p["joie"] < 0.3 and humeur != "dort":
            self._clin = 0.15
            self._prochain_clin = random.uniform(2.2, 5.5) if random.random() > 0.15 else 0.25
        self._clin = max(0.0, self._clin - dt)

    def agite(self):
        """Vrai si quelque chose bouge vite (pour décider de la fréquence d'animation)."""
        return (not self.saut.calme(0.01) or not self.lacet.calme(0.004) or self.tremble > 0
                or self._clin > 0 or self.humeur() in ("miam", "reflechit", "faim", "surpris", "ecoute"))

    # ---------------------------------------------------------------- dessin
    def _forme(self, R):
        """La goutte : bas rond, pointe en haut qui se balance."""
        s = self.pointe.valeur * R
        c = QPainterPath(QPointF(s, -1.58 * R))
        c.cubicTo(QPointF(s * 0.6 + 0.3 * R, -1.2 * R), QPointF(R, -0.62 * R), QPointF(R, 0))
        c.arcTo(QRectF(-R, -R, 2 * R, 2 * R), 0, -180)
        c.cubicTo(QPointF(-R, -0.62 * R), QPointF(s * 0.6 - 0.3 * R, -1.2 * R), QPointF(s, -1.58 * R))
        c.closeSubpath()
        return c

    def dessiner(self, p, centre, R, halo=True):
        P = self.p
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        dodo = self.humeur() == "dort"
        periode = 5.0 if dodo else 3.2
        souffle = math.sin(self.t * 2 * math.pi / periode) * (0.04 if dodo else 0.025)
        vitesse_saut = borne(-self.saut.vitesse * 0.035, -0.12, 0.18)
        sy = 1 + souffle + vitesse_saut - self.ecrase
        sx = 1 - souffle * 0.6 - vitesse_saut * 0.5 + self.ecrase * 0.6
        secousse = self.tremble * R * 0.12 * math.sin(self.t * 42)

        p.translate(centre.x() + secousse, centre.y() + 0.28 * R)
        if halo:
            h = QRadialGradient(QPointF(0, -0.2 * R), 1.9 * R)
            h.setColorAt(0, QColor(VIOLET.red(), VIOLET.green(), VIOLET.blue(), 85))
            h.setColorAt(1, QColor(VIOLET.red(), VIOLET.green(), VIOLET.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(h)
            p.drawEllipse(QPointF(0, -0.2 * R), 1.9 * R, 1.9 * R)

        p.translate(0, self.saut.valeur * R)
        p.rotate(math.degrees(P["incl"] + self.lacet.valeur * 0.12))
        p.translate(0, R)
        p.scale(sx, sy)
        p.translate(0, -R)
        corps = self._forme(R)

        # corps : lumière venant d'en haut à gauche
        g = QRadialGradient(QPointF(-0.3 * R, -0.45 * R), 1.6 * R, QPointF(-0.4 * R, -0.55 * R))
        g.setColorAt(0.0, BLANC)
        g.setColorAt(0.38, LAVANDE)
        g.setColorAt(0.78, MAUVE)
        g.setColorAt(1.0, VIOLET)
        p.fillPath(corps, g)
        # lumière de rebond violette en bas à droite (effet translucide)
        rebond = QRadialGradient(QPointF(0.62 * R, 0.72 * R), 0.95 * R)
        rebond.setColorAt(0, QColor(236, 222, 255, 150))
        rebond.setColorAt(1, QColor(236, 222, 255, 0))
        p.fillPath(corps, rebond)
        # contour sombre très doux (occlusion) pour détacher la goutte du fond
        contour = QRadialGradient(QPointF(0, -0.1 * R), 1.35 * R)
        contour.setColorAt(0.72, QColor(VIOLET_FONCE.red(), VIOLET_FONCE.green(), VIOLET_FONCE.blue(), 0))
        contour.setColorAt(1.0, QColor(VIOLET_FONCE.red(), VIOLET_FONCE.green(), VIOLET_FONCE.blue(), 120))
        p.fillPath(corps, contour)

        self._visage(p, R)

        # reflets : grosse tache douce + trait sur la pointe
        p.setPen(Qt.NoPen)
        p.save()
        p.translate(-0.45 * R, -0.5 * R)
        p.rotate(-38)
        reflet = QRadialGradient(QPointF(0, 0), 0.3 * R)
        reflet.setColorAt(0, QColor(255, 255, 255, 235))
        reflet.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(reflet)
        p.drawEllipse(QPointF(0, 0), 0.3 * R, 0.17 * R)
        p.restore()
        trait = QPainterPath(QPointF(-0.5 * R, -0.78 * R))
        trait.quadTo(QPointF(-0.36 * R + self.pointe.valeur * R * 0.3, -1.12 * R),
                     QPointF(-0.1 * R + self.pointe.valeur * R * 0.6, -1.3 * R))
        stylo = QPen(QColor(255, 255, 255, 170), max(0.8, 0.075 * R))
        stylo.setCapStyle(Qt.RoundCap)
        p.strokePath(trait, stylo)
        p.restore()

    # ---------------------------------------------------------------- visage projeté sur la sphère
    def _projeter(self, p, R, lon, lat):
        """Place le pinceau sur la sphère (tête tournée) ; renvoie False si le point est caché."""
        lacet, tangage = self.lacet.valeur, self.tangage.valeur
        x, y, z = math.cos(lat) * math.sin(lon), math.sin(lat), math.cos(lat) * math.cos(lon)
        y, z = y * math.cos(tangage) + z * math.sin(tangage), -y * math.sin(tangage) + z * math.cos(tangage)
        x, z = x * math.cos(lacet) + z * math.sin(lacet), -x * math.sin(lacet) + z * math.cos(lacet)
        if z < 0.12:
            return False
        angle = math.degrees(math.atan2(-y, x))
        p.translate(R * x, -R * y)
        p.rotate(angle)
        p.scale(z, 1)          # raccourci : un motif sur le bord d'une sphère s'aplatit
        p.rotate(-angle)
        return True

    def _visage(self, p, R):
        P = self.p
        for cote in (-1, 1):
            p.save()
            if self._projeter(p, R, cote * 0.62, -0.13) and P["joues"] > 0.02:
                g = QRadialGradient(QPointF(0, 0), 0.2 * R)
                g.setColorAt(0, QColor(JOUE.red(), JOUE.green(), JOUE.blue(), round(150 * P["joues"])))
                g.setColorAt(1, QColor(JOUE.red(), JOUE.green(), JOUE.blue(), 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(0, 0), 0.2 * R, 0.12 * R)
            p.restore()
        for cote in (-1, 1):
            p.save()
            if self._projeter(p, R, cote * 0.38, 0.13):
                self._oeil(p, R, cote)
            p.restore()
        p.save()
        if self._projeter(p, R, 0, -0.27):
            self._bouche(p, R)
        p.restore()

    def _oeil(self, p, R, cote):
        P = self.p
        clin = 1 - math.sin(math.pi * (1 - self._clin / 0.15)) if self._clin > 0 else 1
        w = 0.21 * R * P["taille"]
        h = 0.3 * R * P["taille"]
        hh = h * P["ouvert"] * clin * (1 - P["joie"])
        p.setPen(Qt.NoPen)
        if hh > 0.07 * R:
            oeil = QPainterPath()
            oeil.addEllipse(QPointF(0, 0), w / 2, hh / 2)
            if P["triste"] > 0.02:
                def paupiere(x):
                    return -hh / 2 + P["triste"] * hh * (0.3 + 0.32 * cote * x / w)
                masque = QPainterPath()
                masque.addPolygon(QPolygonF([QPointF(-w, paupiere(-w)), QPointF(w, paupiere(w)),
                                             QPointF(w, h), QPointF(-w, h)]))
                oeil = oeil.intersected(masque)
            p.setBrush(ENCRE)
            p.drawPath(oeil)
            if hh > 0.12 * R:
                p.setBrush(QColor(255, 255, 255, 240))
                p.drawEllipse(QPointF(-0.04 * R, -hh * 0.22), 0.07 * R * P["taille"], 0.07 * R * P["taille"])
                p.setBrush(QColor(255, 255, 255, 170))
                p.drawEllipse(QPointF(0.04 * R, hh * 0.2), 0.028 * R * P["taille"], 0.028 * R * P["taille"])
        elif P["joie"] < 0.5:
            ferme = QPainterPath(QPointF(-w * 0.5, 0))
            ferme.quadTo(QPointF(0, 0.09 * R), QPointF(w * 0.5, 0))
            stylo = QPen(ENCRE, max(0.9, 0.05 * R))
            stylo.setCapStyle(Qt.RoundCap)
            p.strokePath(ferme, stylo)
        if P["joie"] > 0.02:
            arc = QPainterPath(QPointF(-w * 0.55, 0.035 * R))
            arc.quadTo(QPointF(0, -0.2 * R), QPointF(w * 0.55, 0.035 * R))
            couleur = QColor(ENCRE)
            couleur.setAlphaF(borne(P["joie"] * 1.4 - 0.2, 0, 1))
            stylo = QPen(couleur, max(0.9, 0.062 * R))
            stylo.setCapStyle(Qt.RoundCap)
            p.strokePath(arc, stylo)

    def _bouche(self, p, R):
        P = self.p
        mw = 0.3 * R * P["largeur"]
        s, o = P["sourire"], P["bouche"]
        if o < 0.08:
            c = QPainterPath(QPointF(-mw / 2, 0))
            c.quadTo(QPointF(0, s * mw * 0.55), QPointF(mw / 2, 0))
            stylo = QPen(ENCRE, max(0.9, 0.055 * R))
            stylo.setCapStyle(Qt.RoundCap)
            p.strokePath(c, stylo)
            return
        profondeur = mw * (0.16 + o * 0.7)
        c = QPainterPath(QPointF(-mw / 2, 0))
        c.cubicTo(QPointF(-mw * 0.2, s * mw * 0.18), QPointF(mw * 0.2, s * mw * 0.18), QPointF(mw / 2, 0))
        c.cubicTo(QPointF(mw * 0.5, profondeur * 1.25), QPointF(-mw * 0.5, profondeur * 1.25), QPointF(-mw / 2, 0))
        c.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(BOUCHE)
        p.drawPath(c)
        if o > 0.2:
            langue = QPainterPath()
            langue.addEllipse(QPointF(0, profondeur * 0.95), mw * 0.3, profondeur * 0.42)
            p.setBrush(LANGUE)
            p.drawPath(langue.intersected(c))


class VueMascotte(QWidget):
    """La mascotte dans un en-tête (elle partage son état avec celle de la bulle)."""

    def __init__(self, mascotte, rayon=11, halo=False, parent=None):
        super().__init__(parent)
        self.mascotte = mascotte
        self.rayon = rayon
        self.halo = halo
        marge = 4.2 if halo else 2.9      # le halo déborde : on prévoit la place pour ne pas le couper
        self.setFixedSize(round(rayon * marge), round(rayon * max(marge, 3.2)))

    def centre_global(self):
        return self.mapToGlobal(QPointF(self.width() / 2, self.height() / 2))

    def paintEvent(self, _):
        p = QPainter(self)
        self.mascotte.dessiner(p, QPointF(self.width() / 2, self.height() / 2), self.rayon, self.halo)


def image_logo(taille):
    """Plop en image, pour le logo et les icônes."""
    m = Mascotte()
    m.p = dict(EXPRESSIONS["logo"])
    m.pointe.valeur = 0.06
    image = QImage(taille, taille, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    m.dessiner(p, QPointF(taille / 2, taille / 2 - taille * 0.02), taille / 2.8, halo=False)
    p.end()
    return image
