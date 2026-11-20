# Fault Diagnosis Procedures & Actionable Maintenance Protocols

## 1. Systematic Fault Classification Matrix

| Symptom / Anomaly | Physical Root Cause | Severity Level | Immediate Action |
| :--- | :--- | :--- | :--- |
| **Ambient Temp ≥ 60.0°C** | Severe thermal runaway risk or environmental overheating | **CRITICAL** | Disconnect electrical loads immediately. Evacuate testbench. Maintain active cooling fan. |
| **Ambient Temp ≥ 35.0°C** | Normal operational heat or restricted ventilation | **WARNING** | Engage 12V cooling fan PWM. Inspect air intake/exhaust grilles. Verify cell spacing. |
| **Rapid Thermal Rise Rate (dT/dt > 1.2°C/min)** | Abnormal internal cell resistance ($R_{int}$) or micro-short | **WARNING / ELEVATED** | Derate continuous discharge current by 50%. Measure cell skin temperature with IR thermometer. |
| **Excessive Voltage Sag (> 1.5V under load)** | Elevated cell internal impedance, loose busbars, or weak cell | **WARNING** | Perform 4-wire Kelvin resistance measurement on series interconnects and cells. |
| **Voltage Depletion (< Cut-off threshold)** | Excessive depth of discharge (DoD) or parasitic drain | **CRITICAL** | Isolate load immediately. Check individual cell voltages with calibrated digital multimeter. |
| **Telemetry Ingestion Age > 45s (Stale Data)** | ESP8266 Wi-Fi stall, RTDB socket timeout, or power loss | **INSUFFICIENT DATA** | Verify 5V power to NodeMCU. Inspect serial debug console and Wi-Fi RSSI signal strength. |
| **Missing Voltage/Current Telemetry (INA219 null)** | I²C bus communication failure (address 0x40) or wire disconnect | **INSUFFICIENT DATA** | Inspect SDA (D5) / SCL (D6) wiring harness and 3.3V power rails. Reset I²C bus. |
| **Missing Ambient Temp/Humidity (DHT11 null)** | 1-wire timing failure (DHT_PIN D7) or sensor disconnect | **INSUFFICIENT DATA** | Verify 10kΩ pull-up resistor on D7 pin. Check 3.3V/5V supply and ground connections. |

---

## 2. Evidence-Based Diagnostic Workflow
For any identified battery anomaly, maintenance personnel must follow this evidence-grounded sequence:

1. **Safety Interlock Verification:**
   - Confirm that automated safety actuators (cooling fan, hardware trip interlocks) are operating independently of web application status.
   - Do NOT override hardware cutoffs based on software indications.

2. **Physical Measurement Mandate:**
   - Web application telemetry provides active surveillance but does not replace physical multi-meter calibration.
   - Measure each individual series cell voltage using a calibrated digital multimeter at the balance lead connector.
   - Any series cell delta:
     $$\Delta V_{\text{cell}} = V_{\text{cell, max}} - V_{\text{cell, min}} > 0.050\text{ V}$$
     indicates active cell imbalance requiring manual balancing before returning to service.

3. **Data Quality Integrity Check:**
   - In consistent telemetry, electrical power must satisfy:
     $$P_{\text{measured}} \approx V_{\text{measured}} \times |I_{\text{measured}}| \quad (\pm 5\%)$$
   - Significant discrepancies indicate sensor ADC saturation, ground loops, or floating analog references.

4. **Environmental Considerations:**
   - Ambient humidity above 85% RH combined with temperature cycling creates condensation risk on exposed printed circuit boards (PCBs), leading to leakage currents across high-impedance divider networks.
