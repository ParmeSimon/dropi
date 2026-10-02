"""Jouer avec Dropi : des mini-jeux en 1 contre 1, Dropi est l'adversaire.

Morpion (Dropi calcule, mais se trompe parfois), pierre-feuille-ciseaux (Dropi apprend tes habitudes) et
réflexe (qui clique le premier quand ça passe au vert). Tout se joue sur le PC, sans IA ni internet :
Dropi répond tout de suite.

La logique (règles, adversaire) est en haut du fichier, sans interface, pour pouvoir être testée seule.
"""
import random
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QIntValidator
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedLayout, QAbstractButton)

import composants as ui
from mascotte import VueMascotte

# ============================================================== la logique

LIGNES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def ligne_gagnante(grille):
    """(joueur, cases) si trois sont alignées, sinon None. Une grille = 9 cases : "X" (toi), "O" (Dropi) ou ""."""
    for a, b, c in LIGNES:
        if grille[a] and grille[a] == grille[b] == grille[c]:
            return grille[a], (a, b, c)
    return None


_CACHE = {}


def _valeur(grille, joueur, profondeur=0):
    """Minimax : +10 si Dropi (O) gagne, -10 si X gagne, plus tôt = mieux pour celui qui gagne.
    Mis en cache par position : la grille vide ne coûte qu'une fois (sinon ~1 s de calcul au premier coup)."""
    cle = (tuple(grille), joueur)
    if cle in _CACHE:
        return _CACHE[cle]
    fin = ligne_gagnante(grille)
    if fin:
        valeur = 10 if fin[0] == "O" else -10
    else:
        libres = [i for i, c in enumerate(grille) if not c]
        if not libres:
            valeur = 0
        else:
            valeurs = []
            for i in libres:
                grille[i] = joueur
                valeurs.append(_valeur(grille, "X" if joueur == "O" else "O", profondeur + 1))
                grille[i] = ""
            valeur = max(valeurs) if joueur == "O" else min(valeurs)
            valeur += -1 if valeur > 0 else (1 if valeur < 0 else 0)       # gagner plus vite (perdre plus tard) vaut mieux
    _CACHE[cle] = valeur
    return valeur


def coup_dropi(grille, erreur=0.2):
    """Le coup de Dropi (O). Une fois sur cinq il joue n'importe où : on peut le battre."""
    libres = [i for i, c in enumerate(grille) if not c]
    if not libres:
        return None
    if random.random() < erreur:
        return random.choice(libres)
    meilleurs, score = [], -99
    for i in libres:
        grille[i] = "O"
        v = _valeur(grille, "X", 1)
        grille[i] = ""
        if v > score:
            meilleurs, score = [i], v
        elif v == score:
            meilleurs.append(i)
    return random.choice(meilleurs)


COUPS = ("pierre", "feuille", "ciseaux")
EMOJI = {"pierre": "✊", "feuille": "✋", "ciseaux": "✌️"}
BAT = {"pierre": "ciseaux", "feuille": "pierre", "ciseaux": "feuille"}      # clé bat valeur


def issue(toi, dropi):
    """1 : tu gagnes la manche, -1 : Dropi, 0 : égalité."""
    if toi == dropi:
        return 0
    return 1 if BAT[toi] == dropi else -1


class AdversairePFC:
    """Dropi regarde ce que tu joues le plus souvent et tente de le battre (une fois sur deux), sinon au hasard."""

    def __init__(self):
        self.vus = {c: 0 for c in COUPS}

    def jouer(self):
        if sum(self.vus.values()) >= 3 and random.random() < 0.5:
            frequent = max(self.vus, key=self.vus.get)
            return next(c for c in COUPS if BAT[c] == frequent)
        return random.choice(COUPS)

    def noter(self, coup):
        self.vus[coup] += 1


def temps_dropi():
    """Le temps de réaction de Dropi, en ms : rapide mais battable."""
    return max(240, min(520, random.gauss(340, 55)))


REPLIQUES = {
    "gagne": ["Hihi, j'ai gagné !", "Trop facile ! 😏", "Pas mal, mais pas assez.", "Un point pour moi !"],
    "perd": ["Aïe… bien joué !", "Chanceux, tu as eu de la chance !", "Hmm, je veux ma revanche.", "Oh non, tu es fort."],
    "egal": ["Égalité… on recommence ?", "On pense pareil, c'est suspect.", "Pile pareil !"],
    "debut": ["Prêt ? Je ne me laisserai pas faire.", "Allez, montre ce que tu sais faire !", "À toi de jouer !"],
}


def replique(genre):
    return random.choice(REPLIQUES[genre])


# ============================================================== les éléments d'interface

VIOLET = QColor("#C4B5FD")             # la couleur de Dropi


