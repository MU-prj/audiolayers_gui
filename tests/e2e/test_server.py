"""E2E — il server vero via subprocess: `python -m audiolayers_gui`.

Come per la CLI del motore, qui niente test client: si avvia il processo
reale su una porta libera e si parla HTTP con la stdlib. Copre l'avvio
(`--port` rispettato), il flusso completo render → polling → download e
il round trip YAML sul filo.
"""

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from tests.helpers import make_state, write_wav

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]


def porta_libera():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as risposta:
        return json.loads(risposta.read())


def post(url, data: bytes, content_type):
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=10) as risposta:
        return risposta.read()


@pytest.fixture(scope="module")
def server():
    """Il processo reale, su una porta scelta qui: se risponde lì,
    `--port` funziona."""
    porta = porta_libera()
    processo = subprocess.Popen(
        [sys.executable, "-m", "audiolayers_gui", "--port", str(porta)],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    base = f"http://127.0.0.1:{porta}"
    try:
        scadenza = time.time() + 20
        while True:
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except OSError:
                if processo.poll() is not None or time.time() > scadenza:
                    raise AssertionError("il server non è mai partito")
                time.sleep(0.2)
        yield base
    finally:
        processo.terminate()
        processo.wait(timeout=10)


class TestServerReale:
    def test_pagina_e_catalogo_rispondono(self, server):
        with urllib.request.urlopen(server + "/", timeout=10) as risposta:
            assert b"audiolayers" in risposta.read().lower()
        catalogo = get_json(server + "/api/params")
        assert set(catalogo) == {"global", "layer", "provision"}

    def test_flusso_completo_render_polling_download(self, server, tmp_path):
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)

        payload = json.dumps({"state": make_state(pool)}).encode()
        job = json.loads(post(server + "/api/render", payload,
                              "application/json"))

        scadenza = time.time() + 60
        while time.time() < scadenza:
            stato = get_json(f"{server}/api/jobs/{job['job_id']}")
            if stato["state"] in ("done", "error"):
                break
            time.sleep(0.2)
        assert stato["state"] == "done", stato

        with urllib.request.urlopen(
                f"{server}/api/jobs/{job['job_id']}/audio",
                timeout=30) as risposta:
            wav = risposta.read()
        assert wav[:4] == b"RIFF"

        log = get_json(server + "/api/log")
        testo = "\n".join(riga for _, riga in log["lines"])
        assert "render: completato" in testo

    def test_yaml_round_trip_sul_filo(self, server, tmp_path):
        state = make_state(tmp_path / "pool")
        payload = json.dumps({"state": state}).encode()

        esportato = post(server + "/api/yaml", payload,
                         "application/json").decode()
        assert yaml.safe_load(esportato)["layers"][0]["fragment"]["duration"] == 0.25

        importato = json.loads(post(server + "/api/import",
                                    esportato.encode(), "text/yaml"))
        assert importato["layers"][0]["params"]["fragment.duration"]["value"] == 0.25
