"""Le moteur d'IA embarqué : llama.cpp (llama-server) lancé par l'assistant lui-même.

Plus besoin d'installer Ollama : Dropi.exe emporte le moteur (dossier « moteur », ~90 Mo) et télécharge
le modèle une seule fois au premier lancement (ou réutilise celui d'Ollama s'il est déjà sur le PC).

Partage des ressources
- Carte graphique : on regarde si elle est libre (WMI) et combien de mémoire vidéo reste. Libre : le modèle y va
  (Vulkan : Nvidia, AMD, Intel). Déjà occupée (jeu, vidéo…) : on reste sur le processeur. Mémoire vidéo juste :
  llama.cpp ne met sur la carte que les couches qui rentrent, en laissant une marge (--fit).
- Mémoire : le modèle est « mappé » depuis le disque et déchargé après `garder_en_memoire` d'inactivité ;
  il se recharge tout seul à la demande suivante. Le cache de lecture des consignes est sauvegardé sur disque
  pour ne pas avoir à le recalculer (plusieurs dizaines de secondes sans carte graphique).
- Processeur : un cœur reste libre, priorité basse : le PC et les jeux gardent la main.
"""
import ctypes
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import donnees

BUILD_MOTEUR = "b11320"
URL_MOTEUR = (f"https://github.com/ggml-org/llama.cpp/releases/download/{BUILD_MOTEUR}/"
              f"llama-{BUILD_MOTEUR}-bin-win-vulkan-x64.zip")
NOM_MODELE = "Qwen3-8B-Q4_K_M.gguf"
URL_MODELE = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/" + NOM_MODELE
TAILLE_MODELE_MIN = 4_500_000_000           # en dessous, le téléchargement est incomplet
GPU_OCCUPE = 50                             # % d'utilisation 3D au-delà duquel on laisse la carte tranquille
MARGE_VRAM = 1536                           # Mo de mémoire vidéo laissés aux autres applis

SANS_FENETRE = 0x08000000
PRIORITE_BASSE = 0x00004000


def duree(texte, defaut=900):
    """« 4h », « 15m », « 30s » ou un nombre de secondes -> secondes."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(texte or ""))
    if not m:
        return defaut
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


# ---------------------------------------------------------------- fichiers
def dossier_moteur():
    for d in (donnees.DOSSIER_PROGRAMME / "moteur", donnees.DONNEES / "moteur"):
        if (d / "llama-server.exe").exists():
            return d
    return None


def _modele_ollama():
    """Le modèle qwen3:8b déjà téléchargé par Ollama, s'il y en a un (on le lit en place, sans le copier)."""
    racine = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")
    try:
        manifeste = json.loads((racine / "manifests/registry.ollama.ai/library/qwen3/8b").read_text("utf-8"))
        for couche in manifeste["layers"]:
            if couche["mediaType"].endswith("image.model"):
                f = racine / "blobs" / couche["digest"].replace(":", "-")
                if f.exists() and f.stat().st_size >= TAILLE_MODELE_MIN:
                    return f
    except (OSError, KeyError, ValueError):
        pass
    return None


def trouver_modele(config):
    voulu = config.get("modele_fichier")
    if voulu and Path(os.path.expandvars(str(voulu))).expanduser().exists():
        return Path(os.path.expandvars(str(voulu))).expanduser()
    local = donnees.DONNEES / "modeles" / NOM_MODELE
    if local.exists() and local.stat().st_size >= TAILLE_MODELE_MIN:
        return local
    return _modele_ollama()