class Case(QAbstractButton):
    """Une case du morpion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.marque, self.gagnante = "", False
        self.setFixedSize(86, 86)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def regler(self, marque, gagnante=False):
        self.marque, self.gagnante = marque, gagnante
        self.setCursor(Qt.ArrowCursor if marque else Qt.PointingHandCursor)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        survol = self.underMouse() and self.isEnabled() and not self.marque
        fond = ui.CARTE_SURVOL if survol else ui.CARTE
        if self.gagnante:
            fond = QColor(ui.SUCCES.red(), ui.SUCCES.green(), ui.SUCCES.blue(), 60)
        p.setPen(QPen(ui.CONTOUR, 1))
        p.setBrush(fond)
        p.drawRoundedRect(r, 14, 14)
        c = r.center()
        d = r.width() * 0.24
        if self.marque == "X":
            p.setPen(QPen(ui.accent(), 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))
        elif self.marque == "O":
            p.setPen(QPen(VIOLET, 7))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, d * 1.1, d * 1.1)


class GrosBouton(QAbstractButton):
    """Un grand bouton avec un emoji et un petit libellé dessous (pierre, feuille, ciseaux)."""

    def __init__(self, emoji, libelle, parent=None):
        super().__init__(parent)
        self.emoji, self.libelle = emoji, libelle
        self.setFixedSize(112, 104)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        actif = self.isEnabled()
        fond = ui.CARTE_APPUI if self.isDown() else (ui.CARTE_SURVOL if self.underMouse() and actif else ui.CARTE)
        p.setPen(QPen(ui.CONTOUR, 1))
        p.setBrush(fond)
        p.drawRoundedRect(r, 16, 16)
        police = ui.police(30)
        police.setFamily("Segoe UI Emoji")
        p.setFont(police)
        p.setPen(ui.TEXTE if actif else ui.TEXTE_3)
        p.drawText(QRectF(r.left(), r.top() + 8, r.width(), 54), Qt.AlignCenter, self.emoji)
        p.setFont(ui.police(12))
        p.setPen(ui.TEXTE_2 if actif else ui.TEXTE_3)
        p.drawText(QRectF(r.left(), r.top() + 64, r.width(), 28), Qt.AlignCenter, self.libelle)


class Zone(QAbstractButton):
    """La grande zone du jeu de réflexe : repos, attente (rouge), go (vert), résultat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.etat, self.texte, self.detail = "repos", "", ""
        self.setMinimumHeight(150)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def regler(self, etat, texte, detail=""):
        self.etat, self.texte, self.detail = etat, texte, detail
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        couleur = {"attente": QColor(240, 82, 79, 120), "go": QColor(108, 203, 95, 200)}.get(self.etat, ui.CARTE)
        if self.etat == "repos" and self.underMouse():
            couleur = ui.CARTE_SURVOL
        p.setPen(QPen(ui.CONTOUR, 1))
        p.setBrush(couleur)
        p.drawRoundedRect(r, 18, 18)
        p.setPen(QColor(0, 0, 0) if self.etat == "go" else ui.TEXTE)
        p.setFont(ui.police(22 if self.etat == "go" else 17, True))
        p.drawText(r.adjusted(10, 0, -10, -18 if self.detail else 0), Qt.AlignCenter | Qt.TextWordWrap, self.texte)
        if self.detail:
            p.setPen(ui.TEXTE_2)
            p.setFont(ui.police(12))
            p.drawText(r.adjusted(10, 0, -10, -12), Qt.AlignHCenter | Qt.AlignBottom, self.detail)


def _score(parent=None):
    e = ui.Etiquette("", 13, ui.TEXTE_2, gras=True)
    e.setAlignment(Qt.AlignCenter)
    return e


def _parole(parent=None):
    e = ui.Etiquette("", 13, ui.TEXTE_3)
    e.setAlignment(Qt.AlignCenter)
    e.setWordWrap(True)
    e.setMinimumHeight(36)
    return e


# ============================================================== les jeux

