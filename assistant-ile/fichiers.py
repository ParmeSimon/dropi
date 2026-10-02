"""Le gestionnaire de fichiers du tableau de bord : tes fichiers rangés par thème, sans avoir à ouvrir l'Explorateur.

À gauche les thèmes (Études, Travail, Administratif…), à droite le contenu. On y cherche, on ouvre, on déplace vers un
autre thème, on renomme, on jette à la corbeille. Un fichier glissé depuis l'Explorateur est rangé tout seul.
Chaque déplacement passe par classement.py : le journal le note, « annule » le défait.
"""
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSize, QTimer, Signal, QObject, QFileInfo, QUrl, QMimeData, QStorageInfo
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QAbstractButton, QTreeWidget, QTreeWidgetItem,
                               QFileIconProvider, QMenu, QInputDialog, QHeaderView, QAbstractItemView)

import classement
import composants as ui
import inventaire
import themes
import tools

MAX_LIGNES = 1500
MAX_RESULTATS = 400
DELAI_RECHERCHE = 8                    # secondes au plus pour une recherche dans un dossier
DOSSIERS_LOURDS = {"windows", "node_modules", "appdata", "programdata", "__pycache__", "system volume information"}
GLYPHES_LIEUX = {"Téléchargements": "telechargement", "Bureau": "bureau", "Documents": "document", "Images": "oeil",
                 "Vidéos": "video", "Musique": "note"}
STYLE_LISTE = """
QTreeWidget { background: transparent; border: none; color: rgba(255,255,255,235); font-size: 13px; outline: none; }
QTreeWidget::item { height: 34px; border-radius: 8px; padding-left: 4px; }
QTreeWidget::item:hover { background: rgba(255,255,255,14); }
QTreeWidget::item:selected { background: rgba(96,205,255,46); color: white; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section { background: transparent; color: rgba(255,255,255,135); border: none; padding: 6px 8px;
                       font-size: 11px; font-weight: 600; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,55); border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,110); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


def disques():
    """Les disques du PC (C:, D:, clés USB…) : [(nom affiché, chemin, « 120 Go libres »)]."""
    trouves = []
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid() or not volume.isReady():
            continue
        racine = volume.rootPath()
        lettre = racine.rstrip("/\\")
        nom = volume.name() or ("Disque local" if lettre.upper().startswith("C") else "Disque")
        libres = volume.bytesAvailable()
        trouves.append((f"{nom} ({lettre})", Path(racine), f"{ui.taille_lisible(libres)} libres" if libres >= 0 else ""))
    return trouves


def _cache(entree):
    """Fichier caché ou réservé à Windows (pagefile.sys, $Recycle.Bin, System Volume Information…) : on ne le montre pas."""
    if entree.name.startswith((".", "~$", "$")) or entree.name.lower() in ("desktop.ini", "thumbs.db"):
        return True
    try:
        return bool(entree.stat(follow_symlinks=False).st_file_attributes & 0x6)      # caché (2) ou système (4)
    except (OSError, AttributeError):
        return False


def lister(dossier):
    """Le contenu d'un dossier : (dossiers, fichiers), chacun trié par nom. Vide si on ne peut pas le lire."""
    dossiers, fichiers = [], []
    try:
        with os.scandir(dossier) as contenu:
            for e in contenu:
                if _cache(e):
                    continue
                try:
                    (dossiers if e.is_dir() else fichiers).append(e.path)
                except OSError:
                    pass
    except OSError:
        pass
    cle = lambda c: os.path.basename(c).casefold()
    return sorted(dossiers, key=cle), sorted(fichiers, key=cle)


def chercher(dossier, texte, limite=MAX_RESULTATS):
    """Les fichiers dont le nom contient tous les mots, dans ce dossier et ses sous-dossiers."""
    mots = themes.simple(texte).split()
    trouves = []
    if not mots:
        return trouves
    fin = time.monotonic() + DELAI_RECHERCHE            # un disque entier, c'est long : on s'arrête au bout de quelques secondes
    for racine, sous_dossiers, noms in os.walk(dossier):
        sous_dossiers[:] = [d for d in sous_dossiers if not d.startswith((".", "$")) and d.lower() not in DOSSIERS_LOURDS]
        if time.monotonic() > fin:
            break
        for nom in noms:
            simple = themes.simple(nom)
            if all(m in simple for m in mots):
                trouves.append(os.path.join(racine, nom))
                if len(trouves) >= limite:
                    return trouves
    return trouves


