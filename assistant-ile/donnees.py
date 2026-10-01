"""Où l'assistant garde ses propres fichiers (journal des rangements, mémoire, erreurs).

Dans %APPDATA%\\AssistantIle : c'est le même dossier que tu lances le script ou Dropi.exe,
et il survit aux mises à jour de l'appli.
"""
import os
import sys
import shutil
from pathlib import Path

DONNEES = Path(os.environ.get("APPDATA") or Path.home()) / "AssistantIle"
DONNEES.mkdir(parents=True, exist_ok=True)

FIGE = getattr(sys, "frozen", False)          # vrai quand on tourne depuis Dropi.exe
DOSSIER_PROGRAMME = Path(sys.executable).parent if FIGE else Path(__file__).resolve().parent


def fichier(nom):
    """Chemin d'un fichier de données (reprend l'ancien s'il était resté dans le dossier du programme)."""
    nouveau = DONNEES / nom
    ancien = DOSSIER_PROGRAMME / nom
    if not nouveau.exists() and ancien.exists():
        shutil.move(str(ancien), str(nouveau))
    return nouveau
