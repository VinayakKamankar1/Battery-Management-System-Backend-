# Technical Specification & Operating Limits: Nominal 12V Lithium-Ion Battery Packs

## 1. Scope & Critical Disclaimers
This document specifies electrical, thermal, and chemical operating boundaries for nominal 12V lithium-ion battery assemblies used in stationary energy storage and electric testbenches.

> **CRITICAL ASIL-D / ISO 26262 SAFETY PRINCIPLE:**
> **A universal voltage envelope CANNOT be assumed for every nominal 12V battery.**
> "Nominal 12V" is a commercial designation covering multiple distinctly incompatible chemistries. Operating limits must be strictly verified against manufacturer datasheets. Until exact chemistry and cell arrangement are confirmed, systems must display **INSUFFICIENT DATA / SPECIFICATIONS UNVERIFIED** rather than guessing operating limits.

---

## 2. Common "Nominal 12V" Chemistries Comparison

| Specification Parameter | 3S Li-ion (NMC / LCO / INR) | 4S Lithium Iron Phosphate (LiFePO4) | Lead-Acid Equivalent (VRLA/AGM) |
| :--- | :--- | :--- | :--- |
| **Cell Chemistry** | LiNiMnCoO2 / LiCoO2 | LiFePO4 (LFP) | PbO2 / Sponge Pb |
| **Series Cell Count** | 3 cells in series (3S) | 4 cells in series (4S) | 6 cells in series (6S) |
| **Nominal Voltage** | **11.1 V - 11.4 V** (3.7V - 3.8V/cell) | **12.8 V** (3.2V/cell) | **12.0 V** (2.0V/cell) |
| **Max Charge Voltage** | **12.60 V** (4.20V/cell strictly) | **14.60 V** (3.65V/cell strictly) | **14.40 V - 14.70 V** |
| **Min Discharge Cut-off** | **9.00 V** (3.00V/cell safe cutoff) | **10.00 V** (2.50V/cell safe cutoff) | **10.50 V** (1.75V/cell) |
| **Warning Voltage (Low)** | **9.60 V** (3.20V/cell) | **11.20 V** (2.80V/cell) | **11.60 V** |
| **Float / Resting Voltage**| **12.30 V - 12.50 V** | **13.20 V - 13.40 V** | **12.60 V - 12.80 V** |

---

## 3. Operating Envelope Discrepancy Hazards
- **Overvoltage Hazard on 3S Pack:** Applying a 4S LiFePO4 charger voltage (14.6V) to a 3S NMC pack forces cells past **4.86V/cell**, triggering immediate cathode delithiation, violent oxygen release, electrolyte oxidation, and catastrophic thermal runaway.
- **Deep Discharge Hazard on 4S Pack:** Discharging a 4S LiFePO4 pack down to 9.0V (the 3S cutoff) forces LFP cells down to **2.25V/cell**, precipitating irreversible copper current collector dissolution, dendrite growth upon subsequent recharge, and internal short-circuits.

---

## 4. Temperature Operating Boundaries (All Chemistries)
- **Normal Operating Range:** 15.0°C to 30.0°C.
- **Ambient Warning Threshold:** ≥ 35.0°C (requires active cooling fan engagement).
- **Critical Thermal Runaway Protection Cut-off:** ≥ 60.0°C (mandatory emergency load shedding).
- **Low-Temperature Charging Lockout:** < 0.0°C (prevents metallic lithium plating on graphite anode).

---

## 5. Telemetry Validation Rules
1. A voltage reading within nominal range (e.g., 12.2V) **does NOT prove battery health**; resting OCV masks internal degradation, cell capacity loss, and elevated internal impedance ($R_{int}$).
2. Ambient air temperature (measured via external sensors such as DHT11) differs significantly from internal core cell temperatures under high dynamic load. An elevated ambient temperature rise rate ($dT/dt > 1.2^\circ\text{C/min}$) indicates intense internal Joule heating ($I^2 R_{int}$).