def telecharger(url, dest, sur_etat=None, nom="", taille_min=0):
    """Téléchargement qui reprend là où il s'est arrêté (proxy de l'entreprise pris en compte)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for essai in range(6):
        deja = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={"User-Agent": "AssistantIsland"})
        if deja:
            req.add_header("Range", f"bytes={deja}-")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if deja and r.status != 206:
                    deja = 0
                total = deja + int(r.headers.get("Content-Length") or 0)
                dernier = 0.0
                with open(part, "ab" if deja else "wb") as f:
                    while True:
                        bloc = r.read(1 << 20)
                        if not bloc:
                            break
                        f.write(bloc)
                        deja += len(bloc)
                        if sur_etat and total and time.monotonic() - dernier > 1:
                            dernier = time.monotonic()
                            sur_etat(f"Téléchargement {nom} : {deja * 100 // total} % ({deja >> 20} / {total >> 20} Mo)")
            break
        except urllib.error.HTTPError as e:
            if e.code == 416:                        # le fichier .part est déjà complet
                break
            if essai == 5:
                raise
        except (OSError, http.client.HTTPException):
            if essai == 5:
                raise
            time.sleep(3 * (essai + 1))
    if part.stat().st_size < taille_min:
        raise RuntimeError(f"Téléchargement incomplet ({part.stat().st_size >> 20} Mo)")
    os.replace(part, dest)
    return dest


def installer_moteur(sur_etat=None):
    """Version « développeur » : Dropi.exe a déjà le moteur ; depuis les sources on le télécharge une fois."""
    import zipfile
    dest = donnees.DONNEES / "moteur"
    zip_ = telecharger(URL_MOTEUR, donnees.DONNEES / "moteur.zip", sur_etat, "du moteur IA")
    with zipfile.ZipFile(zip_) as z:
        z.extractall(dest)
    zip_.unlink()
    return dest


# ---------------------------------------------------------------- carte graphique
def _powershell(script, delai=15):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, timeout=delai, creationflags=SANS_FENETRE)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def gpu_utilisation():
    """% d'utilisation 3D de la carte graphique en ce moment (0 si on ne sait pas)."""
    sortie = _powershell(
        "(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine "
        "| Where-Object { $_.Name -like '*engtype_3D*' } "
        "| Measure-Object -Property UtilizationPercentage -Sum).Sum")
    try:
        return min(100.0, float(sortie.replace(",", ".")))
    except ValueError:
        return 0.0


def cartes(exe):
    """Les cartes vues par llama.cpp : [(nom, Mo libres)]."""
    try:
        r = subprocess.run([str(exe), "--list-devices"], capture_output=True, text=True, timeout=30,
                           creationflags=SANS_FENETRE)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [(m.group(1).strip(), int(m.group(3))) for m in
            re.finditer(r"^\s*\w+\d+:\s*(.+?)\s*\((\d+) MiB, (\d+) MiB free\)", r.stdout + r.stderr, re.M)]


# ---------------------------------------------------------------- le serveur
_job = None