class Morpion(QWidget):
    humeur = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self.grille, self.fini, self.dropi_commence = [""] * 9, True, False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.score = _score()
        lay.addWidget(self.score)
        grille = QGridLayout()
        grille.setSpacing(8)
        self.cases = [Case() for _ in range(9)]
        for i, case in enumerate(self.cases):
            case.clicked.connect(lambda _=False, n=i: self._clic(n))
            grille.addWidget(case, i // 3, i % 3)
        centre = QHBoxLayout()
        centre.addStretch(1)
        centre.addLayout(grille)
        centre.addStretch(1)
        lay.addLayout(centre)
        self.parole = _parole()
        lay.addWidget(self.parole)
        self.rejouer = ui.Bouton("regenerer", "Rejouer", "puce")
        self.rejouer.clicked.connect(self.nouvelle)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(self.rejouer)
        bas.addStretch(1)
        lay.addLayout(bas)
        self._attente = QTimer(self, singleShot=True, timeout=self._dropi_joue)

    def commencer(self):
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self.dropi_commence = random.random() < 0.5
        self.nouvelle(sans_alterner=True)

    def nouvelle(self, sans_alterner=False):
        self._attente.stop()
        if not sans_alterner:
            self.dropi_commence = not self.dropi_commence
        self.grille, self.fini = [""] * 9, False
        for case in self.cases:
            case.regler("")
        self.rejouer.hide()
        self._maj_score()
        if self.dropi_commence:
            self.parole.setText("Je commence !")
            self._attente.start(600)
        else:
            self.parole.setText("À toi (les croix). " + replique("debut"))

    def _maj_score(self):
        v = self.victoires
        self.score.setText(f"Toi {v['X']}   –   {v['O']} Dropi      (nuls : {v['nul']})")

    def _clic(self, n):
        if self.fini or self.grille[n] or self._attente.isActive():
            return
        self._jouer(n, "X")
        if not self.fini:
            self.parole.setText("Hmm, je réfléchis…")
            self._attente.start(random.randint(450, 900))

    def _dropi_joue(self):
        n = coup_dropi(self.grille)
        if n is not None and not self.fini:
            self._jouer(n, "O")
            if not self.fini:
                self.parole.setText("À toi !")

    def _jouer(self, n, joueur):
        self.grille[n] = joueur
        self.cases[n].regler(joueur)
        fin = ligne_gagnante(self.grille)
        if fin:
            for i in fin[1]:
                self.cases[i].regler(self.grille[i], True)
            self._terminer(fin[0])
        elif all(self.grille):
            self._terminer("nul")

    def _terminer(self, resultat):
        self.fini = True
        self.victoires[resultat] += 1
        self._maj_score()
        if resultat == "X":
            self.parole.setText(replique("perd"))
            self.humeur.emit("erreur", 1.4)
        elif resultat == "O":
            self.parole.setText(replique("gagne"))
            self.humeur.emit("content", 1.6)
        else:
            self.parole.setText(replique("egal"))
            self.humeur.emit("surpris", 1.2)
        self.rejouer.show()


class PierreFeuilleCiseaux(QWidget):
    humeur = Signal(str, float)
    POINTS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [0, 0]
        self.adversaire = AdversairePFC()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.score = _score()
        lay.addWidget(self.score)
        self.duel = ui.Etiquette("", 40, ui.TEXTE)
        police = self.duel.font()
        police.setFamily("Segoe UI Emoji")
        self.duel.setFont(police)
        self.duel.setAlignment(Qt.AlignCenter)
        self.duel.setMinimumHeight(64)
        lay.addWidget(self.duel)
        self.parole = _parole()
        lay.addWidget(self.parole)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        rangee.addStretch(1)
        self.boutons = []
        for coup in COUPS:
            b = GrosBouton(EMOJI[coup], coup.capitalize())
            b.clicked.connect(lambda _=False, c=coup: self._jouer(c))
            self.boutons.append(b)
            rangee.addWidget(b)
        rangee.addStretch(1)
        lay.addLayout(rangee)
        self.rejouer = ui.Bouton("regenerer", "Nouvelle partie", "puce")
        self.rejouer.clicked.connect(self.commencer)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(self.rejouer)
        bas.addStretch(1)
        lay.addLayout(bas)

    def commencer(self):
        self.points = [0, 0]
        self.adversaire = AdversairePFC()
        self.duel.setText("")
        self.parole.setText(f"Premier à {self.POINTS} points. " + replique("debut"))
        self.rejouer.hide()
        for b in self.boutons:
            b.setEnabled(True)
        self._maj_score()

    def _maj_score(self):
        self.score.setText(f"Toi {self.points[0]}   –   {self.points[1]} Dropi")

    def _jouer(self, coup):
        dropi = self.adversaire.jouer()
        self.adversaire.noter(coup)
        self.duel.setText(f"{EMOJI[coup]}   contre   {EMOJI[dropi]}")
        r = issue(coup, dropi)
        if r > 0:
            self.points[0] += 1
            self.parole.setText(f"{coup.capitalize()} bat {dropi}. " + replique("perd"))
            self.humeur.emit("aie", 0.9)
        elif r < 0:
            self.points[1] += 1
            self.parole.setText(f"{dropi.capitalize()} bat {coup}. " + replique("gagne"))
            self.humeur.emit("content", 1.0)
        else:
            self.parole.setText(replique("egal"))
            self.humeur.emit("surpris", 0.8)
        self._maj_score()
        if self.POINTS in self.points:
            gagne = self.points[0] == self.POINTS
            self.parole.setText(("Tu as gagné la partie, bravo ! " + replique("perd")) if gagne
                                else "J'ai gagné la partie ! " + replique("gagne"))
            self.humeur.emit("erreur" if gagne else "eureka", 1.8)
            for b in self.boutons:
                b.setEnabled(False)
            self.rejouer.show()


class Reflexe(QWidget):
    humeur = Signal(str, float)
    POINTS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points, self.etat, self._debut, self._dropi = [0, 0], "repos", 0.0, 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.score = _score()
        lay.addWidget(self.score)
        self.zone = Zone()
        self.zone.clicked.connect(self._clic)
        lay.addWidget(self.zone, 1)
        self.parole = _parole()
        lay.addWidget(self.parole)
        self._minuteur = QTimer(self, singleShot=True, timeout=self._go)

    def commencer(self):
        self.points, self.etat = [0, 0], "repos"
        self._minuteur.stop()
        self.zone.regler("repos", "Prêt ?", "Clique pour lancer la manche. Clique dès que ça passe au vert !")
        self.parole.setText(f"Premier à {self.POINTS} manches. Si tu cliques trop tôt, je gagne.")
        self._maj_score()

    def _maj_score(self):
        self.score.setText(f"Toi {self.points[0]}   –   {self.points[1]} Dropi")

    def _clic(self):
        if self.etat == "repos":
            self.etat = "attente"
            self.zone.regler("attente", "Attends le vert…")
            self._minuteur.start(random.randint(1500, 4000))
        elif self.etat == "attente":          # parti trop tôt
            self._minuteur.stop()
            self._fin_manche(None, "Trop tôt ! Tu as cliqué avant le vert.")
        elif self.etat == "go":
            ms = (time.monotonic() - self._debut) * 1000
            self._fin_manche(ms < self._dropi, f"Toi {ms:.0f} ms   ·   Dropi {self._dropi:.0f} ms")

    def _go(self):
        self.etat, self._debut, self._dropi = "go", time.monotonic(), temps_dropi()
        self.zone.regler("go", "CLIQUE !")

    def _fin_manche(self, toi, detail):
        if toi:
            self.points[0] += 1
            self.humeur.emit("aie", 0.9)
            self.parole.setText(replique("perd"))
        else:
            self.points[1] += 1
            self.humeur.emit("content", 1.0)
            self.parole.setText(replique("gagne"))
        self._maj_score()
        if self.POINTS in self.points:
            gagne = self.points[0] == self.POINTS
            self.etat = "fini"
            self.zone.regler("repos", "Tu as gagné !" if gagne else "J'ai gagné !", detail + "   ·   Clique pour rejouer")
            self.humeur.emit("erreur" if gagne else "eureka", 1.8)
            self.zone.clicked.disconnect()
            self.zone.clicked.connect(self._rejouer)
        else:
            self.etat = "repos"
            self.zone.regler("repos", "Manche suivante ?", detail)

    def _rejouer(self):
        self.zone.clicked.disconnect()
        self.zone.clicked.connect(self._clic)
        self.commencer()


# ============================================================== Puissance 4, Mémoire, Devine le nombre

class Chrono:
    """Des petites attentes (« Dropi réfléchit… ») qui s'annulent si on change de jeu ou de partie."""

    def _apres(self, ms, fonction):
        generation = self._generation
        QTimer.singleShot(ms, lambda: fonction() if generation == self._generation else None)

    def _annuler_attentes(self):
        self._generation = getattr(self, "_generation", 0) + 1


# ---------------------------------------------------------------- Puissance 4 : la logique
RANGEES, COLONNES = 6, 7
ORDRE_COLONNES = [3, 2, 4, 1, 5, 0, 6]                  # le centre d'abord : meilleurs coups examinés en premier
FENETRES = [[(r + dr * k, c + dc * k) for k in range(4)]
            for r in range(RANGEES) for c in range(COLONNES) for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1))
            if 0 <= r + dr * 3 < RANGEES and 0 <= c + dc * 3 < COLONNES]


