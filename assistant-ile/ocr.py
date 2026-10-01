"""Lire le texte d'une image avec la reconnaissance de caractères de Windows.

Tout se fait sur le PC (Windows.Media.Ocr), rien n'est envoyé. Les langues disponibles sont celles
installées dans Windows (Paramètres › Heure et langue).
"""
import asyncio

# Comme dans musique.py : les paquets winrt ne sont chargés qu'à l'usage, jamais avant Qt.


def lire(png, langue="fr-FR"):
    """Le texte (ligne par ligne) contenu dans une image PNG donnée en octets."""
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

    async def travail():
        flux = InMemoryRandomAccessStream()
        ecrivain = DataWriter(flux)
        ecrivain.write_bytes(png)
        await ecrivain.store_async()
        ecrivain.detach_stream()
        flux.seek(0)
        decodeur = await BitmapDecoder.create_async(flux)
        image = await decodeur.get_software_bitmap_async()
        moteur = None
        if OcrEngine.is_language_supported(Language(langue)):
            moteur = OcrEngine.try_create_from_language(Language(langue))
        moteur = moteur or OcrEngine.try_create_from_user_profile_languages()
        if moteur is None:
            raise RuntimeError("aucune langue de reconnaissance de texte n'est installée dans Windows")
        resultat = await moteur.recognize_async(image)
        return "\n".join(ligne.text for ligne in resultat.lines)

    return asyncio.run(travail())
