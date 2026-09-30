"""L'effet « goutte d'eau » : ressorts, déformation de la bulle et col liquide qui la relie au bord.

Le col est calculé dans un repère local où le bord de l'écran est la ligne y = 0 et la bulle
est en dessous ; repere_local() fait la conversion pour les quatre bords.
"""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QTransform

RUPTURE = 95      # écart au bord (px) où le col casse quand on tire la bulle
ACCROCHE = 30     # écart où une goutte libre se fait « aspirer » par le bord


def lerp(a, b, t):
    return a + (b - a) * t


def borne(x, a, b):
    return max(a, min(b, x))


class Ressort:
    """Ressort amorti : la valeur rejoint sa cible avec un peu de rebond."""

    def __init__(self, valeur=0.0, raideur=14.0, amorti=0.6):
        self.valeur = self.cible = valeur
        self.vitesse = 0.0
        self.raideur = raideur
        self.amorti = amorti

    def pas(self, dt):
        n = max(1, math.ceil(dt / 0.006))
        h = dt / n
        for _ in range(n):
            acc = (-2 * self.amorti * self.raideur * self.vitesse
                   - self.raideur ** 2 * (self.valeur - self.cible))
            self.vitesse += acc * h
            self.valeur += self.vitesse * h
        return self.valeur

    def calme(self, tolerance=0.002):
        return abs(self.valeur - self.cible) < tolerance and abs(self.vitesse) < tolerance * 20


def repere_local(bord, largeur, hauteur):
    """Transformation toile -> repère local (bord en y = 0, bulle vers les y positifs)."""
    if bord == "bas":
        return QTransform(-1, 0, 0, -1, largeur, hauteur)
    if bord == "gauche":
        return QTransform(0, 1, 1, 0, 0, 0)
    if bord == "droite":
        return QTransform(0, -1, 1, 0, 0, largeur)
    return QTransform()


NORMALES = {"haut": (0, 1), "bas": (0, -1), "gauche": (1, 0), "droite": (-1, 0)}


# ------------------------------------------------------------------ contour de la bulle

def contour(rect, rayon, pas_ligne=9.0, par_quart=7):
    """Points répartis sur le contour d'un rectangle arrondi (sens horaire à l'écran)."""
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    r = min(rayon, rect.width() / 2, rect.height() / 2)
    pts = []

    def ligne(xa, ya, xb, yb):
        longueur = math.hypot(xb - xa, yb - ya)
        if longueur < 0.5:
            return
        n = max(1, math.ceil(longueur / pas_ligne))
        for i in range(n):
            t = i / n
            pts.append((xa + (xb - xa) * t, ya + (yb - ya) * t))

    def arc(cx, cy, depart):
        for i in range(par_quart):
            a = math.radians(depart + 90 * i / par_quart)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    ligne(x0 + r, y0, x1 - r, y0)
    arc(x1 - r, y0 + r, -90)
    ligne(x1, y0 + r, x1, y1 - r)
    arc(x1 - r, y1 - r, 0)
    ligne(x1 - r, y1, x0 + r, y1)
    arc(x0 + r, y1 - r, 90)
    ligne(x0, y1 - r, x0, y0 + r)
    arc(x0 + r, y0 + r, 180)
    return pts


def deformer(pts, centre, etirement=0.0, angle=0.0, ecrase=0.0, normale=(0, 1), appui=0.0):
    """Déforme la bulle comme une goutte.

    etirement : la goutte s'allonge dans la direction `angle` avec une queue pointue derrière.
    ecrase    : aplatie (>0) ou étirée (<0) le long de `normale`, le côté collé au bord ne bouge pas.
    """
    cx, cy = centre.x(), centre.y()
    nx, ny = normale
    ux, uy = math.cos(angle), math.sin(angle)
    rmax = max(math.hypot(x - cx, y - cy) for x, y in pts) or 1.0
    sortie = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        if ecrase:
            dn = dx * nx + dy * ny
            dt = -dx * ny + dy * nx
            dn = (dn + appui) * (1 - ecrase) - appui
            dt *= 1 + 0.55 * ecrase
            dx, dy = dn * nx - dt * ny, dn * ny + dt * nx
        if etirement:
            da = dx * ux + dy * uy
            db = -dx * uy + dy * ux
            if da < 0:
                da *= 1 + 0.3 * etirement + 1.5 * etirement * (-da / rmax) ** 2
            else:
                da *= 1 + 0.3 * etirement
            db /= 1 + 0.35 * etirement
            dx, dy = da * ux - db * uy, da * uy + db * ux
        sortie.append((cx + dx, cy + dy))
    return sortie