def p4_vide():
    return [[""] * COLONNES for _ in range(RANGEES)]


def p4_rangee_libre(g, c):
    for r in range(RANGEES - 1, -1, -1):
        if not g[r][c]:
            return r
    return None


def p4_gagnant(g):
    """(joueur, quatre cases) ou None."""
    for fenetre in FENETRES:
        a = g[fenetre[0][0]][fenetre[0][1]]
        if a and all(g[r][c] == a for r, c in fenetre):
            return a, fenetre
    return None


def _p4_valeur(g, joueur):
    """Évaluation d'une position pour `joueur` : alignements en cours, centre."""
    adverse = "X" if joueur == "O" else "O"
    total = sum(3 for r in range(RANGEES) if g[r][3] == joueur) - sum(3 for r in range(RANGEES) if g[r][3] == adverse)
    for fenetre in FENETRES:
        cases = [g[r][c] for r, c in fenetre]
        mien, autre = cases.count(joueur), cases.count(adverse)
        if mien and autre:
            continue
        if mien == 3:
            total += 6
        elif mien == 2:
            total += 2
        elif autre == 3:
            total -= 7
        elif autre == 2:
            total -= 2
    return total


def _p4_nega(g, profondeur, alpha, beta, joueur):
    adverse = "X" if joueur == "O" else "O"
    if p4_gagnant(g):                                   # le dernier à avoir joué (l'adversaire) a gagné
        return -(1000 + profondeur)
    colonnes = [c for c in ORDRE_COLONNES if not g[0][c]]
    if not colonnes:
        return 0
    if profondeur == 0:
        return _p4_valeur(g, joueur)
    meilleur = -10 ** 6
    for c in colonnes:
        r = p4_rangee_libre(g, c)
        g[r][c] = joueur
        valeur = -_p4_nega(g, profondeur - 1, -beta, -alpha, adverse)
        g[r][c] = ""
        meilleur = max(meilleur, valeur)
        alpha = max(alpha, valeur)
        if alpha >= beta:
            break
    return meilleur


def coup_dropi_p4(g, erreur=0.1, profondeur=4):
    """La colonne que joue Dropi (O) : il voit `profondeur` coups d'avance, et se plante une fois sur dix."""
    colonnes = [c for c in range(COLONNES) if not g[0][c]]
    if not colonnes:
        return None
    if random.random() < erreur:
        return random.choice(colonnes)
    meilleurs, score = [], -10 ** 6
    for c in colonnes:
        r = p4_rangee_libre(g, c)
        g[r][c] = "O"
        valeur = -_p4_nega(g, profondeur - 1, -10 ** 6, 10 ** 6, "X")
        g[r][c] = ""
        if valeur > score:
            meilleurs, score = [c], valeur
        elif valeur == score:
            meilleurs.append(c)
    return random.choice(meilleurs)


# ---------------------------------------------------------------- Mémoire : la logique
SYMBOLES = ["🍎", "🐱", "🚀", "🎸", "🌵", "🍕", "⚽", "🦊"]
SOUVENIR = 0.6                                          # chances que Dropi retienne une carte qu'il voit


def memoire_paquet():
    cartes = SYMBOLES * 2
    random.shuffle(cartes)
    return cartes


def memoire_choix_dropi(cartes, trouvees, connu, premiere=None):
    """Quelle carte Dropi retourne : une paire qu'il a retenue, sinon une carte qu'il n'a jamais vue, sinon au hasard.
    connu : {index: symbole} ce dont il se souvient. premiere : la carte déjà retournée ce tour-ci (ou None)."""
    cachees = [i for i in range(len(cartes)) if i not in trouvees and i != premiere]
    if premiere is not None:                           # il cherche le jumeau de la première carte
        jumeaux = [i for i in cachees if connu.get(i) == cartes[premiere]]
        if jumeaux:
            return jumeaux[0]
    else:
        vus = {}
        for i in cachees:
            if i in connu:
                vus.setdefault(connu[i], []).append(i)
        paires = [v[0] for v in vus.values() if len(v) >= 2]
        if paires:
            return random.choice(paires)
    inconnues = [i for i in cachees if i not in connu]
    return random.choice(inconnues or cachees)


# ---------------------------------------------------------------- Devine le nombre : la logique
def nombre_propose(bas, haut):
    """Le nombre que Dropi essaie : le milieu, à deux près (il n'est pas parfait)."""
    milieu = (bas + haut) // 2
    return max(bas, min(haut, milieu + random.randint(-2, 2)))


