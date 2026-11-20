# Charging & Discharging Guidelines for Lithium-Ion Battery Systems

## 1. Constant Current / Constant Voltage (CC-CV) Charging Protocol
All lithium-ion secondary cells (NMC, LCO, LFP) must adhere to the two-stage Constant Current / Constant Voltage protocol:

1. **Stage 1: Constant Current (CC):**
   - Charge current regulated at manufacturer-specified C-rate (typically 0.5C to 1.0C maximum for standard cells).
   - Voltage rises monotonically as charge accumulates.
   - For 3S NMC packs: Current maintained until pack reaches **12.60 V** (4.20V/cell).
   - For 4S LiFePO4 packs: Current maintained until pack reaches **14.60 V** (3.65V/cell).

2. **Stage 2: Constant Voltage (CV):**
   - Voltage strictly clamped at the upper limit (12.60V or 14.60V).
   - Current exponentially decays as cell polarization approaches chemical equilibrium.
   - **Termination Condition:** Charging must terminate when charge current drops below $C/20$ to $C/50$ (typically 50mA - 100mA).
   - **Trickle Charging Prohibition:** Trickle charging or continuous float at maximum voltage causes continuous electrolyte oxidation, gas generation, and accelerated capacity fade.

---

## 2. Low-Temperature Lithium Plating Hazards
- **Rule:** Never charge any lithium-ion cell below 0°C (32°F) without pre-heating.
- **Physical Mechanism:** At low temperatures, lithium-ion diffusion within the liquid electrolyte and solid graphite intercalation matrix slows drastically. The anode potential drops below $0\text{V vs. Li/Li}^+$, forcing lithium ions to deposit as metallic lithium dendrites on the anode surface instead of intercalating.
- **Consequence:** Dendrites penetrate microporous polymeric separators, causing catastrophic internal short-circuits, micro-arcing, and delayed thermal runaway during subsequent cycles.

---

## 3. High-Temperature Degradation & Thermal Derating
- **Operating Above 45°C:** Solid Electrolyte Interphase (SEI) layer begins passive dissolution. Fresh electrolyte decomposes on newly exposed anode surfaces, consuming active cyclable lithium and permanently reducing State of Health (SOH).
- **Cooling Fan Modulation:** The BMS must activate cooling actuators (such as the L298N dual H-bridge fan driver) when enclosure ambient temperature crosses **35.0°C**.
- **Current Derating:** Continuous discharge current should be derated by 50% if ambient temperature surpasses 45.0°C. If temperature exceeds **60.0°C**, emergency disconnection is required.

---

## 4. In-Service Discharge Safety Boundaries
- **Under-Voltage Cutoff:** Discharge must halt immediately when the pack reaches minimum cut-off voltage under load.
- **Transient Voltage Sag:** High dynamic loads induce an instantaneous IR drop:
  $$\Delta V_{\text{sag}} = I_{\text{load}} \times R_{\text{int}}$$
- If voltage rebounds above cutoff when load is removed, the battery must still be considered depleted; continuous load pulsing in the depletion zone triggers irreversible copper dissolution.
