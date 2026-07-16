"""Integration — API della GUI: render asincrono end-to-end, YAML I/O.

Motore vero su partiture minuscole; Internet Archive finto (il client è
iniettabile nella factory, come in CLI e archivedigger).
"""

import time

import yaml

from audiolayers_gui.app import create_app
from tests.helpers import FakeArchiveClient, make_state, write_wav


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

    def test_render_con_pattern_repeat_casuale(self, tmp_path):
        """Issue #10: una voce dict {value, repeat} nel pattern ritmico
        attraversa GUI → YAML → motore e il render va a buon fine."""
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()

        state = make_state(pool)
        params = state["layers"][0]["params"]
        del params["fragment.duration"]
        params["fragment.rhythm.bpm"] = {"enabled": True, "value": 240}
        params["fragment.rhythm.pattern"] = {
            "enabled": True,
            "value": [0.25, {"value": 0.125, "repeat": "2-4"}],
        }
        job_id = client.post("/api/render",
                             json={"state": state}).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "done"

    def test_yaml_round_trip_pattern_repeat(self, tmp_path):
        """Le voci dict del pattern sopravvivono a export e import:
        la lista resta una foglia unica, niente appiattimento."""
        app = create_app(output_dir=tmp_path / "out")
        client = app.test_client()
        state = make_state(tmp_path / "pool")
        state["layers"][0]["params"]["fragment.rhythm.pattern"] = {
            "enabled": True,
            "value": [0.5, {"value": 0.125, "repeat": [2, 7]}],
        }

        exported = client.post("/api/yaml", json={"state": state}).data.decode()
        pattern = yaml.safe_load(exported)["layers"][0]["fragment"]["rhythm"]["pattern"]
        assert pattern == [0.5, {"value": 0.125, "repeat": [2, 7]}]

        imported = client.post("/api/import", data=exported,
                               content_type="text/yaml").get_json()
        voices = imported["layers"][0]["params"]["fragment.rhythm.pattern"]["value"]
        assert voices == [0.5, {"value": 0.125, "repeat": [2, 7]}]

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


class TestContrattoRender:
    def test_la_partitura_viene_scritta_nella_cartella_output(self, tmp_path):
        """Il render passa dal file: score.yaml è ispezionabile a mano."""
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        out = tmp_path / "out"
        app = create_app(output_dir=out)
        client = app.test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(pool)}).get_json()["job_id"]
        wait_done(client, job_id)

        score = yaml.safe_load((out / "score.yaml").read_text(encoding="utf-8"))
        assert score["seed"] == 7
        assert score["layers"][0]["fragment"]["duration"] == 0.25

    def test_il_wav_prodotto_e_leggibile_stereo_48k(self, tmp_path):
        import io

        import soundfile as sf

        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        client = create_app(output_dir=tmp_path / "out").test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(pool)}).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "done"

        audio = client.get(f"/api/jobs/{job_id}/audio")
        data, sample_rate = sf.read(io.BytesIO(audio.data))
        assert sample_rate == 48000          # default del motore
        assert data.ndim == 2 and data.shape[1] == 2
        assert 0.9 <= len(data) / sample_rate <= 2.5   # ~durata del layer

    def test_render_multilayer(self, tmp_path):
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        state = make_state(pool)
        secondo = {"layer_id": "due", "pool": str(pool), "params": {
            "duration": {"enabled": True, "value": 0.5},
            "fragment.duration": {"enabled": True, "value": 0.25},
        }}
        state["layers"].append(secondo)
        client = create_app(output_dir=tmp_path / "out").test_client()
        job_id = client.post("/api/render",
                             json={"state": state}).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "done"
        assert client.get(f"/api/jobs/{job_id}/audio").data[:4] == b"RIFF"

    def test_due_render_in_sequenza_hanno_job_distinti(self, tmp_path):
        pool = tmp_path / "pool"
        pool.mkdir()
        write_wav(pool / "a.wav", 1.0)
        client = create_app(output_dir=tmp_path / "out").test_client()
        primo = client.post("/api/render",
                            json={"state": make_state(pool)}).get_json()["job_id"]
        secondo = client.post("/api/render",
                              json={"state": make_state(pool)}).get_json()["job_id"]
        assert primo != secondo
        assert wait_done(client, primo)["state"] == "done"
        assert wait_done(client, secondo)["state"] == "done"
        assert client.get(f"/api/jobs/{secondo}/audio").status_code == 200


