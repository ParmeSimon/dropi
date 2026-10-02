"""Les icônes des applications, telles que Windows les montre dans le menu Démarrer.

Windows sait donner l'image de n'importe quelle appli (y compris celles du Microsoft Store) à partir de son
identifiant du menu Démarrer : on la lui demande une fois, puis on la garde en PNG dans
%APPDATA%\\AssistantIle\\icones (le tableau de bord s'ouvre alors sans rien recalculer).
"""
import ctypes
import hashlib
import sys
from ctypes import wintypes

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFileIconProvider

import donnees

DOSSIER = donnees.DONNEES / "icones"
_memoire = {}


class _Guid(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]


def _guid(texte):
    g = _Guid()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(texte), ctypes.byref(g))
    return g


class _Bitmap(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


def _image_shell(nom_shell, taille):
    """L'image que l'Explorateur afficherait pour cet élément (chemin, ou « shell:AppsFolder\\identifiant »)."""
    shell32, ole32, gdi32 = ctypes.windll.shell32, ctypes.windll.ole32, ctypes.windll.gdi32
    ole32.CoInitialize(None)
    usine = ctypes.c_void_p()
    iid = _guid("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")                  # IShellItemImageFactory
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_Guid),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    if shell32.SHCreateItemFromParsingName(nom_shell, None, ctypes.byref(iid), ctypes.byref(usine)) != 0 or not usine:
        return QImage()
    try:
        table = ctypes.cast(ctypes.cast(usine, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        obtenir = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.SIZE, ctypes.c_int,
                                     ctypes.POINTER(wintypes.HBITMAP))(table[3])        # GetImage
        liberer = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])         # Release
        bitmap = wintypes.HBITMAP()
        resultat = obtenir(usine, wintypes.SIZE(taille, taille), 0x4, ctypes.byref(bitmap))   # 0x4 : l'icône, pas un aperçu
        liberer(usine)
        if resultat != 0 or not bitmap:
            return QImage()
        infos = _Bitmap()
        gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetObjectW(bitmap, ctypes.sizeof(infos), ctypes.byref(infos))
        try:
            if not infos.bmBits or infos.bmBitsPixel != 32:
                return QImage()
            brut = ctypes.string_at(infos.bmBits, infos.bmWidthBytes * infos.bmHeight)
            image = QImage(brut, infos.bmWidth, infos.bmHeight, infos.bmWidthBytes, QImage.Format_ARGB32_Premultiplied)
            return image.mirrored(False, True).copy()          # les bitmaps Windows sont stockés à l'envers
        finally:
            gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
            gdi32.DeleteObject(bitmap)
    except Exception:
        return QImage()


def _en_cache(cle, taille, fabriquer):
    identifiant = hashlib.sha1(f"{cle}|{taille}".encode()).hexdigest()[:20]
    if identifiant in _memoire:
        return _memoire[identifiant]
    fichier = DOSSIER / f"{identifiant}.png"
    pix = QPixmap(str(fichier)) if fichier.exists() else QPixmap()
    if pix.isNull():
        image = fabriquer()
        if not image.isNull():
            pix = QPixmap.fromImage(image)
            try:
                DOSSIER.mkdir(parents=True, exist_ok=True)
                pix.save(str(fichier), "PNG")
            except OSError:
                pass
    _memoire[identifiant] = pix
    return pix


def deja_prete(identifiant, taille=64):
    """L'icône de cette appli est-elle déjà en cache (donc immédiate à afficher) ?"""
    cle = hashlib.sha1(f"appli:{identifiant}|{taille}".encode()).hexdigest()[:20]
    return cle in _memoire or (DOSSIER / f"{cle}.png").exists()


def icone_appli(identifiant, taille=64):
    """L'icône d'une appli du menu Démarrer (son AppID, ex. « Microsoft.WindowsCalculator_8wekyb3d8bbwe!App »)."""
    if sys.platform != "win32" or not identifiant:
        return QPixmap()
    return _en_cache("appli:" + identifiant, taille, lambda: _image_shell("shell:AppsFolder\\" + identifiant, taille))


def icone_fichier(chemin, taille=64):
    """L'icône d'un fichier ou d'un programme (.exe) sur le disque."""
    if sys.platform != "win32" or not chemin:
        return QPixmap()

    def fabriquer():
        image = _image_shell(str(chemin), taille)
        if image.isNull():
            image = QFileIconProvider().icon(QFileInfo(str(chemin))).pixmap(taille, taille).toImage()
        return image

    return _en_cache("fichier:" + str(chemin).lower(), taille, fabriquer)