# ---------------------------------------------------------------- les éléments d'interface
class Plateau(QWidget):
    """Le plateau du Puissance 4 : on clique sur une colonne, le pion tombe."""
    colonne = Signal(int)
    CASE, ECART, BORD = 46, 4, 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grille, self.gagnantes, self.survol, self.chute = p4_vide(), set(), -1, None
        self.actif = True
        self.setFixedSize(COLONNES * self.CASE + (COLONNES - 1) * self.ECART + 2 * self.BORD,
                          RANGEES * self.CASE + (RANGEES - 1) * self.ECART + 2 * self.BORD)
        self.setMouseTracking(True)
        self._temps = QTimer(self, interval=16, timeout=self._tomber)

    def _centre(self, r, c):
        pas = self.CASE + self.ECART
        return QPointF(self.BORD + c * pas + self.CASE / 2, self.BORD + r * pas + self.CASE / 2)

    def lacher(self, c, r, joueur, fin):
        """Un pion tombe dans la colonne c jusqu'à la rangée r ; fin() quand il est posé."""
        self.chute = {"c": c, "r": r, "joueur": joueur, "y": -1.0, "v": 0.0, "fin": fin}
        self._temps.start()

    def _tomber(self):
        ch = self.chute
        ch["v"] += 0.06
        ch["y"] += ch["v"]
        if ch["y"] >= ch["r"]:
            self._temps.stop()
            self.chute = None
            ch["fin"]()
        self.update()

    def mouseMoveEvent(self, e):
        c = int((e.position().x() - self.BORD) // (self.CASE + self.ECART))
        c = c if 0 <= c < COLONNES else -1
        if c != self.survol:
            self.survol = c
            self.update()

    def leaveEvent(self, _):
        self.survol = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.actif and self.chute is None and self.survol >= 0:
            self.colonne.emit(self.survol)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(ui.CONTOUR, 1))
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        rayon = self.CASE / 2 - 3
        for c in range(COLONNES):
            if c == self.survol and self.actif and self.chute is None:
                pas = self.CASE + self.ECART
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 14))
                p.drawRoundedRect(QRectF(self.BORD + c * pas - 2, 4, self.CASE + 4, self.height() - 8), 10, 10)
            for r in range(RANGEES):
                joueur = self.grille[r][c]
                centre = self._centre(r, c)
                if not joueur:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(0, 0, 0, 70))
                else:
                    self._pion(p, centre, rayon, joueur, (r, c) in self.gagnantes)
                    continue
                p.drawEllipse(centre, rayon, rayon)
        if self.chute:
            ch = self.chute
            pas = self.CASE + self.ECART
            centre = QPointF(self._centre(0, ch["c"]).x(), self.BORD + self.CASE / 2 + ch["y"] * pas)
            self._pion(p, centre, rayon, ch["joueur"], False)

    @staticmethod
    def _pion(p, centre, rayon, joueur, gagnant):
        couleur = ui.accent() if joueur == "X" else VIOLET
        p.setPen(QPen(QColor(255, 255, 255, 230), 3) if gagnant else Qt.NoPen)
        p.setBrush(couleur)
        p.drawEllipse(centre, rayon, rayon)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawEllipse(QPointF(centre.x() - rayon * 0.25, centre.y() - rayon * 0.3), rayon * 0.45, rayon * 0.35)


class CarteMemoire(QAbstractButton):
    """Une carte du jeu de mémoire : dos (point d'interrogation), face (emoji), ou trouvée."""

    def __init__(self, symbole, parent=None):
        super().__init__(parent)
        self.symbole, self.etat, self.par = symbole, "cachee", ""       # cachee | visible | trouvee
        self.setFixedSize(66, 66)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def regler(self, etat, par=""):
        self.etat, self.par = etat, par
        self.setCursor(Qt.PointingHandCursor if etat == "cachee" else Qt.ArrowCursor)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.etat == "cachee":
            a = ui.accent()
            fond = QColor(a.red(), a.green(), a.blue(), 150 if self.underMouse() else 110)
            p.setPen(QPen(ui.CONTOUR, 1))
            p.setBrush(fond)
            p.drawRoundedRect(r, 12, 12)
            p.setPen(QColor(255, 255, 255, 190))
            p.setFont(ui.police(22, True))
            p.drawText(r, Qt.AlignCenter, "?")
            return
        contour = {"X": ui.accent(), "O": VIOLET}.get(self.par, ui.CONTOUR)
        p.setPen(QPen(contour, 2 if self.etat == "trouvee" else 1))
        p.setBrush(QColor(255, 255, 255, 30) if self.etat == "visible" else QColor(255, 255, 255, 12))
        p.drawRoundedRect(r, 12, 12)
        police = ui.police(26)
        police.setFamily("Segoe UI Emoji")
        p.setFont(police)
        p.setPen(QColor(255, 255, 255, 255 if self.etat == "visible" else 150))
        p.drawText(r, Qt.AlignCenter, self.symbole)