def lisse(pts):
    """Courbe fermée bien ronde qui passe par tous les points (Catmull-Rom)."""
    n = len(pts)
    chemin = QPainterPath(QPointF(*pts[0]))
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        chemin.cubicTo(QPointF(p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6),
                       QPointF(p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6),
                       QPointF(*p2))
    chemin.closeSubpath()
    return chemin


# ------------------------------------------------------------------ col liquide

def col(rect, rayon, tension, force, panneau):
    """Le col qui relie la bulle au bord, dans le repère local (bord en y = 0).

    tension : 0 = bulle collée, 1 = sur le point de casser (le col s'affine).
    force   : 0..1, le col apparaît / disparaît.
    panneau : 0 = petite goutte (col pincé), 1 = grand panneau (épaules arrondies).
    """
    if force < 0.02 or rect.top() < -1:
        return None
    t = borne(tension, 0.0, 1.0)
    r = min(rayon, rect.width() / 2, rect.height() / 2)
    rond = borne(1 - (rect.width() - rect.height()) / 20, 0.0, 1.0)   # 1 = goutte ronde, 0 = capsule
    phi = math.radians(lerp(lerp(lerp(66, 90, panneau), 52, rond), 16, t))
    pince = lerp(0.32 * rond, 0.9, t)
    pince = borne(1 - (1 - pince) * force, 0.0, 0.97)
    epaule = lerp(lerp(9, 13, panneau), 1.5, t) * force
    haut_taille = lerp(0.5, 0.42, t)
    cy = rect.top() + r
    coins = {-1: rect.left() + r, 1: rect.right() - r}

    def cote(sgn):
        cx = coins[sgn]
        pl = QPointF(cx + sgn * r * math.sin(phi), cy - r * math.cos(phi))
        vers_bas = QPointF(sgn * math.cos(phi), math.sin(phi))   # le contour repart vers l'extérieur
        segments = []
        if pince < 0.03:
            q = QPointF(pl.x() + sgn * epaule, 0)
            k = pl.y() * 0.55
            segments.append((q, q + QPointF(-sgn * epaule * 0.55, 0), pl - vers_bas * k, pl))
        else:
            w = QPointF(pl.x() + (cx - pl.x()) * pince, pl.y() * haut_taille)
            q = QPointF(w.x() + sgn * epaule, 0)
            segments.append((q, q + QPointF(-sgn * epaule * 0.6, 0), w - QPointF(0, w.y() * 0.5), w))
            k = math.hypot(pl.x() - w.x(), pl.y() - w.y()) * 0.45
            segments.append((w, w + QPointF(0, (pl.y() - w.y()) * 0.5), pl - vers_bas * k, pl))
        return segments

    gauche, droite = cote(-1), cote(1)
    chemin = QPainterPath(QPointF(gauche[0][0].x(), -40))
    chemin.lineTo(gauche[0][0])
    for _, c1, c2, fin in gauche:
        chemin.cubicTo(c1, c2, fin)
    chemin.lineTo(coins[-1], cy)
    chemin.lineTo(coins[1], cy)
    chemin.lineTo(droite[-1][3])
    for debut, c1, c2, _ in reversed(droite):
        chemin.cubicTo(c2, c1, debut)
    chemin.lineTo(droite[0][0].x(), -40)
    chemin.closeSubpath()
    return chemin
