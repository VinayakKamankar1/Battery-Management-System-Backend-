"""
Automated Test Suite for Smart BMS RAG Battery Health Analysis
Verifies:
1. Telemetry validation & stale/missing data detection
2. Deterministic condition assessment across Unverified and Verified specifications
3. Vector store indexing & Top-K document retrieval with citations
4. End-to-end RAG synthesis & output schema compliance
5. Anti-fabrication & safety integrity guardrails
"""

import unittest
import time
from deterministic_evaluator import DeterministicBatteryEvaluator
from battery_config import set_active_battery_profile, get_active_battery_spec
from vector_store import get_vector_store
from rag_engine import get_rag_engine


class TestSmartBmsRag(unittest.TestCase):

    def setUp(self):
        # Reset to unverified profile for clean test isolation
        set_active_battery_profile("unverified_12v")

    def test_01_telemetry_validation_missing_and_stale(self):
        """Verify that missing fields and stale packets are flagged deterministically."""
        # Test missing telemetry
        res_empty = DeterministicBatteryEvaluator.validate_telemetry({})
        self.assertFalse(res_empty.is_valid)
        self.assertTrue(res_empty.is_stale)
        self.assertTrue(any("voltage" in f for f in res_empty.missing_fields))
        self.assertTrue(any("current" in f for f in res_empty.missing_fields))
        self.assertTrue(any("temperature" in f for f in res_empty.missing_fields))

        # Test stale telemetry (older than 45 seconds)
        old_epoch = (time.time() - 90) * 1000
        stale_data = {
            "voltage": 12.1,
            "current": 2.5,
            "power": 30.25,
            "temperature": 27.5,
            "rawTimestamp": old_epoch
        }
        res_stale = DeterministicBatteryEvaluator.validate_telemetry(stale_data)
        self.assertTrue(res_stale.is_stale)
        self.assertFalse(res_stale.is_valid)
        self.assertTrue(any("stale" in w.lower() for w in res_stale.data_quality_warnings))

        # Test valid and fresh telemetry
        fresh_epoch = (time.time() - 2) * 1000
        fresh_data = {
            "voltage": 12.1,
            "current": 2.5,
            "power": 30.25,
            "temperature": 27.5,
            "rawTimestamp": fresh_epoch
        }
        res_fresh = DeterministicBatteryEvaluator.validate_telemetry(fresh_data)
        self.assertTrue(res_fresh.is_valid)
        self.assertFalse(res_fresh.is_stale)

    def test_02_unverified_specs_yields_insufficient_data(self):
        """When battery chemistry is unverified, condition must be INSUFFICIENT DATA."""
        set_active_battery_profile("unverified_12v")
        fresh_epoch = (time.time() - 2) * 1000
        telemetry = {
            "voltage": 12.2,
            "current": 2.0,
            "power": 24.4,
            "temperature": 26.0,
            "rawTimestamp": fresh_epoch
        }
        assessment = DeterministicBatteryEvaluator.evaluate_condition(telemetry, [])
        self.assertEqual(assessment.condition, "INSUFFICIENT DATA")
        self.assertIn("unverified", assessment.primary_reason.lower())
        self.assertEqual(assessment.specification_status, "UNVERIFIED")

    def test_03_verified_specs_normal_condition(self):
        """When specifications are verified and readings are within limits, condition is NORMAL."""
        set_active_battery_profile("verified_3s_nmc")
        fresh_epoch = (time.time() - 2) * 1000
        telemetry = {
            "voltage": 11.85,
            "current": 2.0,
            "power": 23.7,
            "temperature": 27.0,
            "rawTimestamp": fresh_epoch
        }
        assessment = DeterministicBatteryEvaluator.evaluate_condition(telemetry, [])
        self.assertEqual(assessment.condition, "NORMAL")
        self.assertIn("verified", assessment.primary_reason.lower())
        self.assertIn("A normal voltage reading alone DOES NOT prove the battery is healthy", assessment.health_disclaimer)

    def test_04_thermal_warning_and_critical_trips(self):
        """Verify temperature threshold logic (≥ 35.0°C warning, ≥ 60.0°C critical)."""
        set_active_battery_profile("verified_3s_nmc")
        fresh_epoch = (time.time() - 2) * 1000

        # Warning test (37°C)
        telemetry_warn = {
            "voltage": 11.8,
            "current": 2.0,
            "power": 23.6,
            "temperature": 37.0,
            "rawTimestamp": fresh_epoch
        }
        assess_warn = DeterministicBatteryEvaluator.evaluate_condition(telemetry_warn, [])
        self.assertEqual(assess_warn.condition, "WARNING")
        self.assertTrue(any("37.0°c" in w.lower() for w in assess_warn.active_warnings))

        # Critical test (63°C)
        telemetry_crit = {
            "voltage": 11.8,
            "current": 2.0,
            "power": 23.6,
            "temperature": 63.0,
            "rawTimestamp": fresh_epoch
        }
        assess_crit = DeterministicBatteryEvaluator.evaluate_condition(telemetry_crit, [])
        self.assertEqual(assess_crit.condition, "CRITICAL")
        self.assertTrue(any("over-temperature" in f.lower() for f in assess_crit.active_critical_flags))

    def test_05_voltage_boundary_violations(self):
        """Verify upper charge and lower discharge violations against verified 3S NMC."""
        set_active_battery_profile("verified_3s_nmc")
        fresh_epoch = (time.time() - 2) * 1000

        # Over-voltage test (12.85V on 3S NMC, max is 12.60V)
        telemetry_ovp = {
            "voltage": 12.85,
            "current": 1.0,
            "power": 12.85,
            "temperature": 26.0,
            "rawTimestamp": fresh_epoch
        }
        assess_ovp = DeterministicBatteryEvaluator.evaluate_condition(telemetry_ovp, [])
        self.assertEqual(assess_ovp.condition, "CRITICAL")
        self.assertTrue(any("over-voltage" in f.lower() for f in assess_ovp.active_critical_flags))

        # Under-voltage test (8.70V on 3S NMC, cutoff is 9.00V)
        telemetry_uvp = {
            "voltage": 8.70,
            "current": 2.0,
            "power": 17.4,
            "temperature": 26.0,
            "rawTimestamp": fresh_epoch
        }
        assess_uvp = DeterministicBatteryEvaluator.evaluate_condition(telemetry_uvp, [])
        self.assertEqual(assess_uvp.condition, "CRITICAL")
        self.assertTrue(any("under-voltage" in f.lower() for f in assess_uvp.active_critical_flags))

    def test_06_vector_store_retrieval_and_citations(self):
        """Verify FAISS / vector store indexes technical documents and retrieves citations."""
        vs = get_vector_store()
        self.assertGreater(len(vs.chunks), 0)

        results = vs.search("thermal runaway SEI decomposition temperature", top_k=3)
        self.assertEqual(len(results), 3)
        top_match = results[0]
        self.assertIn("chunk_id", top_match)
        self.assertIn("title", top_match)
        self.assertIn("section", top_match)
        self.assertIn("text", top_match)
        self.assertGreater(top_match.get("score", 0), 0)

    def test_07_rag_engine_end_to_end_analysis(self):
        """Verify full RAG analysis produces all required user-specified fields."""
        set_active_battery_profile("verified_4s_lifepo4")
        fresh_epoch = (time.time() - 2) * 1000
        telemetry = {
            "voltage": 13.25,
            "current": 3.1,
            "power": 41.07,
            "temperature": 28.4,
            "humidity": 45.0,
            "fanStatus": "OFF",
            "buzzerStatus": "OFF",
            "rawTimestamp": fresh_epoch
        }

        engine = get_rag_engine()
        result = engine.run_analysis(provided_telemetry=telemetry, provided_history=[])

        # Verify all required output fields
        self.assertEqual(result["observed_condition"], "NORMAL")
        self.assertIn("actual_sensor_readings", result)
        self.assertIn("recent_trends", result)
        self.assertIn("verified_operating_limits", result)
        self.assertIn("active_warnings", result)
        self.assertIn("possible_causes", result)
        self.assertIn("recommended_actions", result)
        self.assertIn("retrieved_evidence", result)
        self.assertIn("data_quality_warnings", result)
        self.assertIn("timestamp", result)

        # Verify condition status and score fields
        self.assertIn("condition_status", result)
        self.assertIn("battery_condition_score", result)
        self.assertIn("soc_estimate", result)
        self.assertIn("soh_estimate", result)

    def test_08_battery_condition_score_and_statuses(self):
        """Verify documented battery condition score (0-100%) and statuses: Excellent, Good, Normal, Warning, Danger, Insufficient Data."""
        fresh_epoch = (time.time() - 2) * 1000

        # 1. Unverified profile -> Insufficient Data, score is None
        set_active_battery_profile("unverified_12v")
        t_unverified = {"voltage": 12.2, "current": 1.0, "power": 12.2, "temperature": 25.0, "rawTimestamp": fresh_epoch}
        assess_unv = DeterministicBatteryEvaluator.evaluate_condition(t_unverified, [])
        self.assertEqual(assess_unv.condition_status, "Insufficient Data")
        self.assertIsNone(assess_unv.battery_condition_score)

        # 2. Verified profile with optimal parameters -> Excellent (score >= 90)
        set_active_battery_profile("verified_3s_nmc")
        t_opt = {"voltage": 11.85, "current": 1.0, "power": 11.85, "temperature": 24.0, "rawTimestamp": fresh_epoch}
        assess_opt = DeterministicBatteryEvaluator.evaluate_condition(t_opt, [])
        self.assertIsNotNone(assess_opt.battery_condition_score)
        self.assertGreaterEqual(assess_opt.battery_condition_score, 90.0)
        self.assertEqual(assess_opt.condition_status, "Excellent")

        # 3. Verified profile with fan-trigger temperature (38°C) -> Warning status
        t_warn = {"voltage": 11.85, "current": 1.0, "power": 11.85, "temperature": 38.0, "rawTimestamp": fresh_epoch}
        assess_warn = DeterministicBatteryEvaluator.evaluate_condition(t_warn, [])
        self.assertEqual(assess_warn.condition_status, "Warning")

        # 4. Verified profile with critical temp (62°C) -> Danger status
        t_crit = {"voltage": 11.85, "current": 1.0, "power": 11.85, "temperature": 62.0, "rawTimestamp": fresh_epoch}
        assess_crit = DeterministicBatteryEvaluator.evaluate_condition(t_crit, [])
        self.assertEqual(assess_crit.condition_status, "Danger")

    def test_09_approximate_charging_percentage_soc(self):
        """Verify SOC charge percentage calculation: Unavailable when unverified, piecewise OCV when verified."""
        spec_unverified = get_active_battery_spec()
        # With unverified chemistry, must return 'Unavailable'
        set_active_battery_profile("unverified_12v")
        unv_spec = get_active_battery_spec()
        soc_unv = DeterministicBatteryEvaluator.calculate_soc_estimate(12.4, unv_spec)
        self.assertEqual(soc_unv["display_text"], "Unavailable")
        self.assertFalse(soc_unv["is_available"])
        self.assertIsNone(soc_unv["soc_percent"])

        # With verified 3S NMC at 12.45V (near 100%)
        set_active_battery_profile("verified_3s_nmc")
        nmc_spec = get_active_battery_spec()
        soc_nmc_high = DeterministicBatteryEvaluator.calculate_soc_estimate(12.45, nmc_spec)
        self.assertTrue(soc_nmc_high["is_available"])
        self.assertEqual(soc_nmc_high["soc_percent"], 95)
        self.assertEqual(soc_nmc_high["display_text"], "~95%")

        # At nominal 11.10V
        soc_nmc_mid = DeterministicBatteryEvaluator.calculate_soc_estimate(11.10, nmc_spec)
        self.assertEqual(soc_nmc_mid["soc_percent"], 50)
        self.assertEqual(soc_nmc_mid["display_text"], "~50%")

        # At cutoff 9.00V
        soc_nmc_low = DeterministicBatteryEvaluator.calculate_soc_estimate(9.00, nmc_spec)
        self.assertEqual(soc_nmc_low["soc_percent"], 0)
        self.assertEqual(soc_nmc_low["display_text"], "~0%")

        # With calibrated 12V pack profile: >=12.0V is 100% (fully charged), below 12.0V measured accurately down to 9.00V safe cutoff (0%)
        set_active_battery_profile("calibrated_12v")
        calib_spec = get_active_battery_spec()
        # >= 12.0V -> 100% (fully charged)
        soc_calib_full = DeterministicBatteryEvaluator.calculate_soc_estimate(12.00, calib_spec)
        self.assertEqual(soc_calib_full["soc_percent"], 100)
        self.assertEqual(soc_calib_full["display_text"], "~100%")

        # Above 12.0V -> 100%
        soc_calib_above = DeterministicBatteryEvaluator.calculate_soc_estimate(12.35, calib_spec)
        self.assertEqual(soc_calib_above["soc_percent"], 100)
        self.assertEqual(soc_calib_above["display_text"], "~100%")

        # Live telemetry reading 11.152V -> 72%
        soc_calib_live = DeterministicBatteryEvaluator.calculate_soc_estimate(11.152, calib_spec)
        self.assertEqual(soc_calib_live["soc_percent"], 72)
        self.assertEqual(soc_calib_live["display_text"], "~72%")

        # 9.00V cutoff -> 0%
        soc_calib_cutoff = DeterministicBatteryEvaluator.calculate_soc_estimate(9.00, calib_spec)
        self.assertEqual(soc_calib_cutoff["soc_percent"], 0)
        self.assertEqual(soc_calib_cutoff["display_text"], "~0%")

    def test_10_soh_separation_and_non_fabrication(self):
        """Verify that State of Health (SOH) is strictly NOT calculated from voltage alone."""
        set_active_battery_profile("verified_3s_nmc")
        fresh_epoch = (time.time() - 2) * 1000
        telemetry = {"voltage": 12.2, "current": 1.0, "power": 12.2, "temperature": 25.0, "rawTimestamp": fresh_epoch}
        assess = DeterministicBatteryEvaluator.evaluate_condition(telemetry, [])
        self.assertIsNone(assess.soh_estimate["soh_percent"])
        self.assertEqual(assess.soh_estimate["display_text"], "Unavailable")
        self.assertIn("cannot be calculated from instantaneous voltage alone", assess.soh_estimate["explanation"])

    def test_11_firebase_live_data_retrieval(self):
        """Verify that live sensor readings are retrieved from Firebase RTDB with auth."""
        engine = get_rag_engine()
        live_telemetry = engine.fetch_firebase_telemetry()
        # Verify essential physical telemetry keys are present
        self.assertIn("voltage", live_telemetry)
        self.assertIn("current", live_telemetry)
        self.assertIn("power", live_telemetry)
        self.assertIn("temperature", live_telemetry)
        # Verify that actual numeric readings are populated from the live database
        self.assertIsNotNone(live_telemetry.get("voltage"))
        self.assertIsNotNone(live_telemetry.get("temperature"))


if __name__ == "__main__":
    unittest.main()
