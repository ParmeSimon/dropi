"""« En cours de lecture » : la musique qui joue (Apple Music, Spotify…) affichée sur la goutte.

Windows publie ce qui joue dans ses « contrôles multimédias » (le petit panneau du volume) :
on y lit le titre, l'artiste, la cover et la position, une fois par seconde, dans un fil à part.
"""
import time
import asyncio
import datetime
import threading
import os
import importlib.util

# Les paquets winrt sont chargés seulement au démarrage de la surveillance, jamais avant Qt :
# ils apportent une vieille version des DLL Microsoft qui fait planter Qt si elle passe en premier.
_spec = importlib.util.find_spec("winrt")          # (chercher le sous-module chargerait déjà les DLL)
DISPONIBLE = bool(_spec and any(os.path.isdir(os.path.join(d, "windows", "media", "control"))
                                for d in (_spec.submodule_search_locations or [])))
Gestionnaire = Statut = DataReader = Buffer = InputStreamOptions = None


def _charger_winrt():
    global Gestionnaire, Statut, DataReader, Buffer, InputStreamOptions
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Gestionnaire,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Statut)
    from winrt.windows.storage.streams import DataReader, Buffer, InputStreamOptions

derniere = None                # ce qui joue en ce moment (dict), lu par l'île et par l'IA
_surveillant = None


def minutes(secondes):
    secondes = max(0, int(secondes))
    return f"{secondes // 60}:{secondes % 60:02d}"


class Surveillant:
    def __init__(self, sur_changement, applis=("applemusic", "itunes", "spotify")):
        self.sur_changement = sur_changement      # appelé depuis le fil de fond : passer par un signal Qt
        self.applis = [a.lower().replace(" ", "") for a in applis]
        self.boucle = None
        self.session = None
        self._piste, self._cover, self._essais_cover, self._debut = None, None, 0, time.monotonic()

    def demarrer(self):
        if DISPONIBLE:
            threading.Thread(target=self._fil, daemon=True).start()

    def _fil(self):
        _charger_winrt()
        self.boucle = asyncio.new_event_loop()
        asyncio.set_event_loop(self.boucle)
        self.boucle.run_until_complete(self._surveiller())

    async def _surveiller(self):
        global derniere
        gestionnaire = await Gestionnaire.request_async()
        while True:
            try:
                derniere = await self._lire(gestionnaire)
            except Exception:
                derniere = None
            self.sur_changement(derniere)
            await asyncio.sleep(1)

    def _accepte(self, appli):
        appli = (appli or "").lower().replace(" ", "")
        return "toutes" in self.applis or any(a in appli for a in self.applis)

    async def _lire(self, gestionnaire):
        sessions = [s for s in gestionnaire.get_sessions() if self._accepte(s.source_app_user_model_id)]
        en_lecture = [s for s in sessions if s.get_playback_info().playback_status == Statut.PLAYING]
        session = (en_lecture or sessions or [None])[0]
        self.session = session
        if session is None:
            return None
        props = await session.try_get_media_properties_async()
        if not props or not props.title:
            return None
        joue = session.get_playback_info().playback_status == Statut.PLAYING
        temps = session.get_timeline_properties()
        duree = (temps.end_time - temps.start_time).total_seconds()
        position = temps.position.total_seconds()
        # l'appli ne met la position à jour qu'aux changements : on ajoute le temps écoulé depuis
        if joue and temps.last_updated_time.year > 1601:
            position += (datetime.datetime.now(datetime.timezone.utc) - temps.last_updated_time).total_seconds()

        piste = f"{props.title}|{props.artist}"
        if piste != self._piste:
            self._piste, self._cover, self._essais_cover = piste, None, 0
            self._debut = time.monotonic() - position
        if self._cover is None and self._essais_cover < 5 and props.thumbnail:
            self._essais_cover += 1              # la cover arrive parfois une seconde après le titre
            self._cover = await self._lire_cover(props.thumbnail)
        if duree <= 0:                           # appli qui ne donne pas la position : on compte nous-mêmes
            position = time.monotonic() - self._debut
        return {"titre": props.title, "artiste": props.artist or props.album_artist or "",
                "album": props.album_title or "", "duree": max(0.0, duree),
                "position": min(position, duree) if duree > 0 else position, "joue": joue,
                "cover": self._cover, "piste": piste, "appli": session.source_app_user_model_id}

    @staticmethod
    async def _lire_cover(reference):
        flux = await reference.open_read_async()
        taille = flux.size
        tampon = Buffer(taille)
        await flux.read_async(tampon, taille, InputStreamOptions.READ_AHEAD)
        octets = bytearray(tampon.length)
        DataReader.from_buffer(tampon).read_bytes(octets)
        return bytes(octets)

    def commander(self, action):
        if self.boucle and self.session:
            asyncio.run_coroutine_threadsafe(self._commander(self.session, action), self.boucle)

    @staticmethod
    async def _commander(session, action):
        commandes = {"pause": session.try_toggle_play_pause_async, "lecture": session.try_toggle_play_pause_async,
                     "suivant": session.try_skip_next_async, "precedent": session.try_skip_previous_async}
        await commandes.get(action, session.try_toggle_play_pause_async)()


def demarrer(sur_changement, applis):
    global _surveillant
    _surveillant = Surveillant(sur_changement, applis)
    _surveillant.demarrer()


def commander(action):
    if _surveillant:
        _surveillant.commander(action)


def en_cours_texte():
    if not derniere:
        return "Aucune musique en cours de lecture."
    d = derniere
    etat = "en lecture" if d["joue"] else "en pause"
    return f"{d['titre']} de {d['artiste']} ({etat}, {minutes(d['position'])} / {minutes(d['duree'])})."
