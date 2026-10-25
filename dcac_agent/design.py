from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields, replace


@dataclass(frozen=True)
class DesignSpec:
    input_voltage: float = 380.0
    output_voltage: float = 220.0
    output_power: float = 500.0
    output_frequency: float = 50.0
    switching_frequency: float = 20000.0
    inductance: float = 0.002
    capacitance: float = 4.7e-6
    winding_resistance: float = 0.25
    stop_time: float = 0.24
    load_step: bool = False
    load_step_time: float = 0.12
    load_final_ratio: float = 0.5

    def validate(self) -> "DesignSpec":
        bounds = {
            "input_voltage": (10, 1000), "output_voltage": (1, 700),
            "output_power": (5, 10000), "output_frequency": (40, 100),
            "switching_frequency": (5000, 50000), "inductance": (0.0001, 0.05),
            "capacitance": (1e-7, 0.0001), "winding_resistance": (0, 10),
            "stop_time": (0.16, 0.5), "load_step_time": (0.04, 0.35),
            "load_final_ratio": (0.1, 2.0),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} 必须是 {low:g} 至 {high:g} 之间的有限数值。")
        if not isinstance(self.load_step, bool):
            raise ValueError("load_step 必须为布尔值。")
        if math.sqrt(2) * self.output_voltage / self.input_voltage > 0.95:
            raise ValueError("所需调制度超过0.95；请提高直流输入或降低交流输出。当前模板不含升压级。")
        if self.switching_frequency < 50 * self.output_frequency:
            raise ValueError("开关频率相对输出频率过低。")
        start = self.stop_time - 4 / self.output_frequency
        if start < 0.06:
            raise ValueError("仿真时间不足以提取启动后4个完整稳态周期。")
        if self.load_step and self.load_step_time > start - 0.02:
            raise ValueError("负载突变需在稳态分析窗口前至少20 ms发生，请提前突变时间或延长仿真。")
        if self.load_step and self.load_step_time < 0.04 + 2 / self.output_frequency:
            raise ValueError("负载突变需在40 ms软启动结束后至少保留两个基波周期。")
        return self

    def updated(self, updates: dict) -> "DesignSpec":
        allowed = {f.name for f in fields(self)}
        unknown = set(updates) - allowed
        if unknown:
            raise ValueError("未知设计参数：" + ", ".join(sorted(unknown)))
        return replace(self, **updates).validate()

    def to_dict(self) -> dict:
        return asdict(self)

    def derived(self) -> dict:
        resistance = self.output_voltage ** 2 / self.output_power
        omega = 2 * math.pi * self.output_frequency
        resonant_frequency = 1 / (2 * math.pi * math.sqrt(self.inductance * self.capacitance))
        output_current = self.output_power / self.output_voltage
        capacitor_current = omega * self.capacitance * self.output_voltage
        estimated_inductor_current = math.hypot(output_current, capacitor_current)
        return {
            "load_resistance": resistance,
            "output_current": output_current,
            "modulation_index": math.sqrt(2) * self.output_voltage / self.input_voltage,
            "resonant_frequency": resonant_frequency,
            "sample_time": 1 / (self.switching_frequency * 100),
            "fine_sample_time": 1 / (self.switching_frequency * 200),
            "final_load_resistance": resistance / self.load_final_ratio if self.load_step else resistance,
            "switching_to_resonance_ratio": self.switching_frequency / resonant_frequency,
            "resonance_to_fundamental_ratio": resonant_frequency / self.output_frequency,
            "capacitor_current_estimate": capacitor_current,
            "inductor_current_estimate": estimated_inductor_current,
            "winding_loss_estimate": estimated_inductor_current ** 2 * self.winding_resistance,
            "loss_estimate_scope": "constant winding resistance only; not total inverter loss or efficiency",
        }

    def engineering_review(self) -> dict:
        """Analytical screening only; it never substitutes for a simulated result."""
        d = self.derived()
        checks = {
            "modulation_margin": d["modulation_index"] <= 0.95,
            "resonance_above_fundamental": d["resonance_to_fundamental_ratio"] >= 10,
            "resonance_below_switching": d["switching_to_resonance_ratio"] >= 8,
            "analysis_window_after_soft_start": self.stop_time - 4 / self.output_frequency >= 0.06,
        }
        notes = []
        if not checks["resonance_above_fundamental"]:
            notes.append("LC resonance is less than ten times the fundamental frequency.")
        if not checks["resonance_below_switching"]:
            notes.append("Switching frequency is less than eight times the LC resonance.")
        notes.extend([
            "Inductor-current and winding-loss values are sinusoidal analytical estimates, not simulation measurements.",
            "The 0.25 ohm default winding resistance has no material, geometry, frequency, or temperature provenance yet.",
        ])
        return {"checks": checks, "notes": notes}


NUM = r"([0-9]+(?:\.[0-9]+)?)"


def extract_parameters(text: str) -> dict:
    """Small, explicit rule parser. This mode is labelled as rules, never LLM."""
    changes = {}
    patterns = {
        "input_voltage": [rf"(?:输入(?:电压)?|直流(?:输入|母线)?|vin)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*v", rf"{NUM}\s*v\s*(?:直流输入|输入)"],
        "output_voltage": [rf"(?:输出(?:电压)?|交流(?:输出)?|vout)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*v", rf"{NUM}\s*v\s*(?:交流输出|输出)"],
        "output_power": [rf"(?:功率|额定功率|负载功率)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*(kw|w|千瓦|瓦)", rf"{NUM}\s*(kw|w|千瓦|瓦)"],
        "switching_frequency": [rf"(?:开关频率|载波频率|fsw)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*(khz|hz)", rf"{NUM}\s*(khz)"],
        "output_frequency": [rf"(?:输出频率|基波频率|频率)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*(hz)", rf"(?<![\d.]){NUM}\s*(hz)"],
        "inductance": [rf"(?:电感|inductance|\bL)\s*(?:量|为|是|改为|设为|=|：|:)?\s*{NUM}\s*(mh|uh|μh|µh|h)"],
        "capacitance": [rf"(?:电容|capacitance|\bC)\s*(?:量|为|是|改为|设为|=|：|:)?\s*{NUM}\s*(uf|μf|µf|nf|mf|f)"],
        "stop_time": [rf"(?:仿真时间|仿真时长)\s*(?:为|改为|设为|=|：|:)?\s*{NUM}\s*(ms|s|秒)"],
    }
    # Parse explicitly qualified values first; bare 'Hz' must not reuse a switching-frequency span.
    source = text.lower().replace("伏", "v").replace("赫兹", "hz")
    for key, options in patterns.items():
        candidate = source
        if key == "output_frequency":
            candidate = re.sub(rf"(?:开关频率|载波频率|fsw)\s*(?:为|是|改为|设为|=|：|:)?\s*{NUM}\s*(?:khz|hz)", "", source)
        for pattern in options:
            match = re.search(pattern, candidate, re.I)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower() if len(match.groups()) > 1 else ""
                factor = {"kw": 1e3, "千瓦": 1e3, "khz": 1e3, "mh": 1e-3, "uh": 1e-6,
                          "μh": 1e-6, "µh": 1e-6, "uf": 1e-6, "μf": 1e-6, "µf": 1e-6,
                          "nf": 1e-9, "mf": 1e-3, "ms": 1e-3}.get(unit, 1)
                changes[key] = value * factor
                break
    if re.search(r"取消负载突变|关闭负载突变|恒定负载", source):
        changes["load_step"] = False
    elif re.search(r"负载突变|负载阶跃|半载", source):
        changes["load_step"] = True
    return changes
