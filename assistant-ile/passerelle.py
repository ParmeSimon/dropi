"""La passerelle : reçoit ce que l'extension du navigateur envoie (dossier extension/).

Le navigateur ne laisse parler à un programme du PC que les extensions qu'on lui a déclarées :
inscrire() déclare la nôtre (et elle seule, par son identifiant) dans le registre de ton compte.
Le navigateur lance alors hote.py, qui nous transmet le message par un tube local de Windows.
"""
import os
import sys
import json
import winreg
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer

import donnees

NOM_HOTE = "fr.dropi.assistant"
EXTENSION = "cnifejnemhihfgnifncoibomfhjcocnh"      # fixé par la clé « key » de extension/manifest.json
TUBE = "AssistantIsland-extension-" + os.environ.get("USERNAME", "")
NAVIGATEURS = (r"Software\Google\Chrome", r"Software\BraveSoftware\Brave-Browser", r"Software\Microsoft\Edge")


def inscrire():
    """Déclare hote.py aux navigateurs (registre de ton compte, sans droits administrateur)."""
    if donnees.FIGE:
        return False                 # Dropi.exe n'embarque pas de Python pour lancer hote.py
    python = Path(sys.executable).with_name("python.exe")
    lanceur = donnees.DONNEES / "extension_hote.bat"
    lanceur.write_text(f'@echo off\r\n"{python}" -u "{donnees.DOSSIER_PROGRAMME / "hote.py"}"\r\n', encoding="mbcs")
    fiche = donnees.DONNEES / "extension_hote.json"
    fiche.write_text(json.dumps({
        "name": NOM_HOTE, "description": "Dropi : mots de passe", "path": str(lanceur),
        "type": "stdio", "allowed_origins": [f"chrome-extension://{EXTENSION}/"]}, indent=1), encoding="utf-8")
    for navigateur in NAVIGATEURS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{navigateur}\NativeMessagingHosts\{NOM_HOTE}") as cle:
            winreg.SetValueEx(cle, None, 0, winreg.REG_SZ, str(fiche))
    return True


class Passerelle(QObject):
    """Écoute le tube : une ligne de JSON reçue, sur_message(dict) appelé, sa réponse (dict) renvoyée."""

    def __init__(self, sur_message, parent=None):
        super().__init__(parent)
        self.sur_message = sur_message
        QLocalServer.removeServer(TUBE)
        self.serveur = QLocalServer(self)
        self.serveur.newConnection.connect(self._nouveau)
        self.serveur.listen(TUBE)

    def _nouveau(self):
        while self.serveur.hasPendingConnections():
            tube = self.serveur.nextPendingConnection()
            tube.readyRead.connect(lambda t=tube: self._lire(t))
            tube.disconnected.connect(tube.deleteLater)

    def _lire(self, tube):
        while tube.canReadLine():
            try:
                message = json.loads(bytes(tube.readLine()).decode("utf-8"))
                reponse = self.sur_message(message) if isinstance(message, dict) else None
            except ValueError:
                reponse = None
            tube.write(json.dumps(reponse or {"ok": False}).encode("utf-8") + b"\n")
            tube.flush()
