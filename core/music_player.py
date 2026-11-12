"""Cooperative, non-blocking note player for the shared PWM buzzer."""
from assets.tunes.library import TUNES
try:
    from time import ticks_ms, ticks_add, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_add = lambda value, delta: value + delta
    ticks_diff = lambda newer, older: newer - older


class MusicPlayer:
    def __init__(self, sound, tunes=None):
        self.sound = sound
        self.tunes = TUNES if tunes is None else tunes
        self.index = 0
        self.note_index = 0
        self.tempo = 100
        self.playing = False
        self.paused = False
        self.deadline = 0
        self.remaining = 0

    def current_tune(self):
        return self.tunes[self.index] if self.tunes else {"name": "No tunes", "notes": ()}

    def select(self, index):
        if not self.tunes:
            return False
        self.stop()
        self.index = index % len(self.tunes)
        return True

    def start(self):
        tune = self.current_tune()
        if not self.sound.enabled or self.sound.buzzer is None or not tune["notes"]:
            return False
        if self.paused:
            return self.resume()
        self.note_index = 0
        self.playing = True
        self.paused = False
        return self._play_note()

    def pause(self):
        if not self.playing:
            return False
        self.remaining = max(0, ticks_diff(self.deadline, ticks_ms()))
        self.playing = False
        self.paused = True
        self.sound.music_end()
        return True

    def resume(self):
        if not self.paused:
            return self.start()
        self.paused = False
        self.playing = True
        self.deadline = ticks_add(ticks_ms(), self.remaining)
        frequency = self.current_tune()["notes"][self.note_index][0]
        if not self.sound.music_tone(frequency, self.sound.volume):
            self.playing = False
            self.paused = False
            return False
        return True

    def toggle(self):
        return self.pause() if self.playing else self.start()

    def stop(self):
        self.playing = False
        self.paused = False
        self.note_index = 0
        self.remaining = 0
        self.sound.music_end()

    def next(self, direction=1):
        if not self.tunes:
            return False
        was_playing = self.playing or self.paused
        self.index = (self.index + direction) % len(self.tunes)
        self.stop()
        if was_playing:
            return self.start()
        return True

    def adjust_tempo(self, amount):
        self.tempo = max(50, min(200, self.tempo + amount))
        if self.playing:
            self.deadline = ticks_add(ticks_ms(), self._duration(self.current_tune()["notes"][self.note_index][1]))

    def progress(self):
        notes = self.current_tune()["notes"]
        return self.note_index, len(notes)

    def update(self):
        if self.playing and ticks_diff(ticks_ms(), self.deadline) >= 0:
            self.note_index += 1
            if self.note_index >= len(self.current_tune()["notes"]):
                self.stop()
                return True
            return self._play_note()
        return False

    def _duration(self, beats):
        return max(20, (240 * beats * 100) // self.tempo)

    def _play_note(self):
        notes = self.current_tune()["notes"]
        if self.note_index >= len(notes):
            self.stop()
            return False
        frequency, beats = notes[self.note_index]
        duration = self._duration(beats)
        # Rest notes use frequency zero; SoundManager keeps the PWM output silent.
        if not self.sound.music_tone(frequency, self.sound.volume):
            self.playing = False
            self.paused = False
            return False
        self.deadline = ticks_add(ticks_ms(), duration)
        return True
