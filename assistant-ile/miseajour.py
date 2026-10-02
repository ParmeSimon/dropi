"""Mise à jour de Dropi : il regarde la dernière release GitHub, te prévient, et installe en un clic.

Pour publier une mise à jour : voir « Publier une mise à jour » dans le LISEZMOI. Le fichier de la release doit
s'appeler exactement Dropi-Setup.exe et son numéro de version (le tag, ex. v1.2.0) doit être plus grand que celui
de l'appli installée (version.py).

Sécurité : on ne télécharge que depuis github.com, la taille et l'empreinte SHA-256 (donnée par GitHub) du fichier
sont vérifiées avant de le lancer, et rien n'est lancé sans que tu aies cliqué.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import moteur
from version import VERSION

DEPOT = "ParmeSimon/dropi"
NOM_SETUP = "Dropi-Setup.exe"
API = f"https://api.github.com/repos/{DEPOT}/releases/latest"
HOTES_OK = ("github.com", "githubusercontent.com")
PREMIERE_ATTENTE = 30            # secondes après le lancement : l'appli démarre d'abord
INTERVALLE = 6 * 3600            # puis un coup d'œil toutes les 6 heures


def numeros(version):
    return tuple(int(n) for n in re.findall(r"\d+", str(version))[:4])


def plus_recent(a, b):
    return numeros(a) > numeros(b)


def derniere():
    """La dernière release publiée avec un Dropi-Setup.exe, ou None.
    {"version", "titre", "url", "taille", "sha256"}"""
    req = urllib.request.Request(API, headers={"User-Agent": "Dropi", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:                  # pas encore de release
            return None
        raise
    if d.get("draft") or d.get("prerelease"):
        return None
    fichier = next((a for a in d.get("assets", []) if a.get("name") == NOM_SETUP), None)
    if not fichier:
        return None
    empreinte = str(fichier.get("digest") or "")
    return {"version": str(d.get("tag_name", "")).lstrip("vV"), "titre": d.get("name") or d.get("tag_name", ""),
            "url": fichier.get("browser_download_url", ""), "taille": int(fichier.get("size") or 0),
            "sha256": empreinte.split(":", 1)[1].lower() if empreinte.startswith("sha256:") else ""}


def disponible():
    """La release plus récente que la version installée, ou None."""
    info = derniere()
    return info if info and plus_recent(info["version"], VERSION) else None


def _hote_sur(url):
    hote = (urllib.parse.urlparse(url).hostname or "").lower()
    return urllib.parse.urlparse(url).scheme == "https" and any(hote == h or hote.endswith("." + h) for h in HOTES_OK)


def telecharger(info, sur_etat=None):
    """Télécharge le setup et le vérifie. Renvoie son chemin. Lève ValueError si quelque chose cloche."""
    if not _hote_sur(info["url"]):
        raise ValueError("Lien de mise à jour suspect : annulé.")
    dest = Path(tempfile.gettempdir()) / f"Dropi-Setup-{info['version']}.exe"
    dest.unlink(missing_ok=True)
    moteur.telecharger(info["url"], dest, sur_etat, "de la mise à jour", info["taille"])
    if info["taille"] and dest.stat().st_size != info["taille"]:
        dest.unlink(missing_ok=True)
        raise ValueError("Le fichier téléchargé est incomplet.")
    if info["sha256"]:
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        if h.hexdigest() != info["sha256"]:
            dest.unlink(missing_ok=True)
            raise ValueError("Le fichier téléchargé est abîmé (empreinte différente) : annulé.")
    return dest


def lancer_installation(setup):
    """Lance l'installateur en silence (une petite fenêtre de progression), qui ferme Dropi, le remplace et le relance."""
    subprocess.Popen([str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANCER=1"],
                     creationflags=0x00000008 | 0x00000200, close_fds=True)       # DETACHED_PROCESS | NEW_PROCESS_GROUP


class Veilleur:
    """Dans un fil de fond : cherche une mise à jour au lancement puis toutes les 6 heures."""

    def __init__(self, sur_dispo):
        self.sur_dispo = sur_dispo               # appelé (depuis le fil de fond) avec la release trouvée
        self.prevenu = ""

    def demarrer(self):
        threading.Thread(target=self._fil, daemon=True).start()

    def verifier(self):
        info = disponible()
        if info and info["version"] != self.prevenu:
            self.prevenu = info["version"]
            self.sur_dispo(info)
        return info

    def _fil(self):
        time.sleep(PREMIERE_ATTENTE)
        while True:
            try:
                self.verifier()
            except Exception:
                pass                              # pas de réseau, GitHub injoignable : on réessaiera
            time.sleep(INTERVALLE)