class TestTerminale:
    def test_il_dig_scrive_le_sue_fasi_nel_terminale(self, tmp_path):
        pool = tmp_path / "pool"
        client = create_app(output_dir=tmp_path / "out",
                            archive_client=FakeArchiveClient()).test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(pool), "dig": True}
                             ).get_json()["job_id"]
        wait_done(client, job_id)
        text = "\n".join(line for _, line in
                         client.get("/api/log").get_json()["lines"])
        assert "dig: analisi partitura" in text
        assert "dig: completato" in text

    def test_l_errore_del_render_finisce_nel_terminale(self, tmp_path):
        client = create_app(output_dir=tmp_path / "out").test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(tmp_path / "vuoto")}
                             ).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "error"
        text = "\n".join(line for _, line in
                         client.get("/api/log").get_json()["lines"])
        assert "ERRORE" in text


class TestContorniApi:
    def test_job_sconosciuto_via_api(self, tmp_path):
        client = create_app(output_dir=tmp_path / "out").test_client()
        assert client.get("/api/jobs/boh").get_json()["state"] == "unknown"

    def test_audio_di_un_job_sconosciuto_e_404_non_500(self, tmp_path):
        """L'endpoint audio non deve schiantarsi su un id inesistente:
        404 pulito, coerente con lo stato «unknown»."""
        client = create_app(output_dir=tmp_path / "out").test_client()
        assert client.get("/api/jobs/boh/audio").status_code == 404

    def test_audio_di_un_job_fallito_e_404(self, tmp_path):
        """Un render fallito non ha wav da scaricare: 404, non un 500 con
        traceback (il job esiste ma result è None)."""
        client = create_app(output_dir=tmp_path / "out").test_client()
        job_id = client.post("/api/render",
                             json={"state": make_state(tmp_path / "vuoto")}
                             ).get_json()["job_id"]
        assert wait_done(client, job_id)["state"] == "error"
        assert client.get(f"/api/jobs/{job_id}/audio").status_code == 404

    def test_gli_asset_statici_sono_serviti(self, tmp_path):
        client = create_app(output_dir=tmp_path / "out").test_client()
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200

    def test_yaml_rotto_in_import_non_ammazza_il_server(self, tmp_path):
        client = create_app(output_dir=tmp_path / "out").test_client()
        risposta = client.post("/api/import", data="a: [1, 2",
                               content_type="text/yaml")
        assert risposta.status_code == 500
        assert client.get("/api/params").status_code == 200   # il server vive


class TestContrattoCatalogo:
    """Ciò su cui la GUI conta per generarsi da /api/params."""

    def test_ogni_voce_ha_i_campi_minimi(self, tmp_path):
        cat = create_app(output_dir=tmp_path / "out") \
            .test_client().get("/api/params").get_json()
        for voci in cat.values():
            for voce in voci:
                assert {"path", "label", "kind", "default", "info"} <= set(voce), \
                    f"voce incompleta: {voce.get('path')}"

    def test_i_range_ui_sono_ordinati_e_sotto_il_tetto(self, tmp_path):
        cat = create_app(output_dir=tmp_path / "out") \
            .test_client().get("/api/params").get_json()
        for voci in cat.values():
            for voce in voci:
                if "ui" not in voce:
                    continue
                assert voce["ui"]["min"] < voce["ui"]["max"], voce["path"]
                if "max" in voce:
                    assert voce["ui"]["max"] <= voce["max"], voce["path"]

    def test_le_select_dichiarano_le_opzioni(self, tmp_path):
        cat = create_app(output_dir=tmp_path / "out") \
            .test_client().get("/api/params").get_json()
        for voci in cat.values():
            for voce in voci:
                if voce["kind"] == "select":
                    assert voce["options"], voce["path"]
                    assert voce["default"] in voce["options"], voce["path"]