# ---------------------------------------------------------------- les jeux
class Puissance4(QWidget, Chrono):
    humeur = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self.fini, self.dropi_commence, self._generation = True, False, 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.score = _score()
        lay.addWidget(self.score)
        self.plateau = Plateau()
        self.plateau.colonne.connect(self._clic)
        centre = QHBoxLayout()
        centre.addStretch(1)
        centre.addWidget(self.plateau)
        centre.addStretch(1)
        lay.addLayout(centre)
        self.parole = _parole()
        lay.addWidget(self.parole)
        self.rejouer = ui.Bouton("regenerer", "Rejouer", "puce")
        self.rejouer.clicked.connect(self.nouvelle)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(self.rejouer)
        bas.addStretch(1)
        lay.addLayout(bas)

    def commencer(self):
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self.dropi_commence = random.random() < 0.5
        self.nouvelle(sans_alterner=True)

    def nouvelle(self, sans_alterner=False):
        self._annuler_attentes()
        if not sans_alterner:
            self.dropi_commence = not self.dropi_commence
        self.plateau.grille, self.plateau.gagnantes, self.plateau.chute = p4_vide(), set(), None
        self.plateau.actif, self.fini = True, False
        self.plateau.update()
        self.rejouer.hide()
        self._maj_score()
        if self.dropi_commence:
            self.parole.setText("Je commence !")
            self.plateau.actif = False
            self._apres(600, self._dropi_joue)
        else:
            self.parole.setText("À toi (les pions de ta couleur). " + replique("debut"))

    def _maj_score(self):
        v = self.victoires
        self.score.setText(f"Toi {v['X']}   –   {v['O']} Dropi      (nuls : {v['nul']})")

    def _clic(self, c):
        g = self.plateau.grille
        if self.fini or not self.plateau.actif or g[0][c]:
            return
        self.plateau.actif = False
        self._poser(c, "X", self._apres_joueur)

    def _poser(self, c, joueur, suite):
        r = p4_rangee_libre(self.plateau.grille, c)
        self.plateau.lacher(c, r, joueur, lambda: self._pose(c, r, joueur, suite))

    def _pose(self, c, r, joueur, suite):
        g = self.plateau.grille
        g[r][c] = joueur
        fin = p4_gagnant(g)
        if fin:
            self.plateau.gagnantes = set(fin[1])
            self._terminer(fin[0])
        elif all(g[0]):
            self._terminer("nul")
        else:
            suite()
        self.plateau.update()

    def _apres_joueur(self):
        self.parole.setText("Hmm, je réfléchis…")
        self._apres(random.randint(500, 1000), self._dropi_joue)

    def _dropi_joue(self):
        c = coup_dropi_p4(self.plateau.grille)
        if c is not None:
            self._poser(c, "O", self._rendre_la_main)

    def _rendre_la_main(self):
        self.plateau.actif = True
        self.parole.setText("À toi !")

    def _terminer(self, resultat):
        self.fini, self.plateau.actif = True, False
        self.victoires[resultat] += 1
        self._maj_score()
        texte, humeur = {"X": (replique("perd"), "erreur"), "O": (replique("gagne"), "content"),
                         "nul": (replique("egal"), "surpris")}[resultat]
        self.parole.setText(texte)
        self.humeur.emit(humeur, 1.6)
        self.rejouer.show()


