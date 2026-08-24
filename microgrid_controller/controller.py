"""Constraint-aware power dispatch for a simplified behind-the-meter microgrid."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ControllerConfig:
    battery_capacity_kwh: float = 20.0
    min_soc: float = 0.15
    max_soc: float = 0.95
    max_charge_kw: float = 5.0
    max_discharge_kw: float = 5.0
    grid_import_limit_kw: float = 6.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95

    def __post_init__(self) -> None:
        numeric_values = (
            self.battery_capacity_kwh,
            self.min_soc,
            self.max_soc,
            self.max_charge_kw,
            self.max_discharge_kw,
            self.grid_import_limit_kw,
            self.charge_efficiency,
            self.discharge_efficiency,
        )
        if not all(isfinite(value) for value in numeric_values):
            raise ValueError("controller configuration values must be finite")
        if self.battery_capacity_kwh <= 0:
            raise ValueError("battery capacity must be positive")
        if not 0 <= self.min_soc < self.max_soc <= 1:
            raise ValueError("SOC limits must satisfy 0 <= min < max <= 1")
        if min(self.max_charge_kw, self.max_discharge_kw, self.grid_import_limit_kw) < 0:
            raise ValueError("power limits cannot be negative")
        if not 0 < self.charge_efficiency <= 1 or not 0 < self.discharge_efficiency <= 1:
            raise ValueError("battery efficiencies must be greater than zero and at most one")


@dataclass(frozen=True)
class PowerState:
    solar_kw: float
    load_kw: float
    battery_soc: float
    grid_available: bool = True
    interval_hours: float = 0.25


@dataclass(frozen=True)
class DispatchDecision:
    mode: str
    load_kw: float
    solar_to_load_kw: float
    battery_charge_kw: float
    battery_discharge_kw: float
    grid_import_kw: float
    grid_export_kw: float
    unserved_load_kw: float
    next_soc: float

    @property
    def balance_error_kw(self) -> float:
        supplied = self.solar_to_load_kw + self.battery_discharge_kw + self.grid_import_kw
        return round(supplied + self.unserved_load_kw - self.load_kw, 9)


class MicrogridController:
    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig()

    def dispatch(self, state: PowerState) -> DispatchDecision:
        cfg = self.config
        state_values = (
            state.solar_kw,
            state.load_kw,
            state.battery_soc,
            state.interval_hours,
        )
        if not all(isfinite(value) for value in state_values):
            raise ValueError("power-state values must be finite")
        if min(state.solar_kw, state.load_kw) < 0:
            raise ValueError("solar and load power cannot be negative")
        if not cfg.min_soc <= state.battery_soc <= cfg.max_soc:
            raise ValueError(
                "battery_soc must be within the configured minimum and maximum"
            )
        if state.interval_hours <= 0:
            raise ValueError("interval_hours must be positive")

        solar_to_load = min(state.solar_kw, state.load_kw)
        surplus = max(0.0, state.solar_kw - solar_to_load)
        deficit = max(0.0, state.load_kw - solar_to_load)

        charge_headroom_kwh = max(0.0, (cfg.max_soc - state.battery_soc) * cfg.battery_capacity_kwh)
        charge_limit_kw = charge_headroom_kwh / (state.interval_hours * cfg.charge_efficiency)
        battery_charge = min(surplus, cfg.max_charge_kw, charge_limit_kw)
        grid_export = surplus - battery_charge if state.grid_available else 0.0

        available_battery_kwh = max(
            0.0,
            (state.battery_soc - cfg.min_soc) * cfg.battery_capacity_kwh,
        )
        discharge_limit_kw = available_battery_kwh * cfg.discharge_efficiency / state.interval_hours
        if state.grid_available:
            required_discharge = max(0.0, deficit - cfg.grid_import_limit_kw)
        else:
            required_discharge = deficit
        battery_discharge = min(required_discharge, cfg.max_discharge_kw, discharge_limit_kw)

        remaining_deficit = deficit - battery_discharge
        grid_import = (
            min(remaining_deficit, cfg.grid_import_limit_kw) if state.grid_available else 0.0
        )
        unserved = max(0.0, remaining_deficit - grid_import)

        energy_change_kwh = (
            battery_charge * cfg.charge_efficiency
            - battery_discharge / cfg.discharge_efficiency
        ) * state.interval_hours
        next_soc = state.battery_soc + energy_change_kwh / cfg.battery_capacity_kwh
        next_soc = min(cfg.max_soc, max(cfg.min_soc, next_soc))

        if unserved > 0:
            mode = "load_shed"
        elif not state.grid_available:
            mode = "islanded"
        elif battery_charge > 0:
            mode = "solar_charging"
        elif battery_discharge > 0:
            mode = "peak_shaving"
        elif grid_export > 0:
            mode = "solar_export"
        else:
            mode = "grid_connected"

        return DispatchDecision(
            mode=mode,
            load_kw=round(state.load_kw, 4),
            solar_to_load_kw=round(solar_to_load, 4),
            battery_charge_kw=round(battery_charge, 4),
            battery_discharge_kw=round(battery_discharge, 4),
            grid_import_kw=round(grid_import, 4),
            grid_export_kw=round(grid_export, 4),
            unserved_load_kw=round(unserved, 4),
            next_soc=round(next_soc, 5),
        )
