"""Construit l'installateur de l'assistant : UN seul fichier, Dropi-Setup.exe.

    python construire_exe.py                 -> construction/Dropi-Setup.exe  (à mettre dans la « release »)
    python construire_exe.py --local         -> construit puis installe directement sur ce PC (sans installateur)
    python construire_exe.py --local --installer-seulement   (réinstalle la dernière construction)

Ce qu'embarque l'installateur : Dropi.exe (Python + interface + voix), le moteur d'IA (llama.cpp, build
Vulkan : Nvidia, AMD et Intel) et la config. Le modèle d'IA (~5 Go) est trop gros pour une release GitHub (2 Go
max par fichier) : il se télécharge tout seul, une fois, au premier lancement (voir moteur.py).

Pour construire l'installateur il faut Inno Setup 6 :  winget install JRSoftware.InnoSetup
L'appli s'installe dans %LOCALAPPDATA%\\Programs\\Dropi (pas besoin d'être administrateur), avec un
raccourci sur le Bureau, dans le menu Démarrer, et un lancement avec Windows. La config (config.yaml) est gardée
d'une mise à jour à l'autre ; mémoire et journal sont dans %APPDATA%\\AssistantIle.
"""
import os
import re
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
CHANTIER = ICI / "construction"
DIST = CHANTIER / "dist" / "Dropi"
DESTINATION = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Dropi"

sys.path.insert(0, str(ICI))
import moteur                                                      # noqa: E402  (version du moteur à embarquer)

# Ce que le serveur d'IA n'a pas besoin d'embarquer : les outils de test, de bench, l'ARM, les autres exe.
GARDER_EXE = {"llama-server.exe"}
JETER_DLL = re.compile(r"^(llama-(?!server|common)|ggml-rpc|ggml-cpu-(cannonlake|cascadelake|cooperlake|piledriver|ivybridge))")
JETER_QT = ["Qt3D", "QtBluetooth", "QtCharts", "QtDataVisualization", "QtDesigner", "QtHelp", "QtMultimedia",
            "QtNfc", "QtOpenGL", "QtPdf", "QtPositioning", "QtQml", "QtQuick", "QtRemoteObjects", "QtScxml",
            "QtSensors", "QtSerialPort", "QtSql", "QtSvg", "QtTest", "QtWebChannel", "QtWebEngine", "QtWebSockets",
            "QtXml", "QtStateMachine", "QtSpatialAudio", "QtTextToSpeech", "QtHttpServer", "QtGraphs"]


def etape(texte):
    print(f"\n=== {texte}", flush=True)


def taille(dossier):
    return sum(f.stat().st_size for f in Path(dossier).rglob("*") if f.is_file()) / 1e6


def preparer_moteur():
    """Télécharge llama.cpp (Vulkan) une fois, puis le dépose allégé dans l'appli."""
    zip_ = CHANTIER / f"moteur-{moteur.BUILD_MOTEUR}.zip"
    if not zip_.exists():
        CHANTIER.mkdir(exist_ok=True)
        moteur.telecharger(moteur.URL_MOTEUR, zip_, lambda t: print("  " + t, end="\r"), "du moteur")
    cible = DIST / "moteur"
    shutil.rmtree(cible, ignore_errors=True)
    with zipfile.ZipFile(zip_) as z:
        z.extractall(cible)
    for f in cible.iterdir():
        if (f.suffix == ".exe" and f.name not in GARDER_EXE) or (f.suffix == ".dll" and JETER_DLL.match(f.name)):
            f.unlink()
    # le serveur doit encore répondre une fois allégé
    r = subprocess.run([str(cible / "llama-server.exe"), "--list-devices"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        sys.exit("Le moteur allégé ne démarre plus :\n" + (r.stdout + r.stderr)[-500:])
    print(f"  moteur : {taille(cible):.0f} Mo")


def construire():
    etape("Dépendances")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(ICI / "requirements.txt"),
                    "pyinstaller"], check=True)
    etape("Logo")
    subprocess.run([sys.executable, str(ICI / "logo.py")], check=True, cwd=ICI)
    etape("Construction de Dropi.exe (quelques minutes)")
    exclusions = [x for m in ["tkinter", "matplotlib", "torch", "unittest", "pydoc_data", "PIL.ImageQt"] for x in ("--exclude-module", m)]
    exclusions += [x for m in JETER_QT for x in ("--exclude-module", "PySide6." + m)]
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "Dropi", "--icon", str(ICI / "logo.ico"),
        "--distpath", str(CHANTIER / "dist"), "--workpath", str(CHANTIER / "build"), "--specpath", str(CHANTIER),
        "--collect-all", "faster_whisper", "--collect-binaries", "ctranslate2", "--collect-all", "winrt",
        "--collect-all", "_sounddevice_data", *exclusions,
        str(ICI / "island.py"),
    ], check=True, cwd=ICI)
    etape("Allègement")
    interne = DIST / "_internal"
    for tr in interne.rglob("translations"):                      # traductions de Qt : on n'en a pas besoin
        shutil.rmtree(tr, ignore_errors=True)
    shutil.copy2(ICI / "config.yaml", DIST / "config.yaml")
    etape("Moteur d'IA")
    preparer_moteur()
    print(f"\nAppli complète : {taille(DIST):.0f} Mo")


