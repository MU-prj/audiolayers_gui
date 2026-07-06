"""Stato dei controlli GUI ↔ partitura YAML (bidirezionale).

Ogni controllo è {enabled, value}: disattivato → la chiave non entra
nella partitura e vale il default del motore. Percorsi in dot notation
(fragment.duration, pointer.start, selection.strategy) così la GUI non
conosce la struttura annidata dello YAML.
"""


def build_score(state: dict) -> dict:
    """Costruisce il dict-partitura dai controlli attivi."""
    score: dict = {}
    for name, control in state.get("global", {}).items():
        if control.get("enabled"):
            _set_nested(score, name, control["value"])  # anche provision.*
    score["layers"] = []
    for layer_state in state.get("layers", []):
        layer = {"layer_id": layer_state["layer_id"]}
        # Pool a 3 stati (issue #3): vuoto = derivato dal motore (la
        # chiave NON si emette), "auto" o path espliciti passano.
        if layer_state.get("pool"):
            layer["pool"] = layer_state["pool"]
        for path, control in layer_state.get("params", {}).items():
            if control.get("enabled"):
                _set_nested(layer, path, control["value"])
        score["layers"].append(layer)
    return score


def parse_score(score: dict) -> dict:
    """Inverso: da una partitura (import YAML) allo stato dei controlli."""
    state = {"global": {}, "layers": []}
    for name, value in score.items():
        if name == "layers":
            continue
        if isinstance(value, dict):   # blocchi annidati (provision globale)
            for path, leaf in _walk(value, f"{name}."):
                state["global"][path] = {"enabled": True, "value": leaf}
        else:
            state["global"][name] = {"enabled": True, "value": value}
    for layer in score.get("layers", []):
        layer_state = {
            "layer_id": layer.get("layer_id", "layer"),
            # Assente = derivato dal motore: niente default fisso, o la
            # derivazione si perderebbe al prossimo build (issue #3).
            "pool": layer.get("pool", ""),
            "params": {},
        }
        for path, value in _walk(layer):
            if path in ("layer_id", "pool"):
                continue
            layer_state["params"][path] = {"enabled": True, "value": value}
        state["layers"].append(layer_state)
    return state


def _set_nested(target: dict, path: str, value) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value


def _walk(data: dict, prefix: str = ""):
    """Appiattisce il dict in coppie (percorso.dot, valore foglia)."""
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _walk(value, f"{path}.")
        else:
            yield path, value
