"""Unit — LogBuffer: il terminale della GUI.

Righe con timestamp, interfaccia file-like per redirect_stdout, lettura
incrementale via `since`, buffer circolare con indici assoluti: la GUI
fa polling senza mai perdere il conto, anche quando il buffer ruota.
"""

import re
import threading

from audiolayers_gui.app import LogBuffer


class TestAdd:
    def test_le_righe_arrivano_con_timestamp(self):
        log = LogBuffer()
        log.add("ciao")
        lines = log.since(0)["lines"]
        assert len(lines) == 1
        timestamp, line = lines[0]
        assert line == "ciao"
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", timestamp)

    def test_next_avanza_con_le_righe(self):
        log = LogBuffer()
        for i in range(3):
            log.add(f"riga {i}")
        assert log.since(0)["next"] == 3


class TestWrite:
    def test_write_spezza_le_righe_e_scarta_le_vuote(self):
        log = LogBuffer()
        log.write("prima\nseconda\n\n   \nterza")
        assert [line for _, line in log.since(0)["lines"]] == \
            ["prima", "seconda", "terza"]

    def test_flush_non_fa_nulla(self):
        LogBuffer().flush()   # deve esistere: interfaccia file-like


class TestSince:
    def test_lettura_incrementale(self):
        log = LogBuffer()
        log.add("a")
        prima = log.since(0)
        log.add("b")
        dopo = log.since(prima["next"])
        assert [line for _, line in dopo["lines"]] == ["b"]
        assert log.since(dopo["next"])["lines"] == []

    def test_rollover_mantiene_gli_indici_assoluti(self):
        log = LogBuffer(max_lines=3)
        for i in range(5):
            log.add(f"riga {i}")
        tutto = log.since(0)
        assert [line for _, line in tutto["lines"]] == \
            ["riga 2", "riga 3", "riga 4"]
        assert tutto["next"] == 5
        assert [line for _, line in log.since(4)["lines"]] == ["riga 4"]

    def test_scritture_concorrenti_non_perdono_righe(self):
        log = LogBuffer(max_lines=10000)

        def scrivi(prefisso):
            for i in range(100):
                log.add(f"{prefisso}-{i}")

        threads = [threading.Thread(target=scrivi, args=(k,))
                   for k in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert log.since(0)["next"] == 1000

    def test_lettura_incrementale_dopo_lo_scarto(self):
        """Chi aveva letto fino a next=2 riprende senza duplicati né buchi
        anche se nel frattempo il buffer ha scartato righe vecchie."""
        log = LogBuffer(max_lines=2)
        for parola in ("a", "b", "c", "d"):
            log.add(parola)
        dopo = log.since(2)
        assert [line for _, line in dopo["lines"]] == ["c", "d"]
        assert dopo["next"] == 4