def _lier_au_programme(proc):
    """Si l'assistant se ferme ou plante, Windows arrête aussi le moteur (sinon il garderait 6 Go de mémoire)."""
    global _job
    try:
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]

        class Base(ctypes.Structure):
            _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                        ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

        class Etendu(ctypes.Structure):
            _fields_ = [("Base", Base), ("io", ctypes.c_uint64 * 6), ("m", ctypes.c_size_t * 4)]

        _job = k.CreateJobObjectW(None, None)
        info = Etendu()
        info.Base.LimitFlags = 0x2000                       # KILL_ON_JOB_CLOSE
        k.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k.AssignProcessToJobObject(_job, int(proc._handle))
    except Exception:
        pass


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Moteur:
    def __init__(self, config, sur_etat=None):
        self.config = config
        self.sur_etat = sur_etat or (lambda texte: None)
        self.garder = duree(config.get("garder_en_memoire"), 900)
        self.contexte = int(config.get("ia_contexte", 6144))
        self.proc, self.port, self.cle_cache = None, None, None
        self.sur = ""                                   # « carte graphique » ou « processeur » : où tourne le modèle
        self._verrou = threading.RLock()
        self._derniere = time.monotonic()
        self._occupe = 0                                # demandes en cours : on ne décharge pas pendant l'une d'elles
        threading.Thread(target=self._veille, daemon=True).start()

    # -- vie du serveur
    def vivant(self):
        return self.proc is not None and self.proc.poll() is None

    def _etat(self, texte):
        try:
            self.sur_etat(texte)
        except Exception:
            pass

    def _preparer(self):
        dossier = dossier_moteur() or installer_moteur(self._etat)
        modele = trouver_modele(self.config)
        if modele is None:
            modele = telecharger(self.config.get("modele_url") or URL_MODELE,
                                 donnees.DONNEES / "modeles" / NOM_MODELE, self._etat,
                                 "du modèle IA (une seule fois)", TAILLE_MODELE_MIN)
        return dossier / "llama-server.exe", modele

    def _arguments(self, exe, modele):
        gpu = str(self.config.get("ia_gpu", "auto")).lower()
        cartes_vues = cartes(exe) if gpu != "non" else []
        utiliser_gpu = bool(cartes_vues)
        if utiliser_gpu and gpu == "auto" and gpu_utilisation() > GPU_OCCUPE:
            utiliser_gpu = False                         # la carte est déjà bien occupée : on ne la charge pas
        coeurs = int(self.config.get("ia_threads") or max(2, (os.cpu_count() or 4) // 2 - 1))
        args = [str(exe), "-m", str(modele), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(self.contexte), "-np", "1", "-t", str(coeurs), "-fa", "on",
                "-ctk", "q8_0", "-ctv", "q8_0", "--jinja", "--no-webui", "--cache-reuse", "256",
                "--slot-save-path", str(donnees.DONNEES / "cache_ia")]
        if utiliser_gpu:
            args += ["--fit", "on", "-fitt", str(MARGE_VRAM), "-ngl", "99"]
            self.sur = "carte graphique"
        else:
            args += ["--device", "none", "-ngl", "0"]
            self.sur = "processeur"
        return args

    def demarrer(self):
        with self._verrou:
            if self.vivant():
                return
            exe, modele = self._preparer()
            self.port = _port_libre()
            (donnees.DONNEES / "cache_ia").mkdir(exist_ok=True)
            self._etat("Chargement de l'IA…")
            args = self._arguments(exe, modele)
            self.proc = subprocess.Popen(args, cwd=str(exe.parent), stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=SANS_FENETRE | PRIORITE_BASSE)
            _lier_au_programme(self.proc)
            fin = time.monotonic() + 600
            while time.monotonic() < fin:
                if self.proc.poll() is not None:
                    raise RuntimeError("Le moteur d'IA s'est arrêté au démarrage.")
                try:
                    c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                    c.request("GET", "/health")
                    if c.getresponse().status == 200:
                        self._etat("")
                        return
                except OSError:
                    pass
                time.sleep(0.5)
            self.arreter_moteur()
            raise RuntimeError("Le moteur d'IA met trop de temps à démarrer.")

    def arreter_moteur(self):
        with self._verrou:
            if self.proc is not None:
                try:
                    self.proc.terminate()
                    self.proc.wait(10)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self.proc = None

    def pret(self):
        """À appeler avant chaque demande : (re)lance le moteur au besoin et note qu'il sert."""
        self._derniere = time.monotonic()
        if not self.vivant():
            self.demarrer()
        return self.port

    def connexion(self, delai=900):
        return http.client.HTTPConnection("127.0.0.1", self.pret(), timeout=delai)

    def en_cours(self, debut):
        """Marque le début (True) ou la fin (False) d'une demande : le moteur ne se décharge pas pendant."""
        with self._verrou:
            self._occupe += 1 if debut else -1
            self._derniere = time.monotonic()

    def _veille(self):
        while True:
            time.sleep(20)
            with self._verrou:
                if self.vivant() and not self._occupe and time.monotonic() - self._derniere > self.garder:
                    self.arreter_moteur()

    # -- cache de lecture des consignes
    def _slot(self, action, nom):
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.pret(), timeout=120)
            c.request("POST", f"/slots/0?action={action}", json.dumps({"filename": nom}),
                      {"Content-Type": "application/json"})
            return c.getresponse().status == 200
        except OSError:
            return False

    def restaurer_cache(self, cle):
        """Recharge la lecture des consignes faite une fois pour toutes (rien à recalculer)."""
        self.cle_cache = "base-" + hashlib.sha1(f"{cle}|{self.contexte}|{BUILD_MOTEUR}".encode()).hexdigest()[:12] + ".bin"
        return (donnees.DONNEES / "cache_ia" / self.cle_cache).exists() and self._slot("restore", self.cle_cache)

    def sauver_cache(self):
        if self.cle_cache:
            for ancien in (donnees.DONNEES / "cache_ia").glob("base-*.bin"):
                if ancien.name != self.cle_cache:
                    ancien.unlink(missing_ok=True)
            self._slot("save", self.cle_cache)
