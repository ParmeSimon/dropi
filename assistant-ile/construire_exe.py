"""Construit Assistant.exe (avec Plop en icône), l'installe, et le lance au démarrage de Windows.

    python construire_exe.py          (ou double-clic sur construire_exe.bat)

L'appli est installée dans %LOCALAPPDATA%\\Programs\\Assistant Island, avec un raccourci sur le Bureau
et dans le menu Démarrer. Ta config (config.yaml, à côté de Assistant.exe) est gardée d'une
installation à l'autre ; ta mémoire et le journal des rangements sont dans %APPDATA%\\AssistantIle.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ICI = Path(__file__).resolve().parent
CHANTIER = ICI / "construction"
DESTINATION = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Assistant Island"


def etape(texte):
    print(f"\n=== {texte}", flush=True)


def construire():
    etape("Dépendances")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(ICI / "requirements.txt"),
                    "pyinstaller"], check=True)
    etape("Logo")
    subprocess.run([sys.executable, str(ICI / "logo.py")], check=True, cwd=ICI)
    etape("Construction de Assistant.exe (quelques minutes)")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "Assistant", "--icon", str(ICI / "logo.ico"),
        "--distpath", str(CHANTIER / "dist"), "--workpath", str(CHANTIER / "build"), "--specpath", str(CHANTIER),
        "--collect-all", "faster_whisper", "--collect-binaries", "ctranslate2", "--collect-all", "winrt",
        "--collect-all", "_sounddevice_data",
        "--exclude-module", "tkinter", "--exclude-module", "matplotlib", "--exclude-module", "torch",
        str(ICI / "island.py"),
    ], check=True, cwd=ICI)


def installer():
    etape(f"Installation dans {DESTINATION}")
    subprocess.run(["taskkill", "/IM", "Assistant.exe", "/F"], capture_output=True)   # l'ancienne version
    source = CHANTIER / "dist" / "Assistant"
    DESTINATION.mkdir(parents=True, exist_ok=True)
    if (DESTINATION / "_internal").exists():
        shutil.rmtree(DESTINATION / "_internal")
    shutil.copytree(source, DESTINATION, dirs_exist_ok=True)
    if not (DESTINATION / "config.yaml").exists():
        shutil.copy2(ICI / "config.yaml", DESTINATION / "config.yaml")
    exe = DESTINATION / "Assistant.exe"

    etape("Raccourcis et démarrage avec Windows")
    sys.path.insert(0, str(ICI))
    from logo import creer_raccourci, dossier_windows
    import demarrage
    creer_raccourci(Path(dossier_windows("Desktop")) / "Assistant.lnk", exe, dossier=DESTINATION)
    creer_raccourci(Path(dossier_windows("Programs")) / "Assistant Island.lnk", exe, dossier=DESTINATION)
    demarrage.activer(f'"{exe}"')
    print("Lancement automatique au démarrage de Windows : activé (clic droit sur la goutte pour le couper).")
    print(f"\nTerminé ! Assistant.exe est dans {DESTINATION}")


if __name__ == "__main__":
    if "--installer-seulement" not in sys.argv:
        construire()
    installer()
