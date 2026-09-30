"""Lancer l'assistant au démarrage de Windows (clé « Run » de ton compte, sans droits administrateur)."""
import sys
import winreg
from pathlib import Path

import donnees

CLE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "AssistantIsland"


def commande():
    """Ce que Windows lance : Assistant.exe, ou le script avec pythonw (sans fenêtre noire)."""
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


def activer(cmd=None):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as cle:
        winreg.SetValueEx(cle, NOM, 0, winreg.REG_SZ, cmd or commande())


def desactiver():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, NOM)
    except OSError:
        pass
