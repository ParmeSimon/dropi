"""Micro : enregistre tant que le bouton est maintenu, puis transcrit en local avec Whisper."""
import numpy as np
import sounddevice as sd

TAUX = 16000


class Micro:
    def __init__(self, modele="small", langue="fr"):
        self.nom_modele = modele
        self.langue = langue
        self.modele = None
        self.morceaux = []
        self.flux = None

    def _charger(self):
        if self.modele is None:
            from faster_whisper import WhisperModel
            try:
                self.modele = WhisperModel(self.nom_modele, device="cuda", compute_type="float16")
            except Exception:
                self.modele = WhisperModel(self.nom_modele, device="cpu", compute_type="int8")

    def demarrer(self):
        self.morceaux = []
        self.flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="float32",
                                   callback=lambda data, *_: self.morceaux.append(data.copy()))
        self.flux.start()

    def arreter_et_transcrire(self):
        if self.flux:
            self.flux.stop()
            self.flux.close()
            self.flux = None
        if not self.morceaux:
            return ""
        audio = np.concatenate(self.morceaux).flatten()
        if len(audio) < TAUX * 0.4:  # moins de 0,4 s : clic accidentel
            return ""
        self._charger()
        segments, _ = self.modele.transcribe(audio, language=self.langue, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
