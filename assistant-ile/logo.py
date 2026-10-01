"""Génère le logo (Plop) : logo.png + logo.ico, et un raccourci « Assistant » sur le Bureau.

    python logo.py              -> logo.png et logo.ico
    python logo.py --raccourci  -> en plus, raccourci sur le Bureau (version script)
"""
import sys
import struct
import subprocess
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from mascotte import image_logo

DOSSIER = Path(__file__).resolve().parent


def png(image):
    tampon = QBuffer()
    tampon.open(QIODevice.WriteOnly)
    image.save(tampon, "PNG")
    return bytes(tampon.data())


def ecrire_ico(chemin, tailles=(16, 24, 32, 48, 64, 128, 256)):
    """Fichier .ico multi-tailles (images PNG à l'intérieur, comme Windows le fait)."""
    images = [png(image_logo(t)) for t in tailles]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire, donnees = b"", b""
    for t, data in zip(tailles, images):
        repertoire += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(data), decalage + len(donnees))
        donnees += data
    Path(chemin).write_bytes(entete + repertoire + donnees)


def dossier_windows(nom):
    """Chemin d'un dossier spécial de Windows : Desktop, Programs (menu Démarrer)…"""
    return subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{nom}')"],
                          capture_output=True, text=True).stdout.strip()


def creer_raccourci(lnk, cible, arguments="", dossier="", icone=""):
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
              f"$s.TargetPath = '{cible}'; $s.Arguments = '{arguments}';"
              f"$s.WorkingDirectory = '{dossier}'; $s.IconLocation = '{icone or cible}';"
              f"$s.Description = 'Dropi'; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    print(f"Raccourci créé : {lnk}")


def raccourci_script():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    creer_raccourci(Path(dossier_windows("Desktop")) / "Dropi.lnk", pythonw, f'"{DOSSIER / "island.py"}"',
                    DOSSIER, DOSSIER / "logo.ico")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    image_logo(512).save(str(DOSSIER / "logo.png"))
    ecrire_ico(DOSSIER / "logo.ico")
    print("logo.png et logo.ico créés.")
    if "--raccourci" in sys.argv:
        raccourci_script()
