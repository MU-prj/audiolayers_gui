"""Unit — job manager della GUI: lavori in background con stato.

Il runner è una strategy (callable che produce il wav): il manager non
sa se sotto c'è un render puro o dig+render.
"""

import time

from audiolayers_gui.jobs import JobManager


def wait_done(manager, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = manager.status(job_id)
        if status["state"] in ("done", "error"):
            return status
        time.sleep(0.01)
    raise AssertionError("job mai terminato")


class TestJobManager:
    def test_job_completato_espone_il_risultato(self, tmp_path):
        out = tmp_path / "x.wav"

        def runner():
            out.write_bytes(b"RIFF")
            return out

        manager = JobManager()
        job_id = manager.submit(runner)
        status = wait_done(manager, job_id)
        assert status["state"] == "done"
        assert manager.result(job_id) == out

    def test_job_fallito_riporta_l_errore(self):
        def runner():
            raise RuntimeError("pool vuoto")

        manager = JobManager()
        job_id = manager.submit(runner)
        status = wait_done(manager, job_id)
        assert status["state"] == "error"
        assert "pool vuoto" in status["detail"]

    def test_job_sconosciuto(self):
        assert JobManager().status("boh")["state"] == "unknown"
