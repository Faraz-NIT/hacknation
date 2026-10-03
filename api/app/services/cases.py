"""Case engine: scenario fixture + live public data -> one frozen case snapshot."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..models import Alternative, Case
from . import live

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASE_FOR_MODE = {"expert": "case_A", "trainee": "case_B"}


def load_fixture(case_id: str) -> Case:
    path = FIXTURES / f"{case_id}.json"
    if not path.exists():
        raise KeyError(case_id)
    return Case.model_validate(json.loads(path.read_text()))


def build_case(case_id: str, use_live: bool = True) -> Case:
    case = load_fixture(case_id)
    case.provenance = {"alternatives": "scenario", "flight_status": "scenario", "weather": "off", "market": "off"}
    if not use_live or os.environ.get("SKYMENTOR_OFFLINE") == "1":
        return case

    airports = [case.origin, case.destination] + [a.hub for a in case.alternatives if a.hub in live.AIRPORTS]
    airports = list(dict.fromkeys(airports))

    with ThreadPoolExecutor(max_workers=8) as pool:
        status_f = pool.submit(live.get_flight_status, case.flight.number)
        market_f = pool.submit(live.search_alternatives, case.origin, case.destination)
        weather_fs = {iata: pool.submit(live.get_weather, iata) for iata in airports}

        status, status_label = status_f.result()
        if status:
            # Keep the scenario's disruption (that is what the expert is solving);
            # surface the real-world status as provenance-labelled context.
            case.flight.source = status_label
            case.provenance["flight_status"] = status_label
            case.provenance["live_flight_status"] = f"{status.get('status')} (delay {status.get('delay_min') or 0} min)"

        labels = set()
        for iata, fut in weather_fs.items():
            data, label = fut.result()
            if data:
                case.weather[iata] = {**data, "source": label}
                labels.add(label.split(" ")[0])
        case.provenance["weather"] = "live" if labels == {"live"} else (", ".join(sorted(labels)) or "unavailable")

        market, market_label = market_f.result()
        case.provenance["market"] = market_label
        if market:
            case.market = market
            if os.environ.get("USE_LIVE_ALTERNATIVES") == "1":
                case.alternatives = [Alternative.model_validate(m) for m in market]
                case.provenance["alternatives"] = market_label
    return case
