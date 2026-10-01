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
    "ecoute":    dict(ouvert=1, taille=1.15, joie=0, triste=0, sourire=.3, bouche=.28, largeur=.6, joues=.5, incl=-.12, haut=.05),
    "erreur":    dict(ouvert=.9, taille=.95, joie=0, triste=1, sourire=-.75, bouche=0, largeur=.8, joues=.2, incl=0, haut=-.05),
    "faim":      dict(ouvert=1, taille=1.28, joie=0, triste=0, sourire=.5, bouche=1.0, largeur=1.15, joues=1, incl=0, haut=0),
    "miam":      dict(ouvert=1, taille=1.0, joie=.85, triste=0, sourire=.8, bouche=.3, largeur=1.1, joues=1, incl=0, haut=0),
    "curieux":   dict(ouvert=1, taille=1.12, joie=0, triste=0, sourire=.35, bouche=.12, largeur=.75, joues=.55, incl=.2, haut=0),
    "surpris":   dict(ouvert=1, taille=1.3, joie=0, triste=0, sourire=0, bouche=.7, largeur=.55, joues=.3, incl=0, haut=0),
    "dort":      dict(ouvert=0, taille=1.0, joie=0, triste=0, sourire=.3, bouche=0, largeur=.8, joues=.55, incl=.1, haut=-.12),
    "tape":      dict(ouvert=.95, taille=1.0, joie=0, triste=0, sourire=.45, bouche=0, largeur=.9, joues=.5, incl=0, haut=-.42),
    "logo":      dict(ouvert=1, taille=1.08, joie=0, triste=0, sourire=.95, bouche=.32, largeur=1.05, joues=.85, incl=0, haut=.02),
    # il se creuse les méninges : un sourcil froncé, l'autre levé, un œil plissé, le regard en l'air
    "reflechit": dict(ouvert=.85, taille=.95, joie=0, triste=0, sourire=-.1, bouche=0, largeur=.6, joues=.3, incl=.1, haut=.4,
                      sourcil=.7, asym=1),
    # il a trouvé : grands yeux, sourcils levés, bouche ouverte (l'ampoule s'allume au-dessus)
    "eureka":    dict(ouvert=1, taille=1.28, joie=0, triste=0, sourire=1.0, bouche=.6, largeur=.95, joues=.9, incl=0, haut=.3,
                      sourcil=-.9),
    # il s'est cogné : yeux en > <
    "aie":       dict(ouvert=1, taille=1.0, joie=0, triste=0, sourire=-.6, bouche=0, largeur=.8, joues=.25, incl=0, haut=0,
                      croix=1),
    # secoué : yeux en spirale, des étoiles lui tournent autour
    "etourdi":   dict(ouvert=1, taille=1.1, joie=0, triste=0, sourire=-.1, bouche=.3, largeur=.5, joues=.3, incl=0, haut=0,
                      spirale=1),
    # chatouillé
    "rire":      dict(ouvert=1, taille=1.0, joie=1, triste=0, sourire=1.0, bouche=.8, largeur=1.15, joues=1, incl=0, haut=.1),
    "baille":    dict(ouvert=0, taille=1.0, joie=0, triste=0, sourire=0, bouche=1.0, largeur=.7, joues=.4, incl=.06, haut=.2),
    "clin":      dict(ouvert=1, taille=1.0, joie=0, triste=0, sourire=.9, bouche=0, largeur=1.0, joues=.7, incl=-.1, haut=0,
                      clin=1),
    "alerte":    dict(ouvert=1, taille=1.3, joie=0, triste=0, sourire=.2, bouche=.45, largeur=.6, joues=.5, incl=0, haut=.1,
                      sourcil=-.8),
}
# sourcil : froncé (1) ou levé (-1) | asym : un sourcil levé, un œil plissé | croix : yeux en > <
# spirale : yeux qui tournent | clin : clin d'œil
for _e in EXPRESSIONS.values():
    for _cle in ("sourcil", "asym", "croix", "spirale", "clin"):
        _e.setdefault(_cle, 0)

