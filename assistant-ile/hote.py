"""Le relais entre l'extension du navigateur et l'assistant.

Le navigateur lance ce petit programme quand l'extension a quelque chose à dire (il n'accepte que
notre extension : voir passerelle.py). On transmet le message à l'assistant qui tourne, par un tube
local de Windows, et on renvoie sa réponse. Rien ne sort du PC.
"""
import os
import sys
import struct

TUBE = r"\\.\pipe\AssistantIsland-extension-" + os.environ.get("USERNAME", "")
FERME = b'{"ok": false, "erreur": "assistant_ferme"}'


def lire():
    """Un message du navigateur : 4 octets de longueur, puis du JSON."""
    entete = sys.stdin.buffer.read(4)
    if len(entete) < 4:
        return None
    return sys.stdin.buffer.read(struct.unpack("<I", entete)[0])


def repondre(octets):
    sys.stdout.buffer.write(struct.pack("<I", len(octets)) + octets)
    sys.stdout.buffer.flush()


def transmettre(message):
    try:
        with open(TUBE, "r+b", buffering=0) as tube:
            tube.write(message.replace(b"\n", b" ") + b"\n")
            return tube.readline().strip() or FERME
    except OSError:
        return FERME


if __name__ == "__main__":
    while True:
        message = lire()
        if message is None:
            break
        repondre(transmettre(message))
