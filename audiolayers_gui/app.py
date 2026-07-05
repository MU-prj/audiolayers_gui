"""GUI web di audiolayers: Flask minimale sopra il motore.

Factory `create_app` con dipendenze iniettabili (client Internet Archive
per --dig, cartella output): i test girano offline, la CLI `python -m
audiolayers_gui` usa i default veri. Il render gira come job in background
(JobManager) e la GUI fa polling.
"""

import contextlib
import io
import tempfile
import threading
import time
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_file

from audiolayers_gui.jobs import JobManager
from audiolayers_gui.score_builder import build_score, parse_score

STATIC_DIR = Path(__file__).parent / "static"


class LogBuffer:
    """Terminale della GUI: righe con timestamp, lettura incrementale."""

    def __init__(self, max_lines: int = 500):
        self._lines: list[tuple[str, str]] = []
        self._max = max_lines
        self._offset = 0          # indice assoluto della prima riga tenuta
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        for line in text.splitlines():
            if line.strip():
                self.add(line.rstrip())

    def flush(self) -> None:      # interfaccia file-like per redirect_stdout
        pass

    def add(self, line: str) -> None:
        with self._lock:
            self._lines.append((time.strftime("%H:%M:%S"), line))
            overflow = len(self._lines) - self._max
            if overflow > 0:
                del self._lines[:overflow]
                self._offset += overflow

    def since(self, index: int) -> dict:
        with self._lock:
            start = max(0, index - self._offset)
            return {"lines": self._lines[start:],
                    "next": self._offset + len(self._lines)}


@contextlib.contextmanager
def _log_errors(log: LogBuffer):
    try:
        yield
    except Exception as exc:
        log.add(f"ERRORE: {exc}")
        raise


def create_app(*, output_dir: Path | None = None,
               archive_client=None) -> Flask:
    app = Flask("audiolayers_gui", static_folder=str(STATIC_DIR),
                static_url_path="/static")
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="audiolayers_gui_"))
    out.mkdir(parents=True, exist_ok=True)
    jobs = JobManager()
    log = LogBuffer()
    # I render condividono gli stessi file (out/score.yaml, out/render.wav)
    # e il redirect di stdout/stderr è globale al processo: due render
    # concorrenti si sovrascriverebbero la partitura a metà lettura. Il
    # JobManager resta asincrono (submit/polling), ma la fase di scrittura
    # e sintesi viene serializzata.
    render_lock = threading.Lock()

    @app.get("/")
    def index():
        return send_file(STATIC_DIR / "index.html")

    @app.post("/api/render")
    def render():
        payload = request.get_json(force=True)
        score = build_score(payload["state"])
        dig = bool(payload.get("dig"))

        def runner():
            # Tutto ciò che il motore stampa (picco, seed, warning del
            # dig) finisce nel terminale della GUI.
            with render_lock, \
                 contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), \
                 _log_errors(log):
                score_path = out / "score.yaml"
                score_path.write_text(
                    yaml.safe_dump(score, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
                log.add(f"partitura scritta: {len(score['layers'])} layer")
                if dig:
                    log.add("dig: analisi partitura e download da Internet Archive...")
                    from audiolayers.provisioning.pool_source import provision_score
                    provision_score(score_path, client=archive_client)
                    log.add("dig: completato")
                log.add("render: avviato")
                from audiolayers.engine.render import render_score
                wav_path = out / "render.wav"
                render_score(score_path, wav_path)
                log.add(f"render: completato -> {wav_path.name}")
            return wav_path

        job_id = jobs.submit(runner)
        log.add(f"job {job_id}: accodato" + (" (con dig)" if dig else ""))
        return jsonify({"job_id": job_id})

    @app.get("/api/log")
    def read_log():
        return jsonify(log.since(request.args.get("since", 0, type=int)))

    @app.get("/api/params")
    def params():
        """Catalogo dei parametri: la GUI si genera da qui (fonte unica)."""
        from audiolayers.parameters.catalog import catalog
        return jsonify(catalog())

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id):
        return jsonify(jobs.status(job_id))

    @app.get("/api/jobs/<job_id>/audio")
    def job_audio(job_id):
        return send_file(jobs.result(job_id), mimetype="audio/wav")

    @app.post("/api/yaml")
    def export_yaml():
        score = build_score(request.get_json(force=True)["state"])
        text = yaml.safe_dump(score, sort_keys=False, allow_unicode=True)
        return text, 200, {"Content-Type": "text/yaml; charset=utf-8"}

    @app.post("/api/import")
    def import_yaml():
        score = yaml.safe_load(request.get_data(as_text=True))
        return jsonify(parse_score(score))

    return app