ANIMEES = ("miam", "reflechit", "faim", "surpris", "ecoute", "eureka", "aie", "etourdi", "rire", "baille", "alerte")
JAUNE = QColor("#FFD23F")
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
        self.balance = 0.0                   # la tête qui dodeline (réflexion, étourdissement)
        self._humeur_vue, self._depuis = "repos", 0.0     # depuis quand il a cette humeur
        self._a_baille = False
        self._prochaine_manie = random.uniform(20, 45)   # petits gestes quand il ne se passe rien

    # ---------------------------------------------------------------- réactions
    def humeur(self):
        if self._passagere and self.t < self._fin_passagere:
            return self._passagere
        return "dort" if self.dodo and self.base == "repos" else self.base

    def reagir(self, humeur, duree=1.0):
        self._passagere, self._fin_passagere = humeur, self.t + duree
        if humeur in ("content", "miam", "surpris", "eureka", "alerte"):
            self.sauter(0.7 if humeur not in ("content", "eureka") else 1.0)
        if humeur in ("erreur", "aie"):
            self.tremble = 1.0

    def sauter(self, force=1.0):
        self.saut.vitesse -= 4.8 * force

    def hocher(self):
        self.tangage.vitesse -= 2.2

    def reveiller(self):
        self._souris_t = time.monotonic()
        self._a_baille = False
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

        # la vie quand il ne se passe rien : il bâille avant de s'endormir, cligne de l'œil, sautille
        if self.base == "repos" and not self._passagere_active():
            if immobile > SOMMEIL - 8 and not self.dodo and not self._a_baille:
                self._a_baille = True
                self.reagir("baille", 2.6)
            self._prochaine_manie -= dt
            if self._prochaine_manie <= 0 and not self.dodo:
                self._prochaine_manie = random.uniform(20, 45)
                if random.random() < 0.5:
                    self.reagir("clin", 0.8)
                else:
                    self.sauter(0.45)

        humeur = self.humeur()
        if humeur != self._humeur_vue:
            self._humeur_vue, self._depuis = humeur, self.t
        cible = EXPRESSIONS.get(humeur, EXPRESSIONS["repos"])
        k = 1 - math.exp(-dt * 11)
        for cle, v in cible.items():
            self.p[cle] += (v - self.p[cle]) * k
        if humeur == "miam":
            self.p["bouche"] = 0.12 + 0.4 * (0.5 + 0.5 * math.sin(self.t * 15))
        elif humeur == "rire":                       # il est secoué de rire
            self.p["bouche"] = 0.55 + 0.3 * math.sin(self.t * 22)
            if int(self.t * 6) != int((self.t - dt) * 6):
                self.saut.vitesse -= 1.5
        dodeline = {"reflechit": 0.13 * math.sin(self.t * 1.5), "etourdi": 0.22 * math.sin(self.t * 5.5),
                    "baille": -0.08}.get(humeur, 0.0)
        self.balance += (dodeline - self.balance) * (1 - math.exp(-dt * 9))

        # où regarder
        if humeur == "reflechit":
            lacet, tangage = 0.4 * math.sin(self.t * 0.9), 0.08 * math.sin(self.t * 2.3)
        elif humeur in ("tape", "dort", "aie", "etourdi", "baille", "eureka"):
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
                or self._clin > 0 or self.humeur() in ANIMEES)

    def _passagere_active(self):
        return bool(self._passagere) and self.t < self._fin_passagere

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
        p.rotate(math.degrees(P["incl"] + self.lacet.valeur * 0.12 + self.balance))
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
        self._effets(p, centre, R)

    # ---------------------------------------------------------------- ce qui flotte autour de lui
    def _effets(self, p, centre, R):
        """Engrenages quand il réfléchit, ampoule quand il trouve, étoiles quand il s'est cogné…
        Tout tient en haut à droite de sa tête, pour rester dans la bulle."""
        humeur, t = self.humeur(), self.t
        age = t - self._depuis
        fin = max(0.0, min(1.0, (self._fin_passagere - t) / 0.25)) if self._passagere_active() else 1.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(centre.x(), centre.y() + 0.28 * R + self.saut.valeur * R)
        apparition = min(1.0, age / 0.2)
        p.setOpacity(p.opacity() * apparition * fin)
        if humeur == "reflechit":
            self._engrenage(p, QPointF(0.9 * R, -1.02 * R), 0.36 * R, t * 1.7, 6, QColor(255, 255, 255, 235))
            self._engrenage(p, QPointF(1.36 * R, -0.6 * R), 0.24 * R, -t * 2.55 + 0.3, 5, MAUVE)
            if age > 8:
                self._sueur(p, R, t)
        elif humeur == "eureka":
            self._ampoule(p, R, age)
        elif humeur in ("aie", "etourdi"):
            self._etoiles(p, R, t)
        elif humeur == "rire":
            self._coeurs(p, R, t)
        elif humeur == "ecoute":
            self._ondes(p, R, t)
        elif humeur == "alerte":
            self._exclamation(p, R, age)
        elif humeur == "erreur":
            self._sueur(p, R, t)
        p.restore()

    @staticmethod
    def _engrenage(p, centre, rayon, angle, dents, couleur):
        roue, pas_dent = QPainterPath(), 2 * math.pi / dents
        for k in range(dents):
            a = angle + k * pas_dent
            for i, (r, da) in enumerate(((0.72, -0.3), (1.0, -0.17), (1.0, 0.17), (0.72, 0.3))):
                point = QPointF(centre.x() + rayon * r * math.cos(a + da * pas_dent * 1.6),
                                centre.y() + rayon * r * math.sin(a + da * pas_dent * 1.6))
                roue.lineTo(point) if (k or i) else roue.moveTo(point)
        roue.closeSubpath()
        trou = QPainterPath()
        trou.addEllipse(centre, rayon * 0.3, rayon * 0.3)
        p.setPen(Qt.NoPen)
        p.setBrush(couleur)
        p.drawPath(roue.subtracted(trou))

    @staticmethod
    def _etoile(p, x, y, s):
        etoile = QPainterPath(QPointF(x, y - s))
        for px, py in ((0.24, -0.24), (1, 0), (0.24, 0.24), (0, 1), (-0.24, 0.24), (-1, 0), (-0.24, -0.24)):
            etoile.lineTo(x + px * s, y + py * s)
        etoile.closeSubpath()
        p.drawPath(etoile)

    def _ampoule(self, p, R, age):
        pop = min(1.0, age / 0.22)
        echelle = pop + 0.35 * math.sin(math.pi * pop)          # elle surgit en dépassant un peu sa taille
        c, r = QPointF(0.95 * R, -1.02 * R), 0.36 * R * echelle
        lueur = QRadialGradient(c, 2.6 * r)
        lueur.setColorAt(0, QColor(255, 220, 90, round(150 + 50 * math.sin(self.t * 14))))
        lueur.setColorAt(1, QColor(255, 220, 90, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(lueur)
        p.drawEllipse(c, 2.6 * r, 2.6 * r)
        p.setBrush(QColor("#B9B3CC"))                             # le culot
        p.drawRoundedRect(QRectF(c.x() - 0.42 * r, c.y() + 0.7 * r, 0.84 * r, 0.62 * r), 0.15 * r, 0.15 * r)
        verre = QRadialGradient(QPointF(c.x() - 0.3 * r, c.y() - 0.35 * r), 1.4 * r)
        verre.setColorAt(0, QColor("#FFFBD6"))
        verre.setColorAt(1, JAUNE)
        p.setBrush(verre)
        p.drawEllipse(c, r, r)
        stylo = QPen(QColor(255, 226, 120, 230), max(0.9, 0.16 * r))
        stylo.setCapStyle(Qt.RoundCap)
        p.setPen(stylo)
        for angle in (-150, -90, -30):                            # les rayons
            a = math.radians(angle)
            p.drawLine(QPointF(c.x() + 1.35 * r * math.cos(a), c.y() + 1.35 * r * math.sin(a)),
                       QPointF(c.x() + 1.8 * r * math.cos(a), c.y() + 1.8 * r * math.sin(a)))

    def _etoiles(self, p, R, t):
        p.setPen(Qt.NoPen)
        p.setBrush(JAUNE)
        for k in range(3):                                        # elles tournent au-dessus de sa tête
            a = t * 5.5 + k * 2 * math.pi / 3
            self._etoile(p, 0.85 * R * math.cos(a), -1.18 * R + 0.26 * R * math.sin(a),
                         R * (0.17 + 0.05 * math.sin(a)))

    def _coeurs(self, p, R, t):
        p.setPen(Qt.NoPen)
        for k in range(2):
            phase = (t * 0.9 + k * 0.5) % 1
            x, y, s = (0.75 + 0.35 * k) * R, (-0.75 - 0.75 * phase) * R, R * (0.13 + 0.09 * phase)
            coeur = QPainterPath(QPointF(x, y + s))
            coeur.cubicTo(QPointF(x - 1.7 * s, y - 0.2 * s), QPointF(x - 0.6 * s, y - 1.3 * s), QPointF(x, y - 0.35 * s))
            coeur.cubicTo(QPointF(x + 0.6 * s, y - 1.3 * s), QPointF(x + 1.7 * s, y - 0.2 * s), QPointF(x, y + s))
            p.setBrush(QColor(JOUE.red(), JOUE.green(), JOUE.blue(), round(240 * math.sin(math.pi * phase))))
            p.drawPath(coeur)

    def _ondes(self, p, R, t):
        p.setBrush(Qt.NoBrush)
        for k in range(3):                                        # le son qui arrive
            phase = (t * 1.3 - k * 0.22) % 1
            stylo = QPen(QColor(255, 255, 255, round(210 * (1 - phase))), max(1.0, 0.09 * R))
            stylo.setCapStyle(Qt.RoundCap)
            p.setPen(stylo)
            r = R * (1.15 + 0.5 * phase)
            p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), 22 * 16, 44 * 16)

    def _exclamation(self, p, R, age):
        bond = abs(math.sin(age * 7)) * 0.18 * R
        x, y = 0.98 * R, -1.25 * R - bond
        p.setPen(Qt.NoPen)
        p.setBrush(JAUNE)
        p.drawRoundedRect(QRectF(x - 0.1 * R, y, 0.2 * R, 0.52 * R), 0.1 * R, 0.1 * R)
        p.drawEllipse(QPointF(x, y + 0.74 * R), 0.11 * R, 0.11 * R)

    def _sueur(self, p, R, t):
        phase = (t * 0.75) % 1
        x, y, s = -0.8 * R, (-0.78 + 0.34 * phase) * R, 0.15 * R
        goutte = QPainterPath(QPointF(x, y - 1.7 * s))
        goutte.cubicTo(QPointF(x + 0.3 * s, y - s), QPointF(x + s, y - 0.3 * s), QPointF(x + s, y + 0.2 * s))
        goutte.arcTo(QRectF(x - s, y - 0.8 * s, 2 * s, 2 * s), 0, -180)
        goutte.cubicTo(QPointF(x - s, y - 0.3 * s), QPointF(x - 0.3 * s, y - s), QPointF(x, y - 1.7 * s))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(150, 215, 255, round(235 * math.sin(math.pi * phase))))
        p.drawPath(goutte)

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
        trait = QPen(ENCRE, max(0.9, 0.06 * R))
        trait.setCapStyle(Qt.RoundCap)
        trait.setJoinStyle(Qt.RoundJoin)
        if P["croix"] > 0.5:                 # cogné : > <
            chevron = QPainterPath(QPointF(cote * w * 0.5, -0.13 * R))
            chevron.lineTo(QPointF(-cote * w * 0.35, 0))
            chevron.lineTo(QPointF(cote * w * 0.5, 0.13 * R))
            p.strokePath(chevron, trait)
            return
        if P["spirale"] > 0.5:               # étourdi : les yeux tournent
            spirale = QPainterPath(QPointF(0, 0))
            for i in range(1, 26):
                a = i * 0.52 + self.t * 9 * cote
                spirale.lineTo(QPointF(w * 0.62 * i / 25 * math.cos(a), w * 0.62 * i / 25 * math.sin(a)))
            p.strokePath(spirale, QPen(ENCRE, max(0.8, 0.045 * R)))
            return
        self._sourcil(p, R, cote, w, h)
        joie = max(P["joie"], P["clin"] if cote == 1 else 0)          # le clin d'œil ferme l'œil droit en ^
        plisse = 1 - 0.32 * P["asym"] * (cote == -1)                  # il plisse l'œil gauche en réfléchissant
        P = dict(P, joie=joie)
        hh = h * P["ouvert"] * clin * (1 - P["joie"]) * plisse
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

    def _sourcil(self, p, R, cote, w, h):
        """Froncé (il se concentre), levé (surprise), ou un de chaque (il réfléchit)."""
        s, asym = self.p["sourcil"], self.p["asym"]
        force = max(abs(s), asym)
        if force < 0.08:
            return
        if asym > 0.5:                       # le gauche froncé et bas, le droit levé
            s, leve = (s, -0.02 * R) if cote == -1 else (-0.5, 0.13 * R)
        else:
            leve = max(0.0, -s) * 0.09 * R
        y = -h * 0.78 - leve
        interieur = QPointF(-cote * w * 0.62, y + s * 0.1 * R)
        exterieur = QPointF(cote * w * 0.62, y - s * 0.05 * R)
        couleur = QColor(ENCRE)
        couleur.setAlphaF(borne(force * 1.5, 0, 1))
        stylo = QPen(couleur, max(0.9, 0.06 * R))
        stylo.setCapStyle(Qt.RoundCap)
        p.setPen(stylo)
        p.drawLine(interieur, exterieur)

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
        marge = 4.2 if halo else 3.5      # le halo et ce qui flotte autour de Plop débordent : on prévoit la place
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