def date_lisible(secondes):
    maintenant = time.time()
    ecart = maintenant - secondes
    if ecart < 3600:
        return "à l'instant" if ecart < 120 else f"il y a {int(ecart // 60)} min"
    m, auj = time.localtime(secondes), time.localtime(maintenant)
    if (m.tm_year, m.tm_yday) == (auj.tm_year, auj.tm_yday):
        return f"aujourd'hui {m.tm_hour:02d}:{m.tm_min:02d}"
    return f"{m.tm_mday:02d}/{m.tm_mon:02d}/{m.tm_year}"


class EntreeLaterale(QAbstractButton):
    """Une ligne de la colonne de gauche : un thème (avec son nombre de fichiers) ou un raccourci."""

    def __init__(self, nom, chemin, glyphe, parent=None):
        super().__init__(parent)
        self.nom, self.chemin, self.nombre, self.actif = nom, str(chemin), None, False
        self.glyphe = ui.ICONES.get(glyphe, "")
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        a = ui.accent()
        if self.actif:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 46))
            p.drawRoundedRect(r, 10, 10)
        elif self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(ui.CARTE_SURVOL)
            p.drawRoundedRect(r, 10, 10)
        p.setPen(a)
        p.setFont(ui.police_icones(14))
        p.drawText(QRectF(10, 0, 24, self.height()), Qt.AlignCenter, self.glyphe)
        p.setPen(ui.TEXTE if self.actif or self.underMouse() else ui.TEXTE_2)
        p.setFont(ui.police(13, self.actif))
        place = self.width() - (150 if getattr(self, "detail", "") else 86)
        p.drawText(QRectF(42, 0, place, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.nom, Qt.ElideRight, int(place)))
        detail = getattr(self, "detail", "") or (str(self.nombre) if self.nombre else "")
        if detail:
            p.setPen(ui.TEXTE_3)
            p.setFont(ui.police(11))
            p.drawText(QRectF(self.width() - 110, 0, 100, self.height()), Qt.AlignVCenter | Qt.AlignRight, detail)


class Onglet(QAbstractButton):
    """« Rangés » / « Sur mon PC » : les deux façons de voir un thème."""

    def __init__(self, texte, parent=None):
        super().__init__(parent)
        self.setText(texte)
        self.actif = False
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 40, 34)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        a = ui.accent()
        if self.actif:
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 200), 1.3))
            p.setBrush(QColor(a.red(), a.green(), a.blue(), 46))
        else:
            p.setPen(QPen(ui.CONTOUR, 1))
            p.setBrush(ui.CARTE_SURVOL if self.underMouse() else ui.CARTE)
        p.drawRoundedRect(r, 17, 17)
        p.setPen(ui.TEXTE if self.actif or self.underMouse() else ui.TEXTE_2)
        p.setFont(ui.police(12, self.actif))
        p.drawText(r, Qt.AlignCenter, self.text())


class Liste(QTreeWidget):
    """La liste des fichiers : on peut en faire glisser vers une autre appli, et en déposer pour les ranger."""
    deposes = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels(["Nom", "Rangé dans", "Modifié", "Taille"])
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(22, 22))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setStyleSheet(STYLE_LISTE)
        self.setFocusPolicy(Qt.StrongFocus)
        entete = self.header()
        entete.setSectionResizeMode(0, QHeaderView.Stretch)
        for colonne, largeur in ((1, 250), (2, 150), (3, 90)):
            entete.setSectionResizeMode(colonne, QHeaderView.Fixed)
            self.setColumnWidth(colonne, largeur)
        entete.setStretchLastSection(False)

    def mimeData(self, elements):
        donnees = QMimeData()
        donnees.setUrls([QUrl.fromLocalFile(e.data(0, Qt.UserRole)) for e in elements if e.data(0, Qt.UserRole)])
        return donnees

    def mimeTypes(self):
        return ["text/uri-list"]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and e.source() is not self:
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        chemins = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if chemins and e.source() is not self:
            e.setDropAction(Qt.CopyAction)        # jamais « déplacer » : l'Explorateur pourrait effacer l'original
            e.accept()
            self.deposes.emit(chemins)


