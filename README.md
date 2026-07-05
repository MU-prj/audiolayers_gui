# audiolayers_gui

GUI web di [audiolayers](https://github.com/MU-prj/audiolayers): Flask
minimale + JavaScript vanilla sopra il motore di sintesi, che arriva come
pacchetto Python installato. Controlli on/off per ogni parametro (off =
default del motore), editor breakpoint per gli envelope, render come job
asincrono con player integrato e download, provisioning da Internet
Archive (`dig`) con un toggle, export/import YAML round-trip con la CLI
del motore.

La GUI si genera dal catalogo `/api/params` esposto dal motore: bounds,
enum e default hanno una sola fonte (`audiolayers.parameters.catalog`),
nessuna tabella duplicata in JavaScript.

## Avvio

```bash
make gui            # oppure: python -m audiolayers_gui [--port 8000]
```

poi apri http://localhost:8000.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # POSIX
# .venv/Scripts/pip install -r requirements.txt   # Windows
```

Il motore è dichiarato in `requirements.txt` come dipendenza git
(`audiolayers @ git+https://github.com/MU-prj/audiolayers@main`). Per
sviluppare motore e GUI insieme, installa il motore in modalità
editable dal checkout locale:

```bash
.venv/bin/pip install -e ../audiolayers
```

## Architettura

- `audiolayers_gui/app.py` — factory `create_app` (dipendenze
  iniettabili: cartella output, client Internet Archive) con le route
  `/api/render`, `/api/jobs/…`, `/api/params`, `/api/yaml`, `/api/import`,
  `/api/log`;
- `audiolayers_gui/jobs.py` — job in background (submit → polling →
  risultato), il runner è una strategy;
- `audiolayers_gui/score_builder.py` — stato dei controlli ↔ dict
  partitura, percorsi in dot notation;
- `audiolayers_gui/static/` — pagina e logica client (vanilla JS).

Il contratto col motore è la partitura YAML più tre funzioni di
libreria: `render_score`, `provision_score`, `catalog`. La separazione è
documentata nel repo del motore
(`docs/plans/done/2026-07-05-003-engine-gui-split.md`).

## Test

```bash
make tests          # tutta la suite
make unit           # score_builder, JobManager, LogBuffer in isolamento
make integration    # le API Flask col motore vero (test client)
make e2e            # il server reale via subprocess, HTTP sul filo
```

I test integration usano il motore vero su partiture minuscole e un
client Internet Archive finto (`tests/helpers.py`): girano offline.
Gli e2e avviano `python -m audiolayers_gui` su una porta libera e
coprono il flusso completo render → polling → download e il percorso
d'errore (pool vuoto → job in errore, audio 404).

### CI

`.github/workflows/ci.yml` esegue l'intera suite (unit + integration +
e2e) a ogni push e pull request, su Python 3.11 e 3.12, con report di
coverage a branch. Il motore non è un pacchetto pip (layout `src/`,
import interni `src.*`): la CI lo clona, ne installa le dipendenze e lo
espone come `audiolayers` con un symlink `audiolayers -> engine/src`,
tenendo la root del motore su `PYTHONPATH` per gli import `src.*`. Per
motore o archivedigger privati basta impostare il secret `GH_PAT`.

## Licenza

Vedi [LICENSE](LICENSE) (CC BY-NC-ND 4.0). Il motore audiolayers è
distribuito separatamente con licenza MIT.
