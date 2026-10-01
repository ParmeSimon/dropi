"""Lancer Dropi au démarrage de Windows (clé « Run » de ton compte, sans droits administrateur)."""
import sys
import winreg
from pathlib import Path

import donnees

CLE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "Dropi"
ANCIEN_NOM = "AssistantIsland"          # le nom avant « Dropi » : on le retire pour ne pas lancer deux fois


def commande():
    """Ce que Windows lance : Dropi.exe, ou le script avec pythonw (sans fenêtre noire)."""
    if donnees.FIGE:
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{donnees.DOSSIER_PROGRAMME / "island.py"}"'


def est_active():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE) as cle:
            winreg.QueryValueEx(cle, NOM)
            return True
    except OSError:
        return False


def _retirer(nom):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, nom)
    except OSError:
        pass


def activer(cmd=None):
    _retirer(ANCIEN_NOM)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as cle:
        winreg.SetValueEx(cle, NOM, 0, winreg.REG_SZ, cmd or commande())


def desactiver():
    _retirer(ANCIEN_NOM)
    _retirer(NOM)
