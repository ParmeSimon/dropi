"""Copier un secret (mot de passe) sans le laisser traîner dans le presse-papiers.

- Windows ne le garde pas dans l'historique (Win + V) ni ne le synchronise entre tes appareils.
- Il n'est mis dans le presse-papiers qu'au moment où une page le demande (au « Coller », rendu différé), et il est
  effacé 1,5 s après ce premier collage. Si personne ne le colle, il est effacé au bout de `delai` secondes.
"""
import struct
import time

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication

FORMATS_EXCLUS = {
    "ExcludeClipboardContentFromMonitorProcessing": b"\x01",    # ni historique ni cloud (la méthode générale)
    "CanIncludeInClipboardHistory": struct.pack("<I", 0),
    "CanUploadToCloudClipboard": struct.pack("<I", 0),
}
TEXTE = "text/plain"
SOURDINE = 0.5                   # secondes après la copie où une lecture n'est pas un collage (Windows qui vérifie)
APRES_COLLAGE = 1500             # ms avant d'effacer, une fois collé

_en_cours = None                 # garde la référence (sinon Qt libère les données)


class Secret(QMimeData):
    """Le texte n'est fourni qu'à la demande ; le premier collage déclenche l'effacement."""

    def __init__(self, texte, delai=20):
        super().__init__()
        self._texte = texte
        self._depuis = time.monotonic()
        self._efface = False
        for nom, valeur in FORMATS_EXCLUS.items():
            self.setData(f'application/x-qt-windows-mime;value="{nom}"', valeur)
        QTimer.singleShot(int(delai * 1000), self.effacer)

    def formats(self):
        return [TEXTE] + super().formats()

    def hasFormat(self, mime):
        return mime == TEXTE or super().hasFormat(mime)

    def retrieveData(self, mime, type_):
        if mime == TEXTE:
            if time.monotonic() - self._depuis > SOURDINE and not self._efface:
                QTimer.singleShot(APRES_COLLAGE, self.effacer)           # collé : on efface dans un instant
            return self._texte
        return super().retrieveData(mime, type_)

    def effacer(self):
        """Efface le presse-papiers, seulement s'il contient encore NOTRE secret (pas autre chose copié depuis)."""
        global _en_cours
        if self._efface:
            return
        self._efface = True
        presse = QApplication.clipboard()
        if presse.mimeData() is self:
            presse.clear()
        self._texte = ""
        if _en_cours is self:
            _en_cours = None


def copier_secret(texte, delai=20):
    global _en_cours
    if _en_cours is not None:
        _en_cours.effacer()
    _en_cours = Secret(texte, delai)
    QApplication.clipboard().setMimeData(_en_cours)
