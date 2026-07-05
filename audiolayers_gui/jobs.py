"""Lavori in background per la GUI: submit → polling → risultato.

Il runner è una strategy: un callable senza argomenti che produce il
percorso del file audio (render puro, dig+render, qualunque cosa). Il
manager conosce solo gli stati: running → done | error.
"""

import threading
import uuid


class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, runner) -> str:
        """Avvia il runner in un thread; ritorna l'id per il polling."""
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"state": "running", "detail": "", "result": None}

        def run():
            try:
                result = runner()
                update = {"state": "done", "result": result}
            except Exception as exc:  # il dettaglio arriva alla GUI
                update = {"state": "error", "detail": str(exc)}
            with self._lock:
                self._jobs[job_id].update(update)

        threading.Thread(target=run, daemon=True).start()
        return job_id

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {"state": "unknown", "detail": ""}
            return {"state": job["state"], "detail": job["detail"]}

    def result(self, job_id: str):
        with self._lock:
            return self._jobs[job_id]["result"]
