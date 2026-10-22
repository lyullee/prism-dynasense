"""SI-only input contracts; missing or invalid inputs never become zero."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Scenario(Contract):
    name: str = Field(default="가압 수소 누출·점화·차단", min_length=1, max_length=160)
    fluid: Literal["Hydrogen"] = "Hydrogen"
    initial_pressure_pa: float = Field(default=2_000_000.0, gt=101_325.0, le=5_000_000.0)
    temperature_k: float = Field(default=293.15, ge=250.0, le=350.0)
    upstream_volume_m3: float = Field(default=0.6, gt=0.0, le=1000.0)
    isolated_volume_m3: float = Field(default=0.025, gt=0.0, le=100.0)
    hole_diameter_m: float = Field(default=0.004, gt=0.0, le=0.05)
    discharge_coefficient: float = Field(default=0.8, gt=0.0, le=1.0)
    isolation_time_s: float = Field(default=10.0, ge=0.0)
    ignition_time_s: float = Field(default=1.0, ge=0.0)
    receptor_distance_m: float = Field(default=1.0, ge=0.5, le=1000.0)
    radiant_fraction: float = Field(default=0.1, gt=0.0, le=0.4)
    atmospheric_transmissivity: float = Field(default=0.9, gt=0.0, le=1.0)
    horizon_s: float = Field(default=40.0, gt=0.0, le=3600.0)
    time_step_s: float = Field(default=0.5, gt=0.0)

    @model_validator(mode="after")
    def validate_clock(self):
        if self.time_step_s > self.horizon_s:
            raise ValueError("time_step_s must not exceed horizon_s")
        if self.horizon_s / self.time_step_s > 20_000:
            raise ValueError("at most 20,000 output intervals are supported")
        return self


VARIABLE_LABELS = {
    "initial_pressure_pa": "초기 압력",
    "upstream_volume_m3": "상류 용적", "isolated_volume_m3": "격리구간 용적",
    "hole_diameter_m": "누출구 직경", "discharge_coefficient": "유출계수",
    "isolation_time_s": "차단 완료시간", "ignition_time_s": "점화시각",
    "receptor_distance_m": "평가 지점 거리", "radiant_fraction": "복사분율",
    "atmospheric_transmissivity": "대기 투과율", "temperature_k": "가스 온도",
}


class Variable(Contract):
    name: str
    lower: float
    upper: float

    @model_validator(mode="after")
    def check_range(self):
        if self.name not in VARIABLE_LABELS:
            raise ValueError(f"unsupported sensitivity variable: {self.name}")
        if not self.lower < self.upper:
            raise ValueError("lower must be less than upper")
        return self


class Study(Contract):
    schema_version: Literal["1"] = "1"
    scenario: Scenario = Field(default_factory=Scenario)
    variables: list[Variable] = Field(default_factory=lambda: [
        Variable(name="hole_diameter_m", lower=0.002, upper=0.006),
        Variable(name="isolated_volume_m3", lower=0.01, upper=0.05),
        Variable(name="isolation_time_s", lower=4.0, upper=16.0),
        Variable(name="receptor_distance_m", lower=0.75, upper=2.5),
        Variable(name="radiant_fraction", lower=0.05, upper=0.15),
    ])
    seed: int = Field(default=20261022, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_design(self):
        names = [v.name for v in self.variables]
        if not 1 <= len(names) <= 12 or len(set(names)) != len(names):
            raise ValueError("one to twelve unique variables are required")
        for var in self.variables:
            baseline = getattr(self.scenario, var.name)
            if not var.lower <= baseline <= var.upper:
                raise ValueError(f"baseline for {var.name} is outside its range")
            for bound in (var.lower, var.upper):
                Scenario.model_validate(self.scenario.model_dump() | {var.name: bound})
        return self

    def with_values(self, values) -> Scenario:
        if len(values) != len(self.variables):
            raise ValueError("sample dimension mismatch")
        updates = {}
        for variable, value in zip(self.variables, values):
            value = float(value)
            if not math.isfinite(value) or not variable.lower <= value <= variable.upper:
                raise ValueError(f"sample outside the declared range: {variable.name}")
            updates[variable.name] = value
        return Scenario.model_validate(self.scenario.model_dump() | updates)

