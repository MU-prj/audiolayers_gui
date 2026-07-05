"""Unit — job manager della GUI: lavori in background con stato.

Il runner è una strategy (callable che produce il wav): il manager non
sa se sotto c'è un render puro o dig+render.
"""

import threading
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

    def test_il_risultato_di_un_job_sconosciuto_e_none(self):
        # result() non solleva su id inesistenti: la route audio se ne
        # serve per rispondere 404 invece di schiantarsi.
        assert JobManager().result("boh") is None


class TestStati:
    def test_job_appena_avviato_e_running(self):
        via = threading.Event()
        manager = JobManager()
        job_id = manager.submit(lambda: via.wait(5))
        assert manager.status(job_id)["state"] == "running"
        via.set()
        assert wait_done(manager, job_id)["state"] == "done"

    def test_id_univoci_anche_per_job_simultanei(self):
        manager = JobManager()
        ids = [manager.submit(lambda: None) for _ in range(20)]
        assert len(set(ids)) == 20
        for job_id in ids:
            assert wait_done(manager, job_id)["state"] == "done"

    def test_il_risultato_di_un_job_fallito_resta_vuoto(self):
        manager = JobManager()
        job_id = manager.submit(lambda: 1 / 0)
        assert wait_done(manager, job_id)["state"] == "error"
        assert manager.result(job_id) is None

    def test_lo_stato_di_errore_non_contamina_gli_altri_job(self):
        manager = JobManager()
        rotto = manager.submit(lambda: 1 / 0)
        sano = manager.submit(lambda: "ok")
        assert wait_done(manager, rotto)["state"] == "error"
        assert wait_done(manager, sano)["state"] == "done"
        assert manager.result(sano) == "ok"
