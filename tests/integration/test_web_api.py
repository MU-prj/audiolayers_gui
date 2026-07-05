"""Integration — API della GUI: render asincrono end-to-end, YAML I/O.

Motore vero su partiture minuscole; Internet Archive finto (il client è
iniettabile nella factory, come in CLI e archivedigger).
"""

import time

import yaml

from audiolayers_gui.app import create_app
from tests.helpers import FakeArchiveClient, write_wav


def make_state(pool, duration=1.0):
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


def wait_done(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").get_json()
        if status["state"] in ("done", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError("job mai terminato")


class TestWebApi:
    def test_render_asincrono_produce_wav_scaricabile(self, tmp_path):
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()

        job_id = client.post("/api/render",
                             json={"state": make_state(pool)}).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "done"

        audio = client.get(f"/api/jobs/{job_id}/audio")
        assert audio.status_code == 200
        assert audio.data[:4] == b"RIFF"

    def test_render_con_dig_popola_il_pool(self, tmp_path):
        pool = tmp_path / "pool"
        app = create_app(output_dir=tmp_path / "out",
                         archive_client=FakeArchiveClient())
        client = app.test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(pool), "dig": True}
                             ).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "done"
        assert list(pool.glob("*.wav"))

    def test_errore_del_render_arriva_alla_gui(self, tmp_path):
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(tmp_path / "vuoto")}
                             ).get_json()["job_id"]
        status = wait_done(client, job_id)
        assert status["state"] == "error"
        assert status["detail"]

    def test_yaml_export_e_import_round_trip(self, tmp_path):
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()
        state = make_state(tmp_path / "pool")

        exported = client.post("/api/yaml", json={"state": state}).data.decode()
        assert yaml.safe_load(exported)["layers"][0]["fragment"]["duration"] == 0.25

        imported = client.post("/api/import", data=exported,
                               content_type="text/yaml").get_json()
        assert imported["layers"][0]["params"]["fragment.duration"]["value"] == 0.25

    def test_terminale_espone_l_output_del_motore(self, tmp_path):
        """Il render stampa picco/seed: le righe finiscono nel log della
        GUI, leggibili a incrementi con ?since=."""
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(pool)}).get_json()["job_id"]
        wait_done(client, job_id)

        log = client.get("/api/log").get_json()
        text = "\n".join(line for _, line in log["lines"])
        assert "picco" in text
        # lettura incrementale: da next in poi non c'è nulla di nuovo
        again = client.get(f"/api/log?since={log['next']}").get_json()
        assert again["lines"] == []

    def test_import_partitura_reale_posiziona_i_valori(self):
        """Le partiture del repo devono rientrare nei controlli giusti:
        envelope come liste, blocchi annidati sui percorsi dot."""
        app = create_app(output_dir=None)
        client = app.test_client()
        text = open("tests/fixtures/stream-crescente.yaml", encoding="utf-8").read()
        state = client.post("/api/import", data=text,
                            content_type="text/yaml").get_json()
        assert state["global"]["seed"]["value"] == 20260703
        params = state["layers"][0]["params"]
        assert params["duration"]["value"] == 20.0
        assert params["fragment.duration"]["value"] == [[0, 0.005], [20, 0.06]]
        assert params["pointer.start_range"]["value"] == 0.5
        assert params["provision.search.license"]["value"] == "cc"

    def test_api_params_espone_il_catalogo(self, tmp_path):
        """La GUI si genera dal catalogo del motore: bounds veri, enum
        veri, niente doppioni JavaScript."""
        app = create_app(output_dir=tmp_path / "out")
        cat = app.test_client().get("/api/params").get_json()
        assert set(cat) == {"global", "layer", "provision"}
        fill = next(e for e in cat["layer"] if e["path"] == "fill_factor")
        assert fill["max"] == 50.0          # bound VERO del motore
        assert fill["ui"]["max"] == 5       # range comodo per lo slider
        sel = next(e for e in cat["layer"] if e["path"] == "selection.strategy")
        assert "rotation" in sel["options"]

    def test_root_serve_la_pagina(self, tmp_path):
        app = create_app(output_dir=tmp_path / "out")
        response = app.test_client().get("/")
        assert response.status_code == 200
        assert b"audiolayers" in response.data.lower()