class _Pont(QObject):
    comptes = Signal(dict)
    resultats = Signal(str, list)
    ranges = Signal(str)


class Gestionnaire(QWidget):
    retour = Signal()                         # revenir au tableau de bord
    change = Signal()                         # des fichiers ont été rangés ou déplacés : l'inventaire est à refaire

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dossier = classement.racine()
        self._recherche = ""
        self.vue = "ranges"                   # « ranges » (ce qui est dans Documents/Dropi) ou « pc » (ce qui attend sur le PC)
        self._inventaire = []
        self._icones = QFileIconProvider()
        self._pont = _Pont()
        self._pont.comptes.connect(self._maj_comptes)
        self._pont.resultats.connect(self._resultats_prets)
        self._pont.ranges.connect(self._ranges)
        self._attente = QTimer(self, singleShot=True, interval=220, timeout=self._lancer_recherche)

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(28)

        # ---- colonne de gauche
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        retour = ui.Bouton("annuler", "Tableau de bord", "puce", info="Revenir au tableau de bord (Échap)")
        retour.clicked.connect(self.retour.emit)
        gauche.addWidget(retour, 0, Qt.AlignLeft)
        gauche.addSpacing(14)
        gauche.addWidget(ui.TitreSection(1, "Mes thèmes", "ouvrir"))
        gauche.addSpacing(6)
        self.entrees = []
        self._ajouter_entree(gauche, "Tous mes fichiers", classement.racine(), "disque")
        for dossier, _ in themes.ARBORESCENCE:
            self._ajouter_entree(gauche, themes.NOMS_THEMES[dossier], classement.racine() / dossier, themes.GLYPHES.get(dossier, "ouvrir"), dossier)
        gauche.addSpacing(14)
        gauche.addWidget(ui.TitreSection(2, "Ce PC", "disque"))
        gauche.addSpacing(6)
        for nom, chemin, libres in disques():             # C:, D:, clés USB : tout le PC reste accessible
            entree = self._ajouter_entree(gauche, nom, chemin, "disque")
            entree.detail, entree.disque = libres, True
            entree.setToolTip(f"{chemin}  ·  {libres}")
        gauche.addSpacing(14)
        gauche.addWidget(ui.TitreSection(3, "Mes dossiers Windows", "pc"))
        gauche.addSpacing(6)
        vus = set()
        for nom, chemin in inventaire.lieux():            # tes vrais dossiers (Windows a pu les mettre sur OneDrive)
            if nom not in vus:
                vus.add(nom)
                self._ajouter_entree(gauche, nom, chemin, GLYPHES_LIEUX.get(nom, "ouvrir"))
        gauche.addStretch(1)
        colonne = QWidget()
        colonne.setLayout(gauche)
        colonne.setFixedWidth(262)
        defilement = QScrollArea()
        defilement.setWidget(colonne)
        defilement.setWidgetResizable(True)
        defilement.setFrameShape(QScrollArea.NoFrame)
        defilement.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        defilement.setFixedWidth(276)
        defilement.viewport().setAutoFillBackground(False)
        colonne.setAutoFillBackground(False)
        defilement.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                                 "QScrollBar:vertical { background: transparent; width: 6px; margin: 2px 0; }"
                                 "QScrollBar::handle:vertical { background: rgba(255,255,255,55); border-radius: 3px; min-height: 30px; }"
                                 "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
                                 "QScrollBar::add-page, QScrollBar::sub-page { background: none; }")
        racine.addWidget(defilement)

        # ---- à droite : chemin, recherche, liste
        droite = QVBoxLayout()
        droite.setSpacing(10)
        haut = QHBoxLayout()
        haut.setSpacing(8)
        self.remonter = ui.Bouton("reduire", info="Dossier parent (Retour arrière)")
        self.remonter.clicked.connect(self._parent)
        haut.addWidget(self.remonter)
        self.ariane = ui.EtiquetteCoupee("", taille=16, gras=True)
        haut.addWidget(self.ariane, 1)
        self.reclasser = ui.Bouton("ranger", "Tout reclasser", "puce", info="Dropi retente de ranger ces fichiers (règles puis IA)")
        self.reclasser.clicked.connect(self._tout_reclasser)
        haut.addWidget(self.reclasser)
        self.champ = ui.Champ("Chercher dans ce dossier…")
        self.champ.setFixedWidth(300)
        self.champ.textChanged.connect(self._texte_change)
        haut.addWidget(self.champ)
        droite.addLayout(haut)
        onglets = QHBoxLayout()
        onglets.setSpacing(8)
        self.onglet_ranges = Onglet("Rangés")
        self.onglet_ranges.clicked.connect(lambda: self._changer_vue("ranges"))
        self.onglet_pc = Onglet("Sur mon PC")
        self.onglet_pc.clicked.connect(lambda: self._changer_vue("pc"))
        onglets.addWidget(self.onglet_ranges)
        onglets.addWidget(self.onglet_pc)
        onglets.addStretch(1)
        self.zone_onglets = QWidget()
        self.zone_onglets.setLayout(onglets)
        onglets.setContentsMargins(0, 0, 0, 0)
        droite.addWidget(self.zone_onglets)
        self.liste = Liste()
        self.liste.itemActivated.connect(self._ouvrir_element)
        self.liste.deposes.connect(self._deposer)
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu)
        self.liste.installEventFilter(self)
        droite.addWidget(self.liste, 1)
        self.etat = ui.Etiquette("", 12, ui.TEXTE_3)
        droite.addWidget(self.etat)
        racine.addLayout(droite, 1)

    def _ajouter_entree(self, lay, nom, chemin, glyphe, theme=None):
        entree = EntreeLaterale(nom, chemin, glyphe)
        entree.theme = theme
        entree.disque = False
        entree.clicked.connect(lambda _=False, c=chemin: self.aller(c))
        self.entrees.append(entree)
        lay.addWidget(entree)
        return entree

    # ------------------------------------------------------------ navigation
    def aller(self, dossier):
        """Affiche un dossier (un thème, « 01 Études », ou un chemin)."""
        dossier = Path(dossier)
        if not dossier.is_absolute():
            dossier = classement.racine() / dossier
        self.dossier = dossier
        self.champ.blockSignals(True)
        self.champ.clear()
        self.champ.blockSignals(False)
        self._recherche = ""
        # rien de rangé ici mais des fichiers qui attendent sur le PC : on les montre d'emblée
        if self._dans_dropi(dossier):
            ranges = sum(len(f) for _, _, f in os.walk(dossier)) if dossier.is_dir() else 0
            self.vue = "pc" if not ranges and self._du_pc() else "ranges"
        else:
            self.vue = "ranges"
        self.rafraichir()

    def regler_inventaire(self, inventaire):
        """Ce que l'inventaire a trouvé sur le PC (voir inventaire.py)."""
        self._inventaire = inventaire.get("fichiers", [])
        if self.isVisible():
            self.rafraichir()

    def _theme_courant(self):
        """Le thème du dossier affiché (« 01 Études »), ou None à la racine ou ailleurs."""
        if not self._dans_dropi(self.dossier):
            return None
        morceaux = self.dossier.relative_to(classement.racine()).parts
        return morceaux[0] if morceaux else None

    def _du_pc(self):
        """Les fichiers de l'inventaire qui iraient dans le dossier affiché."""
        if not self._dans_dropi(self.dossier):
            return []
        morceaux = self.dossier.relative_to(classement.racine()).parts
        trouves = []
        for f in self._inventaire:
            if morceaux and f["theme"] != morceaux[0]:
                continue
            if len(morceaux) > 1 and f["sous"] != morceaux[1]:
                continue
            if os.path.exists(f["chemin"]):
                trouves.append(f)
        return trouves

    def _changer_vue(self, vue):
        self.vue = vue
        self.champ.blockSignals(True)
        self.champ.clear()
        self.champ.blockSignals(False)
        self._recherche = ""
        self.rafraichir()

    def _parent(self):
        if self.dossier.parent != self.dossier:
            self.aller(self.dossier.parent)

    def rafraichir(self):
        self.dossier.mkdir(parents=True, exist_ok=True) if self._dans_dropi(self.dossier) else None
        etats, dans_un_lieu = [], False
        for entree in self.entrees:
            chemin = Path(entree.chemin)
            if entree.theme or chemin == classement.racine():      # un thème : actif aussi dans ses sous-dossiers
                actif = chemin == self.dossier or (chemin in self.dossier.parents and chemin != classement.racine())
            elif entree.disque:
                actif = None                                       # décidé après : seulement si rien d'autre ne correspond
            else:                                                  # un de tes dossiers : jamais quand on est dans Dropi
                actif = not self._dans_dropi(self.dossier) and (chemin == self.dossier or chemin in self.dossier.parents)
                dans_un_lieu = dans_un_lieu or actif
            etats.append(actif)
        for entree, actif in zip(self.entrees, etats):
            if actif is None:
                chemin = Path(entree.chemin)
                actif = (not dans_un_lieu and not self._dans_dropi(self.dossier)
                         and (chemin == self.dossier or chemin in self.dossier.parents))
            if entree.actif != actif:
                entree.actif = actif
                entree.update()
        self.remonter.setEnabled(self.dossier.parent != self.dossier)
        self.ariane.setText(self._nom_chemin(self.dossier))
        dans_dropi = self._dans_dropi(self.dossier)
        du_pc = self._du_pc() if dans_dropi else []
        self.zone_onglets.setVisible(dans_dropi)
        self.onglet_pc.setText(f"Sur mon PC, pas encore rangés  ·  {len(du_pc)}")
        self.onglet_pc.setVisible(bool(du_pc) or self.vue == "pc")
        self.onglet_ranges.actif, self.onglet_pc.actif = self.vue == "ranges", self.vue == "pc"
        for onglet in (self.onglet_ranges, self.onglet_pc):
            onglet.updateGeometry()
            onglet.update()
        self.liste.headerItem().setText(1, "Où il est" if self.vue == "pc" else "Rangé dans")
        if self.vue == "pc" and dans_dropi:
            en_vrac = [f["chemin"] for f in du_pc if f["vrac"]]
            self.reclasser.setText(f"Ranger ces {len(en_vrac)} fichiers")
            self.reclasser.setVisible(bool(en_vrac))
            self.reclasser.updateGeometry()
            self.liste.setColumnHidden(1, False)
            self._remplir([], [f["chemin"] for f in du_pc], avec_lieu=True)
            a_toi = len(du_pc) - len(en_vrac)
            self.etat.setText(f"{len(du_pc)} fichier{'s' if len(du_pc) > 1 else ''} sur ton PC iraient ici : {len(en_vrac)} en vrac"
                              + (f", {a_toi} dans tes propres dossiers (Dropi ne les en sort pas tout seul)" if a_toi else "") + ".")
        else:
            self.reclasser.setText("Tout reclasser")
            self.reclasser.setVisible(self.dossier.name.startswith("99"))
            self.reclasser.updateGeometry()
            self.liste.setColumnHidden(1, True)
            dossiers, fichiers = lister(self.dossier)
            self._remplir(dossiers, fichiers)
        threading.Thread(target=self._compter, daemon=True).start()

    @staticmethod
    def _dans_dropi(chemin):
        racine = classement.racine()
        return chemin == racine or racine in chemin.parents

    def _nom_chemin(self, dossier):
        if self._dans_dropi(dossier):
            morceaux = dossier.relative_to(classement.racine()).parts
            if not morceaux:
                return "Tous mes fichiers"
            return "  ›  ".join([themes.NOMS_THEMES.get(morceaux[0], morceaux[0]), *morceaux[1:]])
        try:
            dossier.relative_to(Path.home())
            return classement.joli(dossier).replace(" › ", "  ›  ")
        except ValueError:                                         # ailleurs sur un disque : C:  ›  Program Files  ›  …
            morceaux = [m.rstrip("\\/") for m in dossier.parts]
            return "  ›  ".join(m for m in morceaux if m)

    def _remplir(self, dossiers, fichiers, avec_lieu=False):
        self.liste.clear()
        total = len(dossiers) + len(fichiers)
        for chemin in (dossiers + fichiers)[:MAX_LIGNES]:
            self.liste.addTopLevelItem(self._ligne(chemin, avec_lieu))
        if not total:
            self.etat.setText("Aucun résultat." if self._recherche else "Ce dossier est vide. Glisse des fichiers ici : Dropi les range.")
        else:
            reste = f" (les {MAX_LIGNES} premiers affichés)" if total > MAX_LIGNES else ""
            self.etat.setText(f"{len(dossiers)} dossier{'s' if len(dossiers) > 1 else ''}, "
                              f"{len(fichiers)} fichier{'s' if len(fichiers) > 1 else ''}{reste}"
                              if not self._recherche else f"{total} résultat{'s' if total > 1 else ''}{reste}")

    def _ligne(self, chemin, avec_lieu):
        p = Path(chemin)
        ligne = QTreeWidgetItem()
        est_dossier = p.is_dir()
        nom = p.name
        if est_dossier and p.parent == classement.racine():
            nom = themes.NOMS_THEMES.get(nom, nom)
        ligne.setText(0, nom)
        ligne.setIcon(0, self._icones.icon(QFileInfo(chemin)))
        ligne.setData(0, Qt.UserRole, chemin)
        ligne.setToolTip(0, chemin)
        if avec_lieu:
            ligne.setText(1, classement.joli(p.parent) if self.vue == "pc" and not self._recherche else classement.court(p.parent))
        try:
            st = p.stat()
            ligne.setText(2, date_lisible(st.st_mtime))
            if not est_dossier:
                ligne.setText(3, ui.taille_lisible(st.st_size))
        except OSError:
            pass
        for colonne in (1, 2, 3):
            ligne.setForeground(colonne, QColor(255, 255, 255, 135))
        ligne.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
        return ligne

    def _compter(self):
        comptes = {}
        for dossier, _ in themes.ARBORESCENCE:
            comptes[dossier] = sum(len(f) for _, _, f in os.walk(classement.racine() / dossier))
        self._pont.comptes.emit(comptes)

    def _maj_comptes(self, comptes):
        for entree in self.entrees:
            if entree.theme in comptes:
                entree.nombre = comptes[entree.theme]
                entree.update()

    # ------------------------------------------------------------ recherche
    def _texte_change(self, texte):
        self._recherche = texte.strip()
        if not self._recherche:
            self._attente.stop()
            self.rafraichir()
        else:
            self._attente.start()

    def _lancer_recherche(self):
        texte, dossier = self._recherche, self.dossier
        if self.vue == "pc":
            mots = themes.simple(texte).split()
            trouves = [f["chemin"] for f in self._du_pc() if all(m in themes.simple(os.path.basename(f["chemin"])) for m in mots)]
            self._pont.resultats.emit(texte, trouves[:MAX_RESULTATS])
            return
        threading.Thread(target=lambda: self._pont.resultats.emit(texte, chercher(dossier, texte)), daemon=True).start()

    def _resultats_prets(self, texte, chemins):
        if texte != self._recherche:
            return                                # on a tapé autre chose depuis
        self.liste.setColumnHidden(1, False)
        self._remplir([], chemins, avec_lieu=True)

    # ------------------------------------------------------------ actions
    def _choisis(self):
        return [e.data(0, Qt.UserRole) for e in self.liste.selectedItems() if e.data(0, Qt.UserRole)]

    def _ouvrir_element(self, element, _=0):
        chemin = element.data(0, Qt.UserRole)
        if not chemin:
            return
        if os.path.isdir(chemin):
            self.aller(chemin)
        else:
            try:
                os.startfile(chemin)
            except OSError:
                self.etat.setText("Windows ne sait pas ouvrir ce fichier.")

    def _menu(self, position):
        chemins = self._choisis()
        if not chemins:
            return
        seul = len(chemins) == 1
        menu = QMenu(self)
        if seul:
            menu.addAction("Ouvrir", lambda: self._ouvrir_element(self.liste.selectedItems()[0]))
        menu.addAction("Afficher dans l'Explorateur", lambda: tools.afficher_dans_explorateur(chemins[0]))
        vers = menu.addMenu("Déplacer vers")
        for dossier, sous_themes in themes.ARBORESCENCE:
            sous_menu = vers.addMenu(themes.NOMS_THEMES[dossier]) if sous_themes != [""] else None
            if sous_menu is None:
                vers.addAction(themes.NOMS_THEMES[dossier], lambda d=dossier: self._deplacer(chemins, d, ""))
                continue
            for sous in sous_themes:
                sous_menu.addAction(sous, lambda d=dossier, s=sous: self._deplacer(chemins, d, s))
        menu.addAction("Reclasser automatiquement", lambda: self._reclasser(chemins))
        if seul:
            menu.addAction("Renommer…", lambda: self._renommer(chemins[0]))
        menu.addSeparator()
        menu.addAction("Mettre à la corbeille", lambda: self._supprimer(chemins))
        menu.exec(self.liste.viewport().mapToGlobal(position))

    def _deplacer(self, chemins, theme, sous):
        erreurs = 0
        for chemin in chemins:
            p = Path(chemin)
            try:
                cible = themes.dossier(classement.racine(), {"theme": theme, "sous": sous}, classement._date(p))
                if p.parent != cible:
                    classement.deplacer(p, cible, raison="à la main")
            except OSError:
                erreurs += 1
        self.rafraichir()
        self.change.emit()
        lieu = themes.nom_affiche({"theme": theme, "sous": sous})
        self.etat.setText(f"{len(chemins) - erreurs} élément(s) déplacé(s) vers {lieu}" + (f", {erreurs} en échec (fichier ouvert ?)" if erreurs else "") + ".")

    def _reclasser(self, chemins):
        self.etat.setText("Je range…")

        def travail():
            ranges, lieux = 0, set()
            for chemin in chemins:
                if os.path.isfile(chemin):
                    try:
                        dest, _, _ = classement.ranger(chemin)
                        ranges += 1
                        lieux.add(classement.court(dest.parent))
                    except OSError:
                        pass
            self._pont.ranges.emit(f"{ranges} fichier(s) rangé(s) : " + ", ".join(sorted(lieux)[:3]) if ranges else "Rien à ranger.")

        threading.Thread(target=travail, daemon=True).start()

    def _tout_reclasser(self):
        if self.vue == "pc":
            self._reclasser([f["chemin"] for f in self._du_pc() if f["vrac"]])
            return
        _, fichiers = lister(self.dossier)
        self._reclasser(fichiers)

    def _deposer(self, chemins):
        self._reclasser(chemins)

    def _ranges(self, message):
        self.vue = "ranges"
        self.rafraichir()
        self.etat.setText(message)
        self.change.emit()

    def _renommer(self, chemin):
        p = Path(chemin)
        nom, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=p.name)
        nom = nom.strip()
        if not ok or not nom or nom == p.name:
            return
        if any(c in nom for c in '<>:"/\\|?*'):
            self.etat.setText("Ce nom contient un caractère interdit par Windows.")
            return
        cible = p.with_name(nom)
        if cible.exists():
            self.etat.setText("Un fichier porte déjà ce nom ici.")
            return
        try:
            p.rename(cible)
            classement.noter(p, cible, raison="renommé")
        except OSError as ex:
            self.etat.setText(f"Impossible de renommer : {ex}")
            return
        self.rafraichir()

    def _supprimer(self, chemins):
        erreurs = 0
        for chemin in chemins:
            resultat = tools.supprimer_fichier(chemin)
            erreurs += resultat.startswith(("Erreur", "Fichier introuvable"))
        self.rafraichir()
        self.etat.setText(f"{len(chemins) - erreurs} élément(s) à la corbeille." + (f" {erreurs} en échec." if erreurs else ""))

    def eventFilter(self, objet, e):
        if objet is self.liste and e.type() == e.Type.KeyPress:
            if e.key() == Qt.Key_Backspace:
                self._parent()
                return True
            if e.key() == Qt.Key_Delete and self._choisis():
                self._supprimer(self._choisis())
                return True
        return super().eventFilter(objet, e)
