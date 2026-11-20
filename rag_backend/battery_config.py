"""
Battery Specification Configuration Manager
Manages verified manufacturer specifications for nominal 12V lithium-ion batteries.

CRITICAL DESIGN RULE:
Universal voltage limits CANNOT be assumed for every nominal 12V lithium-ion battery.
Until chemistry and necessary operating limits are verified, the system must show
an appropriate 'INSUFFICIENT DATA' or 'SPECIFICATIONS UNVERIFIED' status instead of guessing.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class BatterySpecification(BaseModel):
    id: str = Field(..., description="Unique specification profile identifier")
    name: str = Field(..., description="Display title for configuration")
    manufacturer: str = Field("Generic / Unspecified", description="Manufacturer name")
    model: str = Field("Unspecified", description="Model number or cell part number")
    chemistry: str = Field("Unverified", description="Cell chemistry e.g. NMC, LFP, LCO, LMO")
    cell_configuration: str = Field("Unverified", description="Series/Parallel layout e.g. 3S1P, 4S1P")
    nominal_voltage: float = Field(12.0, description="Nominal pack voltage (V)")
    
    # Voltage thresholds (V)
    min_operating_voltage: Optional[float] = Field(None, description="Absolute lower cutoff voltage (V)")
    warning_low_voltage: Optional[float] = Field(None, description="Early low voltage warning threshold (V)")
    nominal_resting_voltage: Optional[float] = Field(None, description="Typical resting OCV (V)")
    warning_high_voltage: Optional[float] = Field(None, description="Early high voltage warning threshold (V)")
    max_operating_voltage: Optional[float] = Field(None, description="Absolute upper charge cutoff voltage (V)")

    # Thermal limits (°C)
    min_charge_temp: float = Field(0.0, description="Minimum allowable charge temperature (°C)")
    max_charge_temp: float = Field(45.0, description="Maximum allowable charge temperature (°C)")
    min_discharge_temp: float = Field(-20.0, description="Minimum allowable discharge temperature (°C)")
    max_discharge_temp: float = Field(60.0, description="Maximum allowable discharge temperature (°C)")
    ambient_fan_trigger_temp: float = Field(30.0, description="DHT11 ambient temp to activate cooling fan & buzzer (°C)")
    critical_overtemp_cutoff: float = Field(60.0, description="Hardware safety cutoff temp (°C)")

    # Capacity & Current limits
    rated_capacity_ah: Optional[float] = Field(None, description="Rated capacity in Amp-hours (Ah)")
    max_continuous_discharge_current_a: Optional[float] = Field(None, description="Max continuous discharge current (A)")
    max_charge_current_a: Optional[float] = Field(None, description="Max continuous charge current (A)")

    # Verification status: 'UNVERIFIED' | 'VERIFIED'
    verification_status: str = Field("UNVERIFIED", description="Verification status against manufacturer datasheet")
    verification_notes: str = Field("", description="Details regarding datasheet source or unverified status")


# Standard Profiles
BATTERY_PROFILES: Dict[str, BatterySpecification] = {
    "unverified_12v": BatterySpecification(
        id="unverified_12v",
        name="Nominal 12V Lithium-Ion (Unverified Chemistry)",
        manufacturer="Unverified / Testbench Default",
        model="Prototype 12V Pack",
        chemistry="Unverified Lithium-Ion",
        cell_configuration="Unverified (Possible 3S NMC or 4S LiFePO4)",
        nominal_voltage=12.0,
        min_operating_voltage=None,  # Cannot be guessed universally
        warning_low_voltage=None,
        nominal_resting_voltage=None,
        warning_high_voltage=None,
        max_operating_voltage=None,  # Cannot be guessed universally
        min_charge_temp=0.0,
        max_charge_temp=45.0,
        min_discharge_temp=-20.0,
        max_discharge_temp=60.0,
        ambient_fan_trigger_temp=30.0,
        critical_overtemp_cutoff=60.0,
        rated_capacity_ah=None,
        max_continuous_discharge_current_a=None,
        max_charge_current_a=None,
        verification_status="UNVERIFIED",
        verification_notes=(
            "Exact cell chemistry and series arrangement are unconfirmed. Universal voltage limits "
            "CANNOT be assumed for every nominal 12V battery. Operating limits must be physically "
            "verified against manufacturer documentation before voltage boundaries can be validated."
        )
    ),
    "verified_3s_nmc": BatterySpecification(
        id="verified_3s_nmc",
        name="3S Lithium-Ion Pack (NMC 18650/21700)",
        manufacturer="Standard Tier-1 Specification (e.g. Samsung/LG/Panasonic)",
        model="3S 18650 Cylindrical Pack",
        chemistry="Lithium Nickel Manganese Cobalt Oxide (LiNiMnCoO2 / NMC)",
        cell_configuration="3S (3 series cells, 3.7V nominal each)",
        nominal_voltage=11.1,
        min_operating_voltage=9.00,       # 3.00 V / cell cutoff
        warning_low_voltage=9.60,         # 3.20 V / cell advisory
        nominal_resting_voltage=11.85,    # 3.95 V / cell mid-charge
        warning_high_voltage=12.45,       # 4.15 V / cell near full
        max_operating_voltage=12.60,      # 4.20 V / cell charge limit
        min_charge_temp=0.0,
        max_charge_temp=45.0,
        min_discharge_temp=-10.0,
        max_discharge_temp=55.0,
        ambient_fan_trigger_temp=30.0,
        critical_overtemp_cutoff=60.0,
        rated_capacity_ah=2.6,
        max_continuous_discharge_current_a=10.0,
        max_charge_current_a=2.6,
        verification_status="VERIFIED",
        verification_notes=(
            "Verified against 3S NMC 4.2V/cell charging standards. Upper cutoff is 12.60V; "
            "lower safe discharge limit is 9.00V."
        )
    ),
    "verified_4s_lifepo4": BatterySpecification(
        id="verified_4s_lifepo4",
        name="4S Lithium Iron Phosphate Pack (LiFePO4)",
        manufacturer="Standard LFP Industrial Specification",
        model="4S LFP Prismatic / Cylindrical Pack",
        chemistry="Lithium Iron Phosphate (LiFePO4)",
        cell_configuration="4S (4 series cells, 3.2V nominal each)",
        nominal_voltage=12.8,
        min_operating_voltage=10.00,      # 2.50 V / cell cutoff
        warning_low_voltage=11.20,        # 2.80 V / cell advisory
        nominal_resting_voltage=13.20,    # 3.30 V / cell resting
        warning_high_voltage=14.20,       # 3.55 V / cell near full
        max_operating_voltage=14.60,      # 3.65 V / cell charge limit
        min_charge_temp=0.0,
        max_charge_temp=45.0,
        min_discharge_temp=-20.0,
        max_discharge_temp=60.0,
        ambient_fan_trigger_temp=30.0,
        critical_overtemp_cutoff=60.0,
        rated_capacity_ah=6.0,
        max_continuous_discharge_current_a=15.0,
        max_charge_current_a=3.0,
        verification_status="VERIFIED",
        verification_notes=(
            "Verified against 4S LiFePO4 3.65V/cell standards. Upper charge voltage is 14.60V; "
            "lower cutoff is 10.00V. Flat discharge curve requires impedance or Coulometric tracking."
        )
    ),
    "calibrated_12v": BatterySpecification(
        id="calibrated_12v",
        name="12V Lithium-Ion Battery (Calibrated: >=12V Full, 9V Cutoff)",
        manufacturer="Calibrated 12V Testbench",
        model="12V Nominal Lithium-Ion Assembly",
        chemistry="12V Lithium-Ion",
        cell_configuration="3S Pack (9.0V - 12.0V)",
        nominal_voltage=12.0,
        min_operating_voltage=9.00,       # 0% empty safe discharge cutoff
        warning_low_voltage=9.60,         # 20% low voltage advisory
        nominal_resting_voltage=11.10,    # 50%-70% mid-range voltage
        warning_high_voltage=12.00,       # Full charge voltage
        max_operating_voltage=12.00,      # 100% fully charged (>=12.0V is 100%)
        min_charge_temp=0.0,
        max_charge_temp=45.0,
        min_discharge_temp=-20.0,
        max_discharge_temp=60.0,
        ambient_fan_trigger_temp=30.0,
        critical_overtemp_cutoff=60.0,
        rated_capacity_ah=2.6,
        max_continuous_discharge_current_a=10.0,
        max_charge_current_a=2.6,
        verification_status="VERIFIED",
        verification_notes=(
            "Calibrated 12V configuration: >=12.0V is 100% (fully charged); below 12.0V "
            "is measured accurately based on voltage down to 9.00V safe cutoff (0%)."
        )
    )
}

# Runtime active specification state - defaults to calibrated 12V pack
_active_profile_id: str = "calibrated_12v"


def get_active_battery_spec() -> BatterySpecification:
    """Return the currently active battery specification."""
    global _active_profile_id
    return BATTERY_PROFILES.get(_active_profile_id, BATTERY_PROFILES["calibrated_12v"])


def set_active_battery_profile(profile_id: str) -> BatterySpecification:
    """Switch active profile to a known profile ID."""
    global _active_profile_id
    if profile_id not in BATTERY_PROFILES:
        raise ValueError(f"Unknown battery profile ID: {profile_id}. Available: {list(BATTERY_PROFILES.keys())}")
    _active_profile_id = profile_id
    return get_active_battery_spec()


def update_custom_battery_spec(custom_spec: Dict[str, Any]) -> BatterySpecification:
    """Register or update a custom verified battery specification."""
    global _active_profile_id
    spec = BatterySpecification(**custom_spec)
    BATTERY_PROFILES[spec.id] = spec
    _active_profile_id = spec.id
    return spec
