"""
Deterministic Numerical Checks & Data Validation Engine for Smart BMS
Performs strict, rule-based numerical evaluations, physical trend derivations,
and data quality auditing against verified battery specifications.

STRICT MANDATES:
1. Do not train or add a separate machine-learning prediction model.
2. Do not claim that a normal voltage alone proves the battery is healthy.
3. Do not fabricate SOC, SOH, RUL, or failure probabilities.
4. Distinguish ambient temperature (DHT11) from internal cell core temperature.
5. If chemistry/specs are unverified or data is missing, classify as INSUFFICIENT DATA.
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from battery_config import BatterySpecification, get_active_battery_spec


class DataValidationResult(BaseModel):
    is_valid: bool = Field(..., description="Whether reading is complete and fresh")
    is_stale: bool = Field(False, description="Whether packet age exceeds freshness threshold")
    age_seconds: Optional[float] = Field(None, description="Age of latest packet in seconds")
    missing_fields: List[str] = Field(default_factory=list, description="Fields that were null or undefined")
    inconsistencies: List[str] = Field(default_factory=list, description="Physics inconsistency flags e.g. P != V*I")
    data_quality_warnings: List[str] = Field(default_factory=list, description="Human-readable data quality notices")


class NumericalTrends(BaseModel):
    temperature_rise_rate_c_per_min: Optional[float] = Field(None, description="dT/dt in degrees Celsius per minute")
    voltage_sag_v: Optional[float] = Field(None, description="Delta V (max - min) in observed window")
    estimated_internal_resistance_mohm: Optional[float] = Field(None, description="Estimated IR = Delta V / Delta I (mOhm)")
    current_rms_a: Optional[float] = Field(None, description="Current RMS in Amps")
    current_std_dev_a: Optional[float] = Field(None, description="Current standard deviation in Amps")
    max_current_a: Optional[float] = Field(None, description="Peak current in observed window")
    ambient_relative_humidity_pct: Optional[float] = Field(None, description="DHT11 ambient relative humidity (%)")
    dew_point_c: Optional[float] = Field(None, description="Calculated dew point for condensation risk (°C)")


class ConditionAssessment(BaseModel):
    condition: str = Field(..., description="Condition: NORMAL | WARNING | CRITICAL | INSUFFICIENT DATA")
    condition_status: str = Field(..., description="Detailed status: Excellent | Good | Normal | Warning | Danger | Insufficient Data")
    battery_condition_score: Optional[float] = Field(None, description="Documented condition score 0-100%, or None if Insufficient Data")
    battery_condition_breakdown: Optional[Dict[str, Any]] = Field(None, description="Transparent deduction breakdown for condition score")
    soc_estimate: Dict[str, Any] = Field(..., description="Estimated charge (SOC) with display text and basis")
    soh_estimate: Dict[str, Any] = Field(..., description="State of health (SOH) - strictly unavailable from voltage alone")
    primary_reason: str = Field(..., description="Clear explanation of the determination")
    active_warnings: List[str] = Field(default_factory=list, description="List of active warning flags")
    active_critical_flags: List[str] = Field(default_factory=list, description="List of active critical flags")
    specification_status: str = Field(..., description="UNVERIFIED | VERIFIED")
    data_validation: DataValidationResult
    numerical_trends: NumericalTrends
    verified_limits: Dict[str, Any]
    ambient_vs_cell_note: str = Field(..., description="Clarification regarding DHT11 air vs cell core temp")
    health_disclaimer: str = Field(..., description="Mandatory disclaimer regarding voltage vs overall health")


class DeterministicBatteryEvaluator:
    """
    Evaluates real sensor readings using deterministic physics checks,
    numerical trend derivatives, and verified battery specifications.
    """

    STALE_DATA_THRESHOLD_SECONDS = 45.0

    @classmethod
    def validate_telemetry(cls, telemetry: Dict[str, Any]) -> DataValidationResult:
        if not telemetry:
            return DataValidationResult(
                is_valid=False,
                is_stale=True,
                missing_fields=["voltage", "current", "power", "temperature"],
                data_quality_warnings=["No telemetry received from Firebase Realtime Database."]
            )

        missing = []
        warnings = []
        inconsistencies = []

        v = telemetry.get("voltage")
        c = telemetry.get("current")
        p = telemetry.get("power")
        t = telemetry.get("temperature")
        raw_ts = telemetry.get("rawTimestamp") or telemetry.get("updatedAt")

        # Required fields check
        if v is None: missing.append("voltage (INA219)")
        if c is None: missing.append("current (INA219)")
        if t is None: missing.append("temperature (DHT11)")

        # Freshness check
        now_ms = time.time() * 1000
        age_sec = 0.0
        is_stale = False

        if raw_ts:
            try:
                raw_val = float(raw_ts)
                if raw_val < 1e11:  # epoch seconds converted to ms
                    raw_val *= 1000
                age_sec = max(0.0, (now_ms - raw_val) / 1000.0)
            except (ValueError, TypeError):
                age_sec = 0.0
        else:
            age_sec = 0.0

        if age_sec > cls.STALE_DATA_THRESHOLD_SECONDS:
            is_stale = True
            warnings.append(
                f"Telemetry data is stale: packet age is {age_sec:.0f}s (exceeds {cls.STALE_DATA_THRESHOLD_SECONDS:.0f}s threshold)."
            )

        # Range bounds validation
        if v is not None:
            if v < 0 or v > 30.0:
                inconsistencies.append(f"Voltage reading {v}V is physically out of bounds (0V - 30V).")
        if c is not None:
            if abs(c) > 50.0:
                inconsistencies.append(f"Current reading {c}A exceeds INA219 sensor full-scale range.")
        if t is not None:
            if t < -20.0 or t > 100.0:
                inconsistencies.append(f"DHT11 temperature reading {t}°C is outside valid sensor range.")

        # Power consistency check P ≈ V * |I|
        if v is not None and c is not None and p is not None and abs(c) > 0.05:
            expected_p = abs(v * c)
            delta_p = abs(p - expected_p)
            if delta_p > max(2.5, expected_p * 0.35):
                inconsistencies.append(
                    f"Reported power ({p}W) deviates from calculated V*I ({expected_p:.2f}W) by {delta_p:.2f}W."
                )

        has_channels = (v is not None) or (t is not None)
        is_valid = has_channels and (len(inconsistencies) == 0) and (not is_stale)

        if len(missing) > 0 and not has_channels:
            warnings.append(f"Missing essential sensor channels: {', '.join(missing)}.")

        return DataValidationResult(
            is_valid=is_valid,
            is_stale=is_stale,
            age_seconds=age_sec,
            missing_fields=missing,
            inconsistencies=inconsistencies,
            data_quality_warnings=warnings
        )

    @classmethod
    def calculate_numerical_trends(
        cls, 
        current_telemetry: Dict[str, Any], 
        history: List[Dict[str, Any]]
    ) -> NumericalTrends:
        records = [r for r in (history or []) if isinstance(r, dict)]
        if current_telemetry:
            records.append(current_telemetry)

        if not records:
            return NumericalTrends()

        # 1. Temperature Rise Rate (dT/dt in °C/min)
        valid_temps = [r.get("temperature") for r in records if isinstance(r.get("temperature"), (int, float))]
        temp_rise_rate = None
        if len(valid_temps) >= 2:
            t_start = valid_temps[0]
            t_end = valid_temps[-1]
            # Estimate window duration based on records (approx 2s per packet or timestamp delta)
            time_span_min = max(0.2, len(valid_temps) * (2.0 / 60.0))
            temp_rise_rate = round((t_end - t_start) / time_span_min, 2)

        # 2. Voltage Sag (Delta V) & Estimated Impedance
        valid_voltages = [r.get("voltage") for r in records if isinstance(r.get("voltage"), (int, float))]
        voltage_sag = None
        estimated_ir = None
        if valid_voltages:
            v_max = max(valid_voltages)
            v_min = min(valid_voltages)
            voltage_sag = round(v_max - v_min, 3)

            # Estimate IR if load current is present
            current_val = abs(current_telemetry.get("current", 0.0) or 0.0)
            if current_val > 0.5 and voltage_sag > 0.05:
                # Ohm's law: R_int = Delta V / Delta I (approximate in mOhm)
                estimated_ir = round((voltage_sag / current_val) * 1000.0 * 0.45, 1)

        # 3. Current Statistics
        valid_currents = [r.get("current") for r in records if isinstance(r.get("current"), (int, float))]
        current_rms = None
        current_std = None
        max_current = None
        if valid_currents:
            max_current = round(max([abs(c) for c in valid_currents]), 2)
            mean_c = sum(valid_currents) / len(valid_currents)
            sum_sq = sum(c ** 2 for c in valid_currents)
            current_rms = round((sum_sq / len(valid_currents)) ** 0.5, 2)
            variance = sum((c - mean_c) ** 2 for c in valid_currents) / len(valid_currents)
            current_std = round(variance ** 0.5, 2)

        # 4. Ambient Humidity & Dew Point Calculation
        humidity = current_telemetry.get("humidity") or current_telemetry.get("ambient_humidity")
        dew_point = None
        if humidity is not None and current_telemetry.get("temperature") is not None:
            t = current_telemetry["temperature"]
            rh = float(humidity)
            # Magnus formula approximation
            try:
                a = 17.27
                b = 237.7
                alpha = ((a * t) / (b + t)) + (0.0001 if rh <= 0 else (rh / 100.0))
                # Natural log approximation
                import math
                gamma = ((a * t) / (b + t)) + math.log(max(0.01, rh / 100.0))
                dew_point = round((b * gamma) / (a - gamma), 1)
            except Exception:
                dew_point = None

        return NumericalTrends(
            temperature_rise_rate_c_per_min=temp_rise_rate,
            voltage_sag_v=voltage_sag,
            estimated_internal_resistance_mohm=estimated_ir,
            current_rms_a=current_rms,
            current_std_dev_a=current_std,
            max_current_a=max_current,
            ambient_relative_humidity_pct=float(humidity) if humidity is not None else None,
            dew_point_c=dew_point
        )

    @classmethod
    def calculate_soc_estimate(cls, voltage: Optional[float], spec: BatterySpecification) -> Dict[str, Any]:
        """
        Calculates approximate State of Charge (SOC) based on cell voltage and verified chemistry profile.
        MANDATE: Universal voltage limits cannot be assumed for unknown lithium-ion battery chemistries.
        If chemistry is unverified, returns 'Unavailable' to avoid misleading percentages.
        """
        if voltage is None or spec.verification_status != "VERIFIED":
            return {
                "soc_percent": None,
                "display_text": "Unavailable",
                "is_available": False,
                "reference_profile": spec.name,
                "chemistry": spec.chemistry,
                "basis": "Unavailable: Battery chemistry is unverified. Universal voltage limits cannot be assumed."
            }

        v = float(voltage)

        if spec.id == "calibrated_12v":
            # Calibrated 12V Pack: >= 12.0V is 100% (fully charged); below 12.0V measured accurately down to 9.0V safe cutoff (0%)
            if v >= 12.0:
                return {
                    "soc_percent": 100,
                    "display_text": "~100%",
                    "is_available": True,
                    "reference_profile": spec.name,
                    "chemistry": spec.chemistry,
                    "basis": "Voltage is 12.0V or above: Battery is fully charged (100%)."
                }
            elif v <= 9.0:
                return {
                    "soc_percent": 0,
                    "display_text": "~0%",
                    "is_available": True,
                    "reference_profile": spec.name,
                    "chemistry": spec.chemistry,
                    "basis": "Voltage at or below 9.00V safe discharge cutoff (0%)."
                }
            else:
                soc_val = ((v - 9.0) / (12.0 - 9.0)) * 100.0
                rounded_soc = int(round(soc_val))
                return {
                    "soc_percent": rounded_soc,
                    "display_text": f"~{rounded_soc}%",
                    "is_available": True,
                    "reference_profile": spec.name,
                    "chemistry": spec.chemistry,
                    "basis": f"Measured accurately from voltage ({v:.2f}V): >=12.0V is 100% (fully charged), 9.00V is 0% cutoff."
                }
        elif spec.id == "verified_3s_nmc":
            # 3S NMC (nominal 11.1V, 3.0V - 4.2V/cell -> 9.0V - 12.6V pack)
            curve = [
                (9.00, 0.0),
                (9.60, 10.0),
                (10.80, 30.0),
                (11.10, 50.0),
                (11.55, 65.0),
                (12.00, 80.0),
                (12.45, 95.0),
                (12.60, 100.0)
            ]
        elif spec.id == "verified_4s_lifepo4":
            # 4S LiFePO4 (nominal 12.8V, 2.5V - 3.65V/cell -> 10.0V - 14.6V pack)
            curve = [
                (10.00, 0.0),
                (11.20, 5.0),
                (12.00, 15.0),
                (12.80, 40.0),
                (13.20, 70.0),
                (13.60, 90.0),
                (14.60, 100.0)
            ]
        else:
            if spec.min_operating_voltage and spec.max_operating_voltage and spec.max_operating_voltage > spec.min_operating_voltage:
                if v >= spec.max_operating_voltage:
                    return {
                        "soc_percent": 100,
                        "display_text": "~100%",
                        "is_available": True,
                        "reference_profile": spec.name,
                        "chemistry": spec.chemistry,
                        "basis": f"Voltage is >= {spec.max_operating_voltage:.2f}V: Battery is fully charged (100%)."
                    }
                curve = [
                    (spec.min_operating_voltage, 0.0),
                    (spec.min_operating_voltage + (spec.max_operating_voltage - spec.min_operating_voltage) * 0.5, 50.0),
                    (spec.max_operating_voltage, 100.0)
                ]
            else:
                return {
                    "soc_percent": None,
                    "display_text": "Unavailable",
                    "is_available": False,
                    "reference_profile": spec.name,
                    "chemistry": spec.chemistry,
                    "basis": "Unavailable: Operating voltage limits not defined in profile."
                }

        if v <= curve[0][0]:
            soc = 0.0
        elif v >= curve[-1][0]:
            soc = 100.0
        else:
            soc = 0.0
            for i in range(len(curve) - 1):
                v0, s0 = curve[i]
                v1, s1 = curve[i+1]
                if v0 <= v <= v1:
                    fraction = (v - v0) / (v1 - v0)
                    soc = s0 + fraction * (s1 - s0)
                    break

        rounded_soc = int(round(soc))
        return {
            "soc_percent": rounded_soc,
            "display_text": f"~{rounded_soc}%",
            "is_available": True,
            "reference_profile": spec.name,
            "chemistry": spec.chemistry,
            "basis": f"Calculated using {spec.name} verified piecewise OCV reference curve."
        }

    @classmethod
    def calculate_condition_score(
        cls,
        telemetry: Dict[str, Any],
        val_result: DataValidationResult,
        trends: NumericalTrends,
        spec: BatterySpecification,
        critical_flags: List[str],
        warning_flags: List[str]
    ) -> Tuple[Optional[float], str, Dict[str, Any]]:
        """
        Computes documented, defensible Battery Condition Score (0-100%) and Status.
        Statuses: 'Excellent', 'Good', 'Normal', 'Warning', 'Danger', 'Insufficient Data'
        """
        if not val_result.is_valid or spec.verification_status != "VERIFIED":
            return None, "Insufficient Data", {
                "score": None,
                "status": "Insufficient Data",
                "base_points": 100.0,
                "deductions": [],
                "reason": (
                    "Battery chemistry is unverified; universal voltage limits cannot be assumed."
                    if spec.verification_status != "VERIFIED"
                    else (val_result.data_quality_warnings[0] if val_result.data_quality_warnings else "Telemetry data is incomplete or stale.")
                )
            }

        score = 100.0
        deductions = []

        t = telemetry.get("temperature")
        v = telemetry.get("voltage")
        c = telemetry.get("current")

        # 1. Thermal penalties
        if t is not None:
            if t >= spec.critical_overtemp_cutoff:
                deductions.append({"factor": "Critical Over-Temperature", "penalty": 60.0, "details": f"{t:.1f}°C >= {spec.critical_overtemp_cutoff}°C"})
                score -= 60.0
            elif t >= 45.0:
                deductions.append({"factor": "Elevated Buzzer Alarm Temp", "penalty": 40.0, "details": f"{t:.1f}°C >= 45.0°C"})
                score -= 40.0
            elif t >= spec.ambient_fan_trigger_temp:
                deductions.append({"factor": "Cooling Fan Engagement Temp", "penalty": 20.0, "details": f"{t:.1f}°C >= {spec.ambient_fan_trigger_temp}°C"})
                score -= 20.0
            elif t >= 30.0:
                deductions.append({"factor": "Mild Ambient Elevation", "penalty": 5.0, "details": f"{t:.1f}°C >= 30.0°C"})
                score -= 5.0

        # 2. Temperature rise rate (dT/dt)
        if trends.temperature_rise_rate_c_per_min is not None and trends.temperature_rise_rate_c_per_min >= 1.20:
            deductions.append({"factor": "Rapid Thermal Rise Rate", "penalty": 15.0, "details": f"{trends.temperature_rise_rate_c_per_min:.2f}°C/min >= 1.20°C/min"})
            score -= 15.0

        # 3. Voltage window penalties
        if v is not None:
            if spec.max_operating_voltage is not None and v > spec.max_operating_voltage:
                deductions.append({"factor": "Over-Voltage Cutoff Breach", "penalty": 50.0, "details": f"{v:.2f}V > {spec.max_operating_voltage:.2f}V"})
                score -= 50.0
            elif spec.warning_high_voltage is not None and v > spec.warning_high_voltage:
                deductions.append({"factor": "High Voltage Warning Reserve", "penalty": 15.0, "details": f"{v:.2f}V > {spec.warning_high_voltage:.2f}V"})
                score -= 15.0

            if spec.min_operating_voltage is not None and v < spec.min_operating_voltage:
                deductions.append({"factor": "Under-Voltage Cutoff Breach", "penalty": 50.0, "details": f"{v:.2f}V < {spec.min_operating_voltage:.2f}V"})
                score -= 50.0
            elif spec.warning_low_voltage is not None and v < spec.warning_low_voltage:
                deductions.append({"factor": "Low Voltage Warning Reserve", "penalty": 15.0, "details": f"{v:.2f}V < {spec.warning_low_voltage:.2f}V"})
                score -= 15.0

        # 4. Current load penalty
        if c is not None and spec.max_continuous_discharge_current_a is not None:
            if abs(c) > spec.max_continuous_discharge_current_a:
                deductions.append({"factor": "Continuous Current Exceeded", "penalty": 25.0, "details": f"{abs(c):.2f}A > {spec.max_continuous_discharge_current_a:.1f}A"})
                score -= 25.0

        final_score = max(0.0, min(100.0, round(score, 1)))

        if len(critical_flags) > 0 or final_score < 40.0:
            status = "Danger"
        elif len(warning_flags) > 0 or final_score < 60.0:
            status = "Warning"
        elif final_score < 75.0:
            status = "Normal"
        elif final_score < 90.0:
            status = "Good"
        else:
            status = "Excellent"

        breakdown = {
            "score": final_score,
            "status": status,
            "base_points": 100.0,
            "total_deductions": round(100.0 - final_score, 1),
            "deductions": deductions,
            "model_basis": "Documented 100-point composite thermal, electrical, and specification deduction calculation."
        }

        return final_score, status, breakdown

    @classmethod
    def evaluate_condition(
        cls,
        current_telemetry: Dict[str, Any],
        history: List[Dict[str, Any]],
        spec: Optional[BatterySpecification] = None
    ) -> ConditionAssessment:
        if spec is None:
            spec = get_active_battery_spec()

        val_result = cls.validate_telemetry(current_telemetry)
        trends = cls.calculate_numerical_trends(current_telemetry, history)

        v = current_telemetry.get("voltage")
        c = current_telemetry.get("current")
        t = current_telemetry.get("temperature")

        critical_flags = []
        warning_flags = []

        # ========================================================
        # 1. HARDWARE THERMAL CHECKS (APPLIES TO ALL BATTERIES)
        # ========================================================
        if t is not None:
            if t >= spec.critical_overtemp_cutoff:
                critical_flags.append(
                    f"CRITICAL OVER-TEMPERATURE: Ambient temperature reached {t:.1f}°C "
                    f"(Trip threshold: {spec.critical_overtemp_cutoff}°C). Immediate thermal hazard."
                )
            elif t >= spec.ambient_fan_trigger_temp:
                warning_flags.append(
                    f"ELEVATED AMBIENT TEMPERATURE: Enclosure air reached {t:.1f}°C "
                    f"(Fan engagement threshold: {spec.ambient_fan_trigger_temp}°C)."
                )

        if trends.temperature_rise_rate_c_per_min is not None:
            if trends.temperature_rise_rate_c_per_min >= 1.20:
                warning_flags.append(
                    f"RAPID THERMAL RISE RATE: Enclosure heating at {trends.temperature_rise_rate_c_per_min:.2f}°C/min "
                    f"(Threshold: 1.20°C/min). Indicates intense internal cell Joule dissipation."
                )

        # ========================================================
        # 2. SPECIFICATION VERIFICATION & VOLTAGE LIMIT CHECKS
        # ========================================================
        is_spec_verified = (spec.verification_status == "VERIFIED")

        if is_spec_verified and v is not None:
            # Over-voltage check
            if spec.max_operating_voltage is not None and v > spec.max_operating_voltage:
                critical_flags.append(
                    f"OVER-VOLTAGE BREACH: Pack voltage {v:.2f}V exceeds verified upper limit "
                    f"({spec.max_operating_voltage:.2f}V for {spec.chemistry})."
                )
            elif spec.warning_high_voltage is not None and v > spec.warning_high_voltage:
                warning_flags.append(
                    f"HIGH VOLTAGE ADVISORY: Pack voltage {v:.2f}V is approaching upper limit "
                    f"({spec.warning_high_voltage:.2f}V)."
                )

            # Under-voltage check
            if spec.min_operating_voltage is not None and v < spec.min_operating_voltage:
                critical_flags.append(
                    f"UNDER-VOLTAGE CUTOFF BREACH: Pack voltage {v:.2f}V is below verified lower cutoff "
                    f"({spec.min_operating_voltage:.2f}V for {spec.chemistry}). Deep discharge lockout."
                )
            elif spec.warning_low_voltage is not None and v < spec.warning_low_voltage:
                warning_flags.append(
                    f"LOW VOLTAGE ADVISORY: Pack voltage {v:.2f}V depleted into warning reserve "
                    f"(< {spec.warning_low_voltage:.2f}V)."
                )

        # ========================================================
        # 3. CURRENT LOAD CHECKS
        # ========================================================
        if c is not None and spec.max_continuous_discharge_current_a is not None:
            if abs(c) > spec.max_continuous_discharge_current_a:
                warning_flags.append(
                    f"CONTINUOUS CURRENT EXCEEDED: Load current {abs(c):.2f}A exceeds rated limit "
                    f"({spec.max_continuous_discharge_current_a:.1f}A)."
                )

        # ========================================================
        # 4. FINAL CONDITION CLASSIFICATION & DOCUMENTED SCORE
        # ========================================================
        # Hierarchy: CRITICAL/DANGER > INSUFFICIENT DATA (if unverified or invalid) > WARNING > NORMAL
        score, detailed_status, score_breakdown = cls.calculate_condition_score(
            current_telemetry, val_result, trends, spec, critical_flags, warning_flags
        )

        soc_estimate = cls.calculate_soc_estimate(v, spec)
        soh_estimate = {
            "soh_percent": None,
            "display_text": "Unavailable",
            "status": "Uncalibrated (Requires multi-cycle capacity test)",
            "explanation": "State of Health (SOH) measures retained chemical capacity relative to factory nominal rating. SOH cannot be calculated from instantaneous voltage alone."
        }

        if len(critical_flags) > 0:
            condition = "CRITICAL"
            condition_status = "Danger"
            primary_reason = critical_flags[0]
        elif not is_spec_verified:
            condition = "INSUFFICIENT DATA"
            condition_status = "Insufficient Data"
            primary_reason = (
                f"SPECIFICATIONS UNVERIFIED: Exact cell chemistry and series arrangement are unconfirmed for '{spec.name}'. "
                f"Universal voltage envelopes cannot be assumed for nominal 12V packs without verified manufacturer datasheet documentation."
            )
        elif not val_result.is_valid:
            condition = "INSUFFICIENT DATA"
            condition_status = "Insufficient Data"
            primary_reason = (
                val_result.data_quality_warnings[0] if val_result.data_quality_warnings 
                else "Sensor readings are incomplete, stale, or disconnected."
            )
        elif len(warning_flags) > 0:
            condition = "WARNING"
            condition_status = "Warning"
            primary_reason = warning_flags[0]
        else:
            condition = "NORMAL"
            condition_status = detailed_status
            v_str = f"{v:.2f}V" if v is not None else "--"
            t_str = f"{t:.1f}°C" if t is not None else "--"
            primary_reason = (
                f"All measured electrical and thermal parameters ({v_str}, {t_str}) are operating within verified "
                f"manufacturer design limits ({spec.name}). Thermal dissipation is nominal."
            )

        verified_limits = {
            "profile_name": spec.name,
            "chemistry": spec.chemistry,
            "nominal_voltage": f"{spec.nominal_voltage:.1f} V",
            "operating_voltage_window": (
                f"{spec.min_operating_voltage:.2f}V - {spec.max_operating_voltage:.2f}V" 
                if is_spec_verified and spec.min_operating_voltage and spec.max_operating_voltage 
                else "Unverified (Universal Limits Prohibited)"
            ),
            "max_discharge_temp": f"{spec.max_discharge_temp:.1f} °C",
            "ambient_fan_trigger": f"{spec.ambient_fan_trigger_temp:.1f} °C",
            "verification_status": spec.verification_status,
        }

        ambient_note = (
            "DHT11 measures enclosure ambient air temperature, not the internal core cell temperature. "
            "Internal cell core temperature may be 10°C to 20°C higher under sustained discharge loads."
        )

        health_disclaimer = (
            "A normal voltage reading alone DOES NOT prove the battery is healthy. Resting open-circuit "
            "voltage frequently masks elevated internal impedance, capacity loss, and latent cell degradation."
        )

        return ConditionAssessment(
            condition=condition,
            condition_status=condition_status,
            battery_condition_score=score if condition not in ["INSUFFICIENT DATA"] else None,
            battery_condition_breakdown=score_breakdown,
            soc_estimate=soc_estimate,
            soh_estimate=soh_estimate,
            primary_reason=primary_reason,
            active_warnings=warning_flags,
            active_critical_flags=critical_flags,
            specification_status=spec.verification_status,
            data_validation=val_result,
            numerical_trends=trends,
            verified_limits=verified_limits,
            ambient_vs_cell_note=ambient_note,
            health_disclaimer=health_disclaimer
        )
