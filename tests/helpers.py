"""Helper condivisi dei test GUI: wav sintetici e Internet Archive finto.

Duplicati consapevolmente dal repo del motore (plan 003, D-S4): poche
righe contro l'interfaccia stabile di archivedigger, non valgono un
pacchetto di test condiviso.
"""

import numpy as np
import soundfile as sf
from archivedigger.models import IAFile, IAItem


def write_wav(path, seconds, sample_rate=48000):
    frames = round(seconds * sample_rate)
    sf.write(str(path), np.zeros(frames, dtype=np.float32), sample_rate)


def make_state(pool, duration=1.0):
    """Stato minimo dei controlli: un layer, un pool, render veloce."""
    return {
        "global": {"seed": {"enabled": True, "value": 7}},
        "layers": [{
            "layer_id": "uno",
            "pool": str(pool),
            "params": {
                "duration": {"enabled": True, "value": duration},
                "fragment.duration": {"enabled": True, "value": 0.25},
            },
        }],
    }


class FakeArchiveClient:
    """Client Internet Archive finto: cataloghi in memoria, download che
    scrive wav reali. Registra query e max_items ricevuti."""

    def __init__(self, n_items=50, length=5.0):
        self._length = length
        self._ids = [f"item-{i:03d}" for i in range(n_items)]
        self.queries: list[str] = []
        self.max_items_seen: list[int] = []

    def search(self, query, sort="downloads desc", max_items=100):
        self.queries.append(query)
        self.max_items_seen.append(max_items)
        yield from self._ids[:max_items]

    def get_item(self, identifier):
        file = IAFile(name=f"{identifier}.wav", format="WAVE",
                      size=1000, length=self._length, source="original")
        return IAItem(identifier=identifier, metadata={}, files=[file])

    def download_file(self, item, file, local_path):
        local_path.parent.mkdir(parents=True, exist_ok=True)
        write_wav(local_path, self._length)
