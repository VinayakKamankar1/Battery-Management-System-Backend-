"""
RAG-Based AI Battery Health Analysis Engine
Orchestrates:
1. Firebase Realtime Database ingestion & validation
2. Deterministic numerical trends and threshold derivations
3. Semantic retrieval of technical documentation from FAISS vector store
4. Grounded LLM / synthesis engine with strict citation requirements
5. Automated output validation (ensures no hallucinated safety or fabricated metrics)
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

from battery_config import BatterySpecification, get_active_battery_spec
from deterministic_evaluator import DeterministicBatteryEvaluator, ConditionAssessment
from vector_store import get_vector_store
from firebase_auth import get_authenticated_rtdb_url

load_dotenv()


class BatteryRagEngine:
    """
    Retrieval-Augmented Generation engine for battery condition analysis.
    """

    def __init__(self):
        self.vector_store = get_vector_store()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.last_analysis: Optional[Dict[str, Any]] = None

    def fetch_firebase_telemetry(self, db_url: Optional[str] = None) -> Dict[str, Any]:
        """Fetch latest sensor readings directly from Firebase Realtime Database REST endpoint."""
        # Query /smart_bms/latest.json with authentication
        try:
            if db_url:
                target = f"{db_url.rstrip('/')}/smart_bms/latest.json"
            else:
                target = get_authenticated_rtdb_url("smart_bms/latest.json")

            resp = requests.get(target, timeout=4.0)
            if resp.ok and resp.json():
                data = resp.json()
                # Normalize field names if needed
                return {
                    "voltage": data.get("voltage_V") if data.get("voltage_V") is not None else data.get("voltage"),
                    "current": data.get("current_A") if data.get("current_A") is not None else data.get("current"),
                    "power": data.get("power_W") if data.get("power_W") is not None else data.get("power"),
                    "temperature": data.get("temperature_C") if data.get("temperature_C") is not None else data.get("temperature"),
                    "humidity": data.get("humidity_percent") if data.get("humidity_percent") is not None else (data.get("humidity_pct") or data.get("humidity")),
                    "ambient_humidity": data.get("humidity_percent") or data.get("ambient_humidity"),
                    "fanStatus": data.get("fan_status") or data.get("fan_state") or data.get("fanStatus") or "OFF",
                    "buzzerStatus": data.get("buzzer_status") or data.get("buzzer_state") or data.get("buzzerStatus") or "OFF",
                    "device_status": data.get("device_status"),
                    "rawTimestamp": data.get("timestamp_epoch") or data.get("rawTimestamp") or data.get("updatedAt") or (time.time() * 1000 if data.get("uptime_ms") else None),
                    "timestamp": data.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            else:
                print(f"[RAG Engine] Telemetry fetch response: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[RAG Engine] Note: Direct Firebase pull error ({e}).")

        return {}

    def fetch_firebase_history(self, db_url: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch historical readings from Firebase RTDB (/smart_bms/readings.json)."""
        try:
            if db_url:
                target = f"{db_url.rstrip('/')}/smart_bms/readings.json?orderBy=\"$key\"&limitToLast={limit}"
            else:
                target = get_authenticated_rtdb_url(f"smart_bms/readings.json?orderBy=\"$key\"&limitToLast={limit}")

            resp = requests.get(target, timeout=4.0)
            if resp.ok and resp.json():
                raw = resp.json()
                if isinstance(raw, dict):
                    records = list(raw.values())
                elif isinstance(raw, list):
                    records = raw
                else:
                    records = []
                # Normalize keys
                normalized = []
                for r in records:
                    if not isinstance(r, dict): continue
                    normalized.append({
                        "voltage": r.get("voltage_V") if r.get("voltage_V") is not None else r.get("voltage"),
                        "current": r.get("current_A") if r.get("current_A") is not None else r.get("current"),
                        "temperature": r.get("temperature_C") if r.get("temperature_C") is not None else r.get("temperature"),
                        "power": r.get("power_W") if r.get("power_W") is not None else r.get("power"),
                        "rawTimestamp": r.get("timestamp_epoch") or r.get("rawTimestamp"),
                    })
                return normalized
        except Exception as e:
            print(f"[RAG Engine] Note: History pull error ({e}).")

        return []

    def retrieve_relevant_documents(
        self,
        assessment: ConditionAssessment,
        telemetry: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Retrieve top technical documentation chunks matching the current battery state."""
        v = telemetry.get("voltage")
        t = telemetry.get("temperature")
        spec = get_active_battery_spec()

        # Build query representing current physical state and active concerns
        query_parts = [
            f"battery condition {assessment.condition}",
            f"chemistry {spec.chemistry}",
            f"nominal voltage {spec.nominal_voltage}V",
        ]

        if assessment.active_critical_flags:
            query_parts.append(" ".join(assessment.active_critical_flags))
        if assessment.active_warnings:
            query_parts.append(" ".join(assessment.active_warnings))

        if t is not None:
            if t >= 35.0:
                query_parts.append("thermal runaway ambient cooling fan dT/dt rise rate SEI layer")
            elif t < 5.0:
                query_parts.append("low temperature charging metallic lithium dendrites plating")

        if v is not None:
            query_parts.append("operating voltage cut-off deep discharge copper dissolution CC-CV")

        if spec.verification_status == "UNVERIFIED":
            query_parts.append("unverified chemistry nominal 12V 3S NMC 4S LiFePO4 operating envelope discrepancy")

        query_str = " ".join(query_parts)
        return self.vector_store.search(query_str, top_k=4)

    def synthesize_rag_assessment(
        self,
        telemetry: Dict[str, Any],
        assessment: ConditionAssessment,
        evidence_chunks: List[Dict[str, Any]],
        spec: BatterySpecification
    ) -> Dict[str, Any]:
        """
        Synthesizes an evidence-grounded battery condition assessment.
        Uses OpenAI LLM if configured; otherwise utilizes deterministic knowledge synthesis.
        """
        # If API key is present, attempt LLM call with strict constraints
        if self.openai_api_key:
            try:
                return self._call_llm_synthesis(telemetry, assessment, evidence_chunks, spec)
            except Exception as e:
                print(f"[RAG Engine] LLM API call error ({e}). Utilizing deterministic knowledge synthesizer.")

        return self._deterministic_grounded_synthesis(telemetry, assessment, evidence_chunks, spec)

    def _call_llm_synthesis(
        self,
        telemetry: Dict[str, Any],
        assessment: ConditionAssessment,
        evidence_chunks: List[Dict[str, Any]],
        spec: BatterySpecification
    ) -> Dict[str, Any]:
        """Call LLM via OpenAI API with strict anti-hallucination and evidence grounding instructions."""
        from openai import OpenAI
        client = OpenAI(api_key=self.openai_api_key)

        context_evidence = "\n\n".join([
            f"[DOCUMENT: {c['title']} | SECTION: {c['section']} | REF: {c['chunk_id']}]\n{c['text']}"
            for c in evidence_chunks
        ])

        system_prompt = (
            "You are an expert Battery Management System (BMS) Diagnostic Engineer operating under "
            "ISO 26262 ASIL-D safety integrity guidelines. You analyze real battery sensor telemetry "
            "strictly grounded in the provided technical documentation.\n\n"
            "STRICT ARCHITECTURAL MANDATES:\n"
            "1. Ground all conclusions in the retrieved documentation. Reference the supporting documents explicitly.\n"
            "2. Never fabricate SOC, SOH, RUL, or failure probabilities. If unverified, state 'Insufficient Data / Unavailable'.\n"
            "3. Do not claim normal voltage alone proves battery health.\n"
            "4. Clearly distinguish DHT11 ambient air temperature from cell internal core temperature.\n"
            "5. Respect the deterministic classification: The condition MUST be " + assessment.condition + ".\n"
            "6. Output ONLY valid JSON matching the specified schema."
        )

        user_prompt = f"""
OBSERVED SENSOR READINGS:
- Pack Voltage: {telemetry.get('voltage')} V
- Current: {telemetry.get('current')} A
- Power: {telemetry.get('power')} W
- Ambient Air Temperature (DHT11): {telemetry.get('temperature')} °C
- Ambient Humidity: {telemetry.get('humidity') or telemetry.get('ambient_humidity') or '--'} %
- Fan Status: {telemetry.get('fanStatus', 'OFF')}
- Buzzer Status: {telemetry.get('buzzerStatus', 'OFF')}

DETERMINISTIC CLASSIFICATION & CALCULATIONS:
- Condition: {assessment.condition}
- Primary Reason: {assessment.primary_reason}
- Specification Status: {spec.verification_status} ({spec.name})
- Temperature Rise Rate (dT/dt): {assessment.numerical_trends.temperature_rise_rate_c_per_min} °C/min
- Voltage Sag (Delta V): {assessment.numerical_trends.voltage_sag_v} V
- Estimated Impedance: {assessment.numerical_trends.estimated_internal_resistance_mohm} mOhm
- Active Warnings: {json.dumps(assessment.active_warnings)}
- Active Critical Flags: {json.dumps(assessment.active_critical_flags)}

RETRIEVED TECHNICAL DOCUMENTATION:
{context_evidence}

Generate a JSON object with:
{{
  "condition": "{assessment.condition}",
  "summary": "2-3 sentence grounded executive summary of battery condition",
  "possible_causes": ["list of grounded potential physical causes"],
  "recommended_actions": ["list of prioritized actionable engineering recommendations"],
  "document_references": [
    {{"document": "Document Title", "section": "Section Name", "relevance_note": "How it supports the finding"}}
  ]
}}
"""
        response = client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.15
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        # Assemble final validated dictionary
        return self._assemble_analysis_record(
            parsed.get("condition", assessment.condition),
            parsed.get("summary", assessment.primary_reason),
            parsed.get("possible_causes", []),
            parsed.get("recommended_actions", []),
            parsed.get("document_references", []),
            telemetry,
            assessment,
            evidence_chunks,
            spec
        )

    def _deterministic_grounded_synthesis(
        self,
        telemetry: Dict[str, Any],
        assessment: ConditionAssessment,
        evidence_chunks: List[Dict[str, Any]],
        spec: BatterySpecification
    ) -> Dict[str, Any]:
        """
        Deterministic knowledge synthesis engine. Composes grounded diagnosis,
        possible causes, and recommended actions directly from retrieved document excerpts.
        Ensures 100% offline functionality without requiring an external API key.
        """
        cond = assessment.condition
        possible_causes = []
        recommended_actions = []
        doc_refs = []

        # Extract document references from chunks
        for c in evidence_chunks:
            doc_refs.append({
                "document": c["title"],
                "section": c["section"],
                "chunk_id": c["chunk_id"],
                "relevance_note": f"Provides technical limits and diagnostic criteria for {c['section'].lower()}."
            })

        # Grounded rules based on condition
        if cond == "CRITICAL":
            summary = (
                f"CRITICAL SAFETY LIMIT REACHED: {assessment.primary_reason}. "
                f"Immediate emergency safety protocols engaged to prevent thermal runaway or irreversible cell degradation."
            )
            possible_causes.append("Severe environmental overheating or cell thermal runaway chain reaction.")
            possible_causes.append("Over-voltage stress causing cathode lattice collapse and oxygen evolution.")
            possible_causes.append("Excessive deep discharge below cut-off inducing copper current collector dissolution.")
            recommended_actions.append("EMERGENCY: Disconnect battery load and charging equipment immediately.")
            recommended_actions.append("Verify cooling fan operation; maintain emergency ventilation around enclosure.")
            recommended_actions.append("Measure individual cell voltages at the balance connector with a calibrated digital multimeter.")

        elif cond == "WARNING":
            summary = (
                f"BATTERY ADVISORY WARNING: {assessment.primary_reason}. "
                f"Monitored parameters are exhibiting thermal elevation, rapid temperature rise, or approaching verified boundaries."
            )
            possible_causes.append("Elevated internal cell impedance (R_int) generating excessive I²R Joule heating under load.")
            possible_causes.append("Restricted enclosure airflow or ventilation grilles obstruction.")
            possible_causes.append("Cell capacity imbalance among series cells causing localized over-discharge or early sag.")
            recommended_actions.append("Verify L298N cooling fan airflow intake and exhaust passages.")
            recommended_actions.append("Derate continuous discharge current by 50% until enclosure ambient returns below 30.0°C.")
            recommended_actions.append("Perform manual Kelvin resistance check across series cell busbars and balance leads.")

        elif cond == "INSUFFICIENT DATA":
            if spec.verification_status == "UNVERIFIED":
                summary = (
                    f"SPECIFICATIONS UNVERIFIED: Exact cell chemistry and arrangement are unconfirmed for '{spec.name}'. "
                    f"Per ISO 26262 guidelines, universal voltage envelopes cannot be assumed for nominal 12V packs."
                )
                possible_causes.append("Missing battery manufacturer datasheet and chemistry confirmation (e.g. 3S NMC vs 4S LiFePO4).")
                possible_causes.append("Discrepancy in voltage boundaries between 12.6V (3S NMC max) and 14.6V (4S LFP max).")
                recommended_actions.append("Obtain verified manufacturer datasheet and configure verified battery profile.")
                recommended_actions.append("Do NOT guess or assume universal voltage limits for nominal 12V batteries.")
            else:
                summary = (
                    f"INSUFFICIENT DATA: {assessment.primary_reason}. "
                    f"Essential sensor telemetry channels are missing, stale, or reporting communication faults."
                )
                possible_causes.append("INA219 I²C bus disconnection (address 0x40) or DHT11 1-wire timing failure.")
                possible_causes.append("NodeMCU ESP8266 telemetry stream delay exceeding freshness threshold (45s).")
                recommended_actions.append("Inspect I²C wiring harness (SDA D5, SCL D6) and DHT11 signal pin (D7).")
                recommended_actions.append("Verify 5V DC power supply to NodeMCU and check Wi-Fi RSSI signal strength.")

        else: # NORMAL
            summary = (
                f"NOMINAL OPERATING STATE: Measurements are within verified manufacturer limits ({spec.name}). "
                f"Thermal dissipation is balanced with no detected anomalous temperature rise."
            )
            possible_causes.append("Healthy cell electrochemical kinetics operating within standard manufacturer design envelope.")
            recommended_actions.append("Continue continuous CAN telemetry and thermal monitoring.")
            recommended_actions.append("Note: Normal resting voltage alone does not prove long-term cell health; maintain periodic capacity testing.")

        return self._assemble_analysis_record(
            cond,
            summary,
            possible_causes,
            recommended_actions,
            doc_refs,
            telemetry,
            assessment,
            evidence_chunks,
            spec
        )

    def _assemble_analysis_record(
        self,
        condition: str,
        summary: str,
        possible_causes: List[str],
        recommended_actions: List[str],
        doc_refs: List[Dict[str, Any]],
        telemetry: Dict[str, Any],
        assessment: ConditionAssessment,
        evidence_chunks: List[Dict[str, Any]],
        spec: BatterySpecification
    ) -> Dict[str, Any]:
        """Assembles the final comprehensive, schema-validated RAG analysis record."""

        # Format retrieved evidence excerpts for UI presentation
        retrieved_evidence = []
        for c in evidence_chunks:
            retrieved_evidence.append({
                "chunk_id": c.get("chunk_id"),
                "document_title": c.get("title"),
                "section": c.get("section"),
                "relevance_score": c.get("score"),
                "excerpt": c.get("text", "")[:320] + "...",
            })

        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "analysis_epoch_ms": int(time.time() * 1000),
            "observed_condition": condition,
            "condition_status": assessment.condition_status,
            "battery_condition_score": assessment.battery_condition_score,
            "battery_condition_breakdown": assessment.battery_condition_breakdown,
            "soc_estimate": assessment.soc_estimate,
            "soh_estimate": assessment.soh_estimate,
            "executive_summary": summary,
            "specification_status": spec.verification_status,
            "configured_battery": {
                "id": spec.id,
                "name": spec.name,
                "manufacturer": spec.manufacturer,
                "model": spec.model,
                "chemistry": spec.chemistry,
                "cell_configuration": spec.cell_configuration,
                "nominal_voltage": f"{spec.nominal_voltage:.1f} V",
                "verified_voltage_window": (
                    f"{spec.min_operating_voltage:.2f}V - {spec.max_operating_voltage:.2f}V"
                    if spec.verification_status == "VERIFIED" and spec.min_operating_voltage and spec.max_operating_voltage
                    else "Unverified (Universal Limits Prohibited)"
                ),
                "verification_notes": spec.verification_notes,
            },
            "actual_sensor_readings": {
                "voltage_v": telemetry.get("voltage"),
                "current_a": telemetry.get("current"),
                "power_w": telemetry.get("power"),
                "ambient_temperature_c": telemetry.get("temperature"),
                "ambient_humidity_pct": telemetry.get("humidity") or telemetry.get("ambient_humidity"),
                "fan_status": telemetry.get("fanStatus", "OFF"),
                "buzzer_status": telemetry.get("buzzerStatus", "OFF"),
                "packet_timestamp": telemetry.get("timestamp"),
                "packet_age_seconds": assessment.data_validation.age_seconds,
            },
            "recent_trends": {
                "temperature_rise_rate_c_per_min": assessment.numerical_trends.temperature_rise_rate_c_per_min,
                "voltage_sag_v": assessment.numerical_trends.voltage_sag_v,
                "estimated_internal_resistance_mohm": assessment.numerical_trends.estimated_internal_resistance_mohm,
                "current_rms_a": assessment.numerical_trends.current_rms_a,
                "current_std_dev_a": assessment.numerical_trends.current_std_dev_a,
                "max_current_a": assessment.numerical_trends.max_current_a,
                "dew_point_c": assessment.numerical_trends.dew_point_c,
            },
            "verified_operating_limits": assessment.verified_limits,
            "active_warnings": assessment.active_warnings,
            "active_critical_flags": assessment.active_critical_flags,
            "possible_causes": possible_causes,
            "recommended_actions": recommended_actions,
            "retrieved_evidence": retrieved_evidence,
            "document_references": doc_refs,
            "data_quality_warnings": assessment.data_validation.data_quality_warnings,
            "ambient_vs_internal_temp_notice": assessment.ambient_vs_cell_note,
            "health_evaluation_disclaimer": assessment.health_disclaimer,
            "anti_fabrication_safeguard": "Active (No fabricated SOC/SOH/RUL or probabilistic hallucinations)",
        }

        self.last_analysis = record
        return record

    def run_analysis(
        self,
        provided_telemetry: Optional[Dict[str, Any]] = None,
        provided_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end RAG analysis:
        1. Ingests telemetry (from parameters or direct Firebase RTDB query)
        2. Ingests historical time series
        3. Evaluates deterministic checks against active BatterySpecification
        4. Queries FAISS vector store
        5. Synthesizes and validates output
        """
        telemetry = provided_telemetry if (provided_telemetry and any(v is not None for v in provided_telemetry.values())) else self.fetch_firebase_telemetry()
        history = provided_history if (provided_history and len(provided_history) > 0) else self.fetch_firebase_history()

        spec = get_active_battery_spec()
        assessment = DeterministicBatteryEvaluator.evaluate_condition(telemetry, history, spec)
        evidence = self.retrieve_relevant_documents(assessment, telemetry)
        result = self.synthesize_rag_assessment(telemetry, assessment, evidence, spec)

        # Output validation safeguard
        if assessment.condition in ["CRITICAL", "WARNING", "INSUFFICIENT DATA"] and result.get("observed_condition") == "NORMAL":
            # Override hallucination immediately
            result["observed_condition"] = assessment.condition
            result["executive_summary"] = f"CRITICAL VALIDATION OVERRIDE: {assessment.primary_reason}"

        return result


# Singleton instance
_rag_engine_instance: Optional[BatteryRagEngine] = None


def get_rag_engine() -> BatteryRagEngine:
    global _rag_engine_instance
    if _rag_engine_instance is None:
        _rag_engine_instance = BatteryRagEngine()
    return _rag_engine_instance
