"""Scenario runner for repeatable microgrid experiments."""

from __future__ import annotations

from dataclasses import asdict
from math import pi, sin

from .controller import MicrogridController, PowerState


def day_profile(steps: int = 96) -> list[dict[str, float | bool | str]]:
    if steps < 4:
        raise ValueError("at least four steps are required")
    interval_hours = 24.0 / steps
    controller = MicrogridController()
    soc = 0.55
    rows: list[dict[str, float | bool | str]] = []
    for step in range(steps):
        hour = step * interval_hours
        daylight = max(0.0, sin(pi * (hour - 6.0) / 12.0))
        solar_kw = 9.0 * daylight
        morning_peak = 2.5 if 7 <= hour < 9 else 0.0
        evening_peak = 5.0 if 17 <= hour < 21 else 0.0
        load_kw = 3.0 + morning_peak + evening_peak
        grid_available = not 18.0 <= hour < 19.0
        state = PowerState(solar_kw, load_kw, soc, grid_available, interval_hours)
        decision = controller.dispatch(state)
        rows.append(
            {
                "hour": round(hour, 2),
                **asdict(state),
                **asdict(decision),
                "balance_error_kw": decision.balance_error_kw,
            }
        )
        soc = decision.next_soc
    return rows