class Memoire(QWidget, Chrono):
    humeur = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cartes, self.boutons, self._generation = [], [], 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.score = _score()
        lay.addWidget(self.score)
        self.grille = QGridLayout()
        self.grille.setSpacing(8)
        centre = QHBoxLayout()
        centre.addStretch(1)
        centre.addLayout(self.grille)
        centre.addStretch(1)
        lay.addLayout(centre)
        self.parole = _parole()
        lay.addWidget(self.parole)
        self.rejouer = ui.Bouton("regenerer", "Rejouer", "puce")
        self.rejouer.clicked.connect(self.commencer)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(self.rejouer)
        bas.addStretch(1)
        lay.addLayout(bas)

    def commencer(self):
        self._annuler_attentes()
        for b in self.boutons:
            self.grille.removeWidget(b)
            b.deleteLater()
        self.cartes = memoire_paquet()
        self.boutons = []
        for i, symbole in enumerate(self.cartes):
            b = CarteMemoire(symbole)
            b.clicked.connect(lambda _=False, n=i: self._clic(n))
            self.boutons.append(b)
            self.grille.addWidget(b, i // 4, i % 4)
        self.trouvees, self.connu, self.points = {}, {}, [0, 0]
        self.premiere, self.tour, self.bloque = None, "X", False
        self.rejouer.hide()
        self.parole.setText("Retourne deux cartes identiques. Si tu trouves une paire, tu rejoues ! " + replique("debut"))
        self._maj_score()

    def _maj_score(self):
        self.score.setText(f"Toi {self.points[0]}   –   {self.points[1]} Dropi      (paires : {sum(self.points)}/8)")

    def _retenir(self, i):
        if random.random() < SOUVENIR:
            self.connu[i] = self.cartes[i]

    def _clic(self, i):
        if self.tour != "X" or self.bloque or i in self.trouvees or i == self.premiere:
            return
        self._retourner(i)

    def _retourner(self, i):
        self.boutons[i].regler("visible")
        self._retenir(i)
        if self.premiere is None:
            self.premiere = i
            if self.tour == "O":
                self._apres(850, self._dropi_seconde)
            return
        self.bloque = True
        premiere, self.premiere = self.premiere, None
        self._apres(900, lambda: self._verifier(premiere, i))

    def _verifier(self, a, b):
        if self.cartes[a] == self.cartes[b]:
            for i in (a, b):
                self.trouvees[i] = self.tour
                self.connu.pop(i, None)
                self.boutons[i].regler("trouvee", self.tour)
            self.points[0 if self.tour == "X" else 1] += 1
            self._maj_score()
            if len(self.trouvees) == len(self.cartes):
                self._terminer()
                return
            if self.tour == "X":
                self.parole.setText("Une paire ! " + replique("perd") + " Rejoue.")
                self.humeur.emit("aie", 0.8)
                self.bloque = False
            else:
                self.parole.setText("Une paire pour moi ! Je rejoue.")
                self.humeur.emit("content", 0.9)
                self._apres(600, self._dropi_premiere)
            return
        for i in (a, b):
            self.boutons[i].regler("cachee")
        if self.tour == "X":
            self.tour = "O"
            self.parole.setText("Raté ! À moi…")
            self._apres(600, self._dropi_premiere)
        else:
            self.tour, self.bloque = "X", False
            self.parole.setText("Raté… À toi !")

    def _dropi_premiere(self):
        self.tour, self.bloque = "O", True
        self._retourner(memoire_choix_dropi(self.cartes, self.trouvees, self.connu))

    def _dropi_seconde(self):
        self._retourner(memoire_choix_dropi(self.cartes, self.trouvees, self.connu, self.premiere))

    def _terminer(self):
        self.bloque = True
        if self.points[0] > self.points[1]:
            self.parole.setText("Tu as gagné ! " + replique("perd"))
            self.humeur.emit("erreur", 1.8)
        elif self.points[0] < self.points[1]:
            self.parole.setText("J'ai gagné ! " + replique("gagne"))
            self.humeur.emit("eureka", 1.8)
        else:
            self.parole.setText("Égalité parfaite ! " + replique("egal"))
            self.humeur.emit("surpris", 1.4)
        self.rejouer.show()


class DevineLeNombre(QWidget, Chrono):
    """Dropi choisit un nombre que tu cherches, puis tu en choisis un qu'il cherche. Le moins d'essais gagne."""
    humeur = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self._generation = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.score = _score()
        lay.addWidget(self.score)
        self.consigne = ui.Etiquette("", 15, ui.TEXTE, gras=True)
        self.consigne.setAlignment(Qt.AlignCenter)
        self.consigne.setWordWrap(True)
        self.consigne.setMinimumHeight(48)
        lay.addWidget(self.consigne)
        self.historique = ui.Etiquette("", 12, ui.TEXTE_2)
        self.historique.setAlignment(Qt.AlignCenter)
        self.historique.setWordWrap(True)
        self.historique.setMinimumHeight(92)
        lay.addWidget(self.historique)
        self.parole = _parole()
        lay.addWidget(self.parole)

        saisie = QHBoxLayout()
        saisie.setSpacing(6)
        self.champ = ui.Champ("Ton nombre (1 à 100)")
        self.champ.setValidator(QIntValidator(1, 100, self))
        self.champ.returnPressed.connect(self._valider)
        self.valider = ui.Bouton("envoyer", "Valider", "accent")
        self.valider.clicked.connect(self._valider)
        saisie.addWidget(self.champ, 1)
        saisie.addWidget(self.valider)
        self.zone_saisie = QWidget()
        self.zone_saisie.setLayout(saisie)
        lay.addWidget(self.zone_saisie)

        reponses = QHBoxLayout()
        reponses.setSpacing(6)
        self.b_grand = ui.Bouton("", "⬆ Plus grand", "puce")
        self.b_trouve = ui.Bouton("ok", "Trouvé !", "accent")
        self.b_petit = ui.Bouton("", "⬇ Plus petit", "puce")
        self.b_grand.clicked.connect(lambda: self._reponse("grand"))
        self.b_trouve.clicked.connect(lambda: self._reponse("trouve"))
        self.b_petit.clicked.connect(lambda: self._reponse("petit"))
        reponses.addStretch(1)
        for b in (self.b_petit, self.b_trouve, self.b_grand):
            reponses.addWidget(b)
        reponses.addStretch(1)
        self.zone_reponses = QWidget()
        self.zone_reponses.setLayout(reponses)
        lay.addWidget(self.zone_reponses)

        self.pret = ui.Bouton("ok", "C'est bon, j'ai choisi mon nombre", "accent")
        self.pret.clicked.connect(self._dropi_commence)
        self.rejouer = ui.Bouton("regenerer", "Rejouer", "puce")
        self.rejouer.clicked.connect(self.nouvelle)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(self.pret)
        bas.addWidget(self.rejouer)
        bas.addStretch(1)
        lay.addLayout(bas)

    def focaliser(self):
        if self.zone_saisie.isVisible():
            self.champ.setFocus()

    def commencer(self):
        self.victoires = {"X": 0, "O": 0, "nul": 0}
        self.nouvelle()

    def nouvelle(self):
        self._annuler_attentes()
        self.secret = random.randint(1, 100)
        self.essais_toi, self.essais_dropi, self.bas, self.haut = 0, 0, 1, 100
        self.coup = None
        self.lignes = []
        self._ecran("toi")
        self.consigne.setText("J'ai pensé à un nombre entre 1 et 100.\nTrouve-le en un minimum d'essais !")
        self.historique.setText("")
        self.parole.setText(replique("debut"))
        self.champ.clear()
        self._maj_score()
        self.champ.setFocus()

    def _ecran(self, quoi):
        self.zone_saisie.setVisible(quoi == "toi")
        self.zone_reponses.setVisible(quoi == "dropi")
        self.pret.setVisible(quoi == "attente")
        self.rejouer.setVisible(quoi == "fin")

    def _maj_score(self):
        v = self.victoires
        self.score.setText(f"Toi {v['X']}   –   {v['O']} Dropi      (nuls : {v['nul']})")

    def _valider(self):
        if not self.zone_saisie.isVisible():
            return
        texte = self.champ.text().strip()
        if not texte.isdigit() or not 1 <= int(texte) <= 100:
            self.parole.setText("Un nombre entre 1 et 100 !")
            return
        n = int(texte)
        self.champ.clear()
        self.essais_toi += 1
        if n == self.secret:
            self.lignes.append(f"{n} ✔")
            self.historique.setText("   ".join(self.lignes[-8:]))
            self.parole.setText(f"Trouvé en {self.essais_toi} essai{'s' if self.essais_toi > 1 else ''} ! À mon tour de chercher ton nombre.")
            self.humeur.emit("aie", 0.8)
            self._ecran("attente")
            self.consigne.setText("À mon tour !\nPense à un nombre entre 1 et 100, et ne me le dis pas.")
            return
        self.lignes.append(f"{n} {'⬆' if n < self.secret else '⬇'}")
        self.historique.setText("   ".join(self.lignes[-8:]))
        self.parole.setText("Plus grand ! ⬆" if n < self.secret else "Plus petit ! ⬇")

    def _dropi_commence(self):
        self.bas, self.haut, self.essais_dropi = 1, 100, 0
        self._ecran("dropi")
        self._proposer()

    def _proposer(self):
        self.coup = nombre_propose(self.bas, self.haut)
        self.essais_dropi += 1
        self.consigne.setText(f"C'est {self.coup} ?")
        self.historique.setText(f"Essai n° {self.essais_dropi}   ·   ton nombre est entre {self.bas} et {self.haut}")

    def _reponse(self, quoi):
        if quoi == "trouve":
            self._terminer()
            return
        if quoi == "grand":
            self.bas = self.coup + 1
        else:
            self.haut = self.coup - 1
        if self.bas > self.haut:
            self._ecran("fin")
            self.consigne.setText("Tu m'as menti ! 😠")
            self.historique.setText("")
            self.parole.setText("Ça ne colle plus avec tes réponses. Partie annulée.")
            self.humeur.emit("alerte", 1.4)
            return
        self.parole.setText("Hmm…")
        self._proposer()

    def _terminer(self):
        self._ecran("fin")
        a, b = self.essais_toi, self.essais_dropi
        self.consigne.setText(f"Toi : {a} essais   ·   Dropi : {b} essais")
        self.historique.setText("")
        if a < b:
            self.victoires["X"] += 1
            self.parole.setText("Tu as gagné ! " + replique("perd"))
            self.humeur.emit("erreur", 1.8)
        elif a > b:
            self.victoires["O"] += 1
            self.parole.setText("J'ai gagné ! " + replique("gagne"))
            self.humeur.emit("eureka", 1.8)
        else:
            self.victoires["nul"] += 1
            self.parole.setText(replique("egal"))
            self.humeur.emit("surpris", 1.4)
        self._maj_score()


# ============================================================== le panneau

JEUX = [("morpion", "Morpion", "tableau"), ("p4", "Puissance 4", "disque"), ("pfc", "Chifoumi", "applis"),
        ("memoire", "Mémoire", "oeil"), ("nombre", "Devine le nombre", "code"), ("reflexe", "Réflexe", "eclair")]


class PageJeux(QWidget):
    """Le panneau « Jouer avec Dropi » : un menu et les trois jeux."""
    fermer = Signal()
    humeur = Signal(str, float)               # Dropi réagit (humeur, durée)

    def __init__(self, mascotte, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 14)
        lay.setSpacing(10)
        tete = QHBoxLayout()
        tete.setSpacing(4)
        tete.addWidget(VueMascotte(mascotte, 10.5))
        self.titre = ui.EtiquetteCoupee("Jouer avec Dropi", taille=14, gras=True)
        tete.addWidget(self.titre, 1)
        self.retour = ui.Bouton("annuler", info="Retour aux jeux")
        self.retour.clicked.connect(lambda: self.ouvrir(None))
        fermer = ui.Bouton("fermer", info="Fermer (Échap)")
        fermer.clicked.connect(self.fermer.emit)
        tete.addWidget(self.retour)
        tete.addWidget(fermer)
        lay.addLayout(tete)

        self.pile = QStackedLayout()
        lay.addLayout(self.pile)
        menu = QWidget()
        m = QVBoxLayout(menu)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(10)
        accroche = ui.Etiquette("Un contre un, à toi de me battre !", 15, ui.TEXTE, gras=True)
        accroche.setAlignment(Qt.AlignCenter)
        m.addStretch(1)
        m.addWidget(accroche)
        sous = ui.Etiquette("Choisis un jeu. Moi, je ne me laisse pas faire.", 12, ui.TEXTE_3)
        sous.setAlignment(Qt.AlignCenter)
        m.addWidget(sous)
        m.addSpacing(8)
        grille = QGridLayout()
        grille.setSpacing(6)
        for colonne in range(3):
            grille.setColumnStretch(colonne, 1)
        for i, (cle, nom, icone) in enumerate(JEUX):
            tuile = ui.Tuile(icone, nom)
            tuile.clicked.connect(lambda _=False, c=cle: self.ouvrir(c))
            grille.addWidget(tuile, i // 3, i % 3)
        m.addLayout(grille)
        m.addStretch(1)
        self.pile.addWidget(menu)
        self.jeux = {"morpion": Morpion(), "p4": Puissance4(), "pfc": PierreFeuilleCiseaux(), "memoire": Memoire(),
                     "nombre": DevineLeNombre(), "reflexe": Reflexe()}
        for jeu in self.jeux.values():
            jeu.humeur.connect(self.humeur.emit)
            self.pile.addWidget(jeu)
        self.setFocusPolicy(Qt.StrongFocus)
        self.ouvrir(None)

    def ouvrir(self, jeu):
        """jeu : "morpion", "pfc", "reflexe" ou None pour le menu."""
        for autre in self.jeux.values():
            for t in autre.findChildren(QTimer):
                t.stop()
            if hasattr(autre, "_annuler_attentes"):
                autre._annuler_attentes()
        if jeu in self.jeux:
            self.pile.setCurrentWidget(self.jeux[jeu])
            self.titre.setText({"pfc": "Pierre-feuille-ciseaux"}.get(jeu) or dict((c, n) for c, n, _ in JEUX)[jeu])
            self.retour.show()
            self.jeux[jeu].commencer()
        else:
            self.pile.setCurrentIndex(0)
            self.titre.setText("Jouer avec Dropi")
            self.retour.hide()

    def focusInEvent(self, e):
        jeu = self.pile.currentWidget()
        if hasattr(jeu, "focaliser"):
            jeu.focaliser()
        super().focusInEvent(e)

    def sizeHint(self):
        return QSize(420, 500)
