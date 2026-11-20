# Battery Safety Documentation: Thermal Runaway, Cell Degradation & Core Diagnostics

## 1. Physical Anatomy of Thermal Runaway
Thermal runaway is an uncontrolled, self-sustaining exothermic chain reaction inside secondary lithium-ion cells. It progresses through distinct physical and chemical stages:

1. **Stage 1 (70°C - 100°C) — SEI Layer Decomposition:**
   The metastable Solid Electrolyte Interphase layer on the graphite anode decomposes exothermically ($~120\text{ J/g}$). Intercalated lithium reacts directly with organic solvents (EC, DMC, DEC), producing flammable hydrocarbon gases ($C_2H_4, CH_4$).

2. **Stage 2 (120°C - 140°C) — Polymeric Separator Shutdown & Melting:**
   Standard polyethylene (PE) or polypropylene (PP) separators melt and collapse, losing structural integrity. Direct contact between the cathode and anode creates low-resistance internal shorts, releasing stored electrical energy as intense local heat.

3. **Stage 3 (160°C - 200°C) — Cathode Active Material Decomposition:**
   Cathode metal oxides (e.g., $Li_{1-x}Ni_{0.8}Mn_{0.1}Co_{0.1}O_2$) collapse, releasing free molecular oxygen ($O_2$). The released oxygen oxidizes the organic electrolyte solvents in a self-oxidizing combustion process independent of external atmospheric air.

4. **Stage 4 (> 200°C - 800°C) — Catastrophic Runaway & Venting:**
   Thermal rise rates exceed $100^\circ\text{C/min}$. Rapid internal pressure generation ruptures safety vents, ejecting toxic, flammable gases ($HF, CO, CO_2, POF_3$) and incandescent particulate matter.

---

## 2. Distinguishing Ambient Enclosure Air vs. Cell Core Temperature
- **Sensor Location Distinction:** The DHT11 sensor installed in the Smart BMS measures the **ambient enclosure air temperature**, NOT the internal core jelly-roll temperature of individual cells.
- **Thermal Inertia & Lag:** Cell core temperatures can be $10^\circ\text{C}$ to $25^\circ\text{C}$ higher than ambient enclosure air under heavy discharge ($C > 1.5C$).
- **Thermal Gradient Indicator:** If the ambient air temperature increases rapidly at a rate:
  $$\frac{dT}{dt} \ge 1.20^\circ\text{C / min}$$
  this indicates massive internal Joule dissipation ($I^2 R_{int}$) or localized internal micro-shorting, even if absolute ambient temperature has not yet reached the 60.0°C cutoff.

---

## 3. Deep Discharge & Copper Shunting Hazards
- **Overdischarge Mechanism:** When a lithium cell drops below 1.5V/cell (or pack drops below cut-off), the negative electrode copper foil current collector oxidizes into soluble $Cu^+$ and $Cu^{2+}$ ions:
  $$Cu \rightarrow Cu^{2+} + 2e^-$$
- **Dendrite Formation on Recharge:** When the cell is recharged, dissolved copper ions migrate back to the anode and precipitate as sharp metallic copper dendrites.
- **Fatal Shunting:** These metallic copper dendrites bridge the separator, creating permanent micro-shorts that induce high self-discharge and elevated thermal generation.
- **Safety Directive:** Any cell verified to have spent extended time below 1.5V must be decommissioned immediately and never recharged.
