"""Unit — score_builder della GUI web: stato dei controlli ↔ partitura.

Ogni controllo è {enabled, value}; disattivato → la chiave non compare
nello YAML e il motore usa i suoi default. I percorsi sono in dot
notation (fragment.duration, pointer.start, selection.strategy).
"""

from audiolayers_gui.score_builder import build_score, parse_score


def stato_minimo():
    return {
        "global": {
            "seed": {"enabled": True, "value": 42},
            "master_volume": {"enabled": False, "value": -6.0},
        },
        "layers": [{
            "layer_id": "uno",
            "pool": "audio/pool/",
            "params": {
                "duration": {"enabled": True, "value": 20.0},
                "fragment.duration": {"enabled": True, "value": 0.05},
                "volume": {"enabled": False, "value": -3.0},
            },
        }],
    }


class TestBuildScore:
    def test_parametri_attivi_entrano_disattivi_spariscono(self):
        score = build_score(stato_minimo())
        assert score["seed"] == 42
        assert "master_volume" not in score
        layer = score["layers"][0]
        assert layer["layer_id"] == "uno"
        assert layer["pool"] == "audio/pool/"
        assert layer["duration"] == 20.0
        assert layer["fragment"]["duration"] == 0.05
        assert "volume" not in layer

    def test_envelope_breakpoint_passa_come_lista(self):
        stato = stato_minimo()
        stato["layers"][0]["params"]["fragment.duration"]["value"] = \
            [[0, 0.01], [20, 0.5]]
        layer = build_score(stato)["layers"][0]
        assert layer["fragment"]["duration"] == [[0, 0.01], [20, 0.5]]


class TestProvision:
    def test_blocco_digger_entra_nella_partitura(self):
        stato = stato_minimo()
        stato["layers"][0]["params"].update({
            "provision.search.license": {"enabled": True, "value": "cc"},
            "provision.search.collection": {"enabled": True,
                                            "value": ["field-recordings"]},
            "provision.files.prefer": {"enabled": True,
                                       "value": [["Flac", "WAVE"]]},
        })
        layer = build_score(stato)["layers"][0]
        assert layer["provision"]["search"]["license"] == "cc"
        assert layer["provision"]["search"]["collection"] == ["field-recordings"]
        assert layer["provision"]["files"]["prefer"] == [["Flac", "WAVE"]]

    def test_round_trip_del_blocco_digger(self):
        stato = stato_minimo()
        stato["layers"][0]["params"]["provision.search.license"] = \
            {"enabled": True, "value": "cc"}
        params = parse_score(build_score(stato))["layers"][0]["params"]
        assert params["provision.search.license"]["value"] == "cc"


class TestModalita:
    def test_rhythm_solo_e_time_mode_passano(self):
        stato = stato_minimo()
        del stato["layers"][0]["params"]["fragment.duration"]
        stato["layers"][0]["params"].update({
            "fragment.rhythm.bpm": {"enabled": True, "value": [[0, 90], [20, 140]]},
            "fragment.rhythm.pattern": {"enabled": True, "value": [0.25, 0.125]},
            "solo": {"enabled": True, "value": True},
            "time_mode": {"enabled": True, "value": "normalized"},
        })
        layer = build_score(stato)["layers"][0]
        assert layer["fragment"]["rhythm"]["bpm"] == [[0, 90], [20, 140]]
        assert layer["fragment"]["rhythm"]["pattern"] == [0.25, 0.125]
        assert layer["solo"] is True
        assert layer["time_mode"] == "normalized"
        assert "duration" not in layer["fragment"]  # mutua esclusione

    def test_round_trip_rhythm(self):
        stato = stato_minimo()
        del stato["layers"][0]["params"]["fragment.duration"]
        stato["layers"][0]["params"]["fragment.rhythm.pattern"] = \
            {"enabled": True, "value": [0.25, 0.125]}
        params = parse_score(build_score(stato))["layers"][0]["params"]
        assert params["fragment.rhythm.pattern"]["value"] == [0.25, 0.125]


class TestDiggerGlobaleNelBuilder:
    def test_provision_globale_annidato_e_round_trip(self):
        stato = stato_minimo()
        stato["global"].update({
            "provision.mode": {"enabled": True, "value": "fixed"},
            "provision.count": {"enabled": True, "value": 15},
            "provision.search.license": {"enabled": True, "value": "cc"},
        })
        score = build_score(stato)
        assert score["provision"]["mode"] == "fixed"
        assert score["provision"]["count"] == 15
        assert score["provision"]["search"]["license"] == "cc"
        back = parse_score(score)
        assert back["global"]["provision.mode"]["value"] == "fixed"
        assert back["global"]["seed"]["value"] == 42


class TestParseScore:
    def test_round_trip_partitura_torna_nei_controlli(self):
        score = build_score(stato_minimo())
        stato = parse_score(score)
        assert stato["global"]["seed"] == {"enabled": True, "value": 42}
        params = stato["layers"][0]["params"]
        assert params["duration"] == {"enabled": True, "value": 20.0}
        assert params["fragment.duration"]["value"] == 0.05
        assert "volume" not in params or not params["volume"]["enabled"]


class TestCasiLimite:
    def test_stato_vuoto_produce_partitura_con_soli_layers(self):
        assert build_score({}) == {"layers": []}

    def test_partitura_senza_layers_torna_stato_senza_layers(self):
        stato = parse_score({"seed": 1})
        assert stato["layers"] == []
        assert stato["global"]["seed"] == {"enabled": True, "value": 1}

    def test_layer_senza_id_e_pool_prende_i_default(self):
        stato = parse_score({"layers": [{"duration": 3.0}]})
        layer = stato["layers"][0]
        assert layer["layer_id"] == "layer"
        assert layer["pool"] == "audio/pool/"
        assert layer["params"]["duration"] == {"enabled": True, "value": 3.0}

    def test_percorso_a_tre_livelli_annida_e_torna(self):
        stato = stato_minimo()
        stato["layers"][0]["params"]["fragment.rhythm.bpm"] = \
            {"enabled": True, "value": 90}
        layer = build_score(stato)["layers"][0]
        assert layer["fragment"]["rhythm"]["bpm"] == 90
        back = parse_score({"layers": [layer]})
        assert back["layers"][0]["params"]["fragment.rhythm.bpm"]["value"] == 90

    def test_build_parse_build_e_stabile(self):
        """La partitura è un punto fisso: build(parse(score)) == score."""
        score = build_score(stato_minimo())
        assert build_score(parse_score(score)) == score

    def test_envelope_resta_foglia_non_viene_appiattito(self):
        """Le breakpoint list sono valori, non blocchi da percorrere."""
        score = {"layers": [{"layer_id": "a", "pool": "p/",
                             "fill_factor": [[0, 0.5], [10, 2.0]]}]}
        params = parse_score(score)["layers"][0]["params"]
        assert params["fill_factor"]["value"] == [[0, 0.5], [10, 2.0]]