SCRIPT_INNO = r'''
[Setup]
AppId={{B0E7C2A4-5B6C-4E1B-9D55-A55157A4715E}
AppName=Dropi
AppVersion=@VERSION@
AppPublisher=Dropi
DefaultDirName={localappdata}\Programs\Dropi
DefaultGroupName=Dropi
PrivilegesRequired=lowest
OutputDir=@SORTIE@
OutputBaseFilename=Dropi-Setup
SetupIconFile=@LOGO@
UninstallDisplayIcon={app}\Dropi.exe
Compression=lzma2/max
LZMADictionarySize=32768
SolidCompression=yes
LZMANumBlockThreads=2
CloseApplications=force
RestartApplications=no
DisableProgramGroupPage=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "@DIST@\*"; DestDir: "{app}"; Excludes: "config.yaml"; Flags: recursesubdirs ignoreversion
Source: "@DIST@\config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autodesktop}\Dropi"; Filename: "{app}\Dropi.exe"
Name: "{group}\Dropi"; Filename: "{app}\Dropi.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Dropi"; ValueData: """{app}\Dropi.exe"""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AssistantIsland"; Flags: deletevalue

[InstallDelete]
Type: filesandordirs; Name: "{localappdata}\Programs\Assistant Island"
Type: files; Name: "{autodesktop}\Assistant.lnk"
Type: files; Name: "{group}\Assistant Island.lnk"

[Run]
Filename: "{app}\Dropi.exe"; Description: "Lancer Dropi"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Dropi.exe /F"; Flags: runhidden; RunOnceId: "StopDropi"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM llama-server.exe /F"; Flags: runhidden; RunOnceId: "StopMoteur"

[Code]
function InitializeSetup(): Boolean;
var R: Integer;
begin
  Exec(ExpandConstant('{sys}	askkill.exe'), '/IM Assistant.exe /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Result := True;
end;
'''


def installateur():
    etape("Installateur Dropi-Setup.exe")
    iscc = next((p for p in [Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 6/ISCC.exe",
                             Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
                             Path(r"C:\Program Files\Inno Setup 6\ISCC.exe")] if p.exists()), None)
    if iscc is None:
        sys.exit("Inno Setup 6 est nécessaire :  winget install JRSoftware.InnoSetup")
    version = os.environ.get("VERSION") or "1.0"
    iss = CHANTIER / "assistant.iss"
    iss.write_text(SCRIPT_INNO.replace("@VERSION@", version).replace("@SORTIE@", str(CHANTIER))
                   .replace("@LOGO@", str(ICI / "logo.ico")).replace("@DIST@", str(DIST)),
                   encoding="utf-8-sig")
    subprocess.run([str(iscc), "/Q", str(iss)], check=True)
    exe = CHANTIER / "Dropi-Setup.exe"
    print(f"\nTerminé ! {exe}  ({exe.stat().st_size / 1e6:.0f} Mo)")


def installer_ici():
    etape(f"Installation dans {DESTINATION}")
    subprocess.run(["taskkill", "/IM", "Dropi.exe", "/F"], capture_output=True)   # l'ancienne version
    subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], capture_output=True)
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for ancien in ("_internal", "moteur"):
        if (DESTINATION / ancien).exists():
            shutil.rmtree(DESTINATION / ancien)
    shutil.copytree(DIST, DESTINATION, dirs_exist_ok=True,
                    ignore=lambda d, noms: ["config.yaml"] if (DESTINATION / "config.yaml").exists() else [])
    exe = DESTINATION / "Dropi.exe"

    etape("Raccourcis et démarrage avec Windows")
    from logo import creer_raccourci, dossier_windows
    import demarrage
    creer_raccourci(Path(dossier_windows("Desktop")) / "Dropi.lnk", exe, dossier=DESTINATION)
    creer_raccourci(Path(dossier_windows("Programs")) / "Dropi.lnk", exe, dossier=DESTINATION)
    demarrage.activer(f'"{exe}"')
    print("Lancement automatique au démarrage de Windows : activé (clic droit sur la goutte pour le couper).")
    print(f"\nTerminé ! Dropi.exe est dans {DESTINATION}")


if __name__ == "__main__":
    if "--installer-seulement" not in sys.argv:
        construire()
    if "--local" in sys.argv:
        installer_ici()
    else:
        installateur()
