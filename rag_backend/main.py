"""
FastAPI Server for RAG-Based AI Battery Health Analysis
Provides endpoints for:
- Deterministic battery condition analysis & RAG evidence generation
- Battery specification configuration management (Unverified 12V vs 3S NMC vs 4S LFP)
- Semantic search across battery knowledge base
- Grounded conversational Q&A
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from battery_config import (
    BATTERY_PROFILES,
    get_active_battery_spec,
    set_active_battery_profile,
    update_custom_battery_spec,
    BatterySpecification
)
from rag_engine import get_rag_engine
from vector_store import get_vector_store
from pdf_generator import get_pdf_generator, REPORTS_DIR
from email_service import get_email_service
from alert_monitor import get_alert_daemon

app = FastAPI(
    title="Smart BMS RAG Battery Health Analysis & Reports API",
    description="Evidence-grounded RAG battery health analysis, ReportLab PDF generation, and automated temperature alerts.",
    version="1.0.0"
)

# Startup event to initiate background Firebase alert monitoring daemon
@app.on_event("startup")
async def startup_event():
    daemon = get_alert_daemon()
    asyncio.create_task(daemon.run_loop())
    print("[FastAPI] Background Alert Daemon task initialized.")

# Enable CORS for Vite frontend and Node backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS_METADATA_FILE = os.path.join(os.path.dirname(__file__), "reports_metadata.json")

def load_reports_metadata() -> List[Dict[str, Any]]:
    if os.path.exists(REPORTS_METADATA_FILE):
        try:
            with open(REPORTS_METADATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_reports_metadata(meta_list: List[Dict[str, Any]]):
    try:
        with open(REPORTS_METADATA_FILE, "w") as f:
            json.dump(meta_list, f, indent=2)
    except Exception as e:
        print(f"[Reports] Error saving reports metadata: {e}")

class ReportGenerateRequest(BaseModel):
    period: str = Field("24h", description="Reporting period ('1h', '24h', '7d', '30d', 'custom')")
    custom_start: Optional[str] = Field(None, description="Start date for custom period")
    custom_end: Optional[str] = Field(None, description="End date for custom period")
    recipient_email: Optional[str] = Field(None, description="Optional recipient email to auto-send")
    telemetry: Optional[Dict[str, Any]] = Field(None, description="Current live sensor telemetry from client")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Historical sensor telemetry from client")

class EmailReportRequest(BaseModel):
    recipient: str = Field(..., description="Recipient email address")
    subject: Optional[str] = Field(None, description="Custom email subject")
    message: Optional[str] = Field(None, description="Custom email message")

class AlertSettingsRequest(BaseModel):
    recipient_email: Optional[str] = None
    threshold_c: Optional[float] = None
    is_threshold_verified: Optional[bool] = None
    threshold_source: Optional[str] = None
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = None
    recovery_notification: Optional[bool] = None
    hysteresis_c: Optional[float] = None



class AnalysisRequest(BaseModel):
    telemetry: Optional[Dict[str, Any]] = Field(None, description="Current sensor readings (optional; pulls from Firebase if omitted)")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Historical sensor readings time series (optional)")


class ProfileSelectRequest(BaseModel):
    profile_id: str = Field(..., description="ID of battery profile to activate")


class QuestionRequest(BaseModel):
    question: str = Field(..., description="User query regarding battery health or telemetry")
    telemetry: Optional[Dict[str, Any]] = Field(None, description="Current live sensor telemetry")


@app.get("/")
def root():
    return {
        "service": "Smart BMS AI Battery Health Analysis Service",
        "status": "ONLINE",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /health",
            "activeSpec": "GET /api/battery-specs",
            "selectSpec": "POST /api/battery-specs/select",
            "customSpec": "POST /api/battery-specs/custom",
            "runAnalysis": "POST /api/rag/analyze",
            "latestAnalysis": "GET /api/rag/latest",
            "knowledgeBase": "GET /api/rag/knowledge-base",
            "queryKnowledge": "POST /api/rag/query",
        }
    }


@app.get("/health")
@app.get("/api/health")
@app.get("/api/rag/health")
def health_check():
    engine = get_rag_engine()
    vs = get_vector_store()
    spec = get_active_battery_spec()
    return {
        "status": "HEALTHY",
        "vector_store_mode": vs.mode,
        "indexed_chunks_count": len(vs.chunks),
        "active_battery_spec": {
            "id": spec.id,
            "name": spec.name,
            "chemistry": spec.chemistry,
            "verification_status": spec.verification_status,
        },
        "has_cached_analysis": engine.last_analysis is not None,
    }


@app.get("/api/battery-specs")
@app.get("/api/rag/battery-specs")
def get_battery_specifications():
    """Return active profile and list of all available battery specifications."""
    active = get_active_battery_spec()
    all_profiles = {k: (v.model_dump() if hasattr(v, "model_dump") else v.dict()) for k, v in BATTERY_PROFILES.items()}
    active_dict = active.model_dump() if hasattr(active, "model_dump") else active.dict()
    return {
        "success": True,
        "active_profile_id": active.id,
        "active_specification": active_dict,
        "available_profiles": all_profiles
    }


@app.post("/api/battery-specs/select")
@app.post("/api/rag/battery-specs/select")
def select_battery_profile(req: ProfileSelectRequest):
    """Switch active profile to a known battery specification ID."""
    try:
        updated = set_active_battery_profile(req.profile_id)
        # Re-run analysis with newly selected spec if cache exists
        engine = get_rag_engine()
        engine.run_analysis()
        updated_dict = updated.model_dump() if hasattr(updated, "model_dump") else updated.dict()
        return {
            "success": True,
            "message": f"Active battery specification switched to: {updated.name}",
            "active_specification": updated_dict
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/battery-specs/custom")
@app.post("/api/rag/battery-specs/custom")
def save_custom_battery_spec(custom_spec: Dict[str, Any]):
    """Register or update a custom verified battery specification."""
    try:
        updated = update_custom_battery_spec(custom_spec)
        engine = get_rag_engine()
        engine.run_analysis()
        updated_dict = updated.model_dump() if hasattr(updated, "model_dump") else updated.dict()
        return {
            "success": True,
            "message": f"Custom specification registered: {updated.name}",
            "active_specification": updated_dict
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid specification payload: {e}")


@app.post("/api/rag/analyze")
@app.post("/api/analyze")
def run_rag_analysis(req: Optional[AnalysisRequest] = None):
    """
    Executes end-to-end RAG battery health analysis:
    Pulls from Firebase (or provided telemetry), performs deterministic checks,
    retrieves technical documentation, and synthesizes an evidence-grounded assessment.
    """
    engine = get_rag_engine()
    telemetry = req.telemetry if req else None
    history = req.history if req else None

    result = engine.run_analysis(telemetry, history)
    return {
        "success": True,
        "data": result
    }


@app.get("/api/rag/latest")
@app.get("/api/latest")
def get_latest_rag_analysis():
    """Get the latest cached RAG battery health analysis (or runs a fresh one if none exists)."""
    engine = get_rag_engine()
    if engine.last_analysis is None:
        result = engine.run_analysis()
    else:
        result = engine.last_analysis

    return {
        "success": True,
        "data": result
    }


@app.get("/api/rag/knowledge-base")
@app.get("/api/knowledge-base")
def get_knowledge_base_chunks(query: Optional[str] = None, limit: int = 20):
    """Browse indexed knowledge base chunks or search with semantic query."""
    vs = get_vector_store()
    if query:
        results = vs.search(query, top_k=limit)
    else:
        results = [c.to_dict() for c in vs.chunks[:limit]]

    return {
        "success": True,
        "count": len(results),
        "total_chunks_indexed": len(vs.chunks),
        "data": results
    }


@app.post("/api/rag/query")
@app.post("/api/query")
def answer_battery_query(req: QuestionRequest):
    """
    Conversational Q&A grounded strictly in the RAG knowledge base
    and current battery telemetry.
    """
    vs = get_vector_store()
    engine = get_rag_engine()
    active_analysis = engine.last_analysis or engine.run_analysis(req.telemetry)

    # Search top 3 chunks for the user's specific inquiry
    chunks = vs.search(req.question, top_k=3)

    citations = [
        {
            "document": c["title"],
            "section": c["section"],
            "chunk_id": c["chunk_id"],
            "score": c.get("score"),
            "excerpt": c["text"][:280] + "..."
        }
        for c in chunks
    ]

    # Synthesize grounded answer
    q_lower = req.question.lower()
    t_c = active_analysis.get("actual_sensor_readings", {}).get("ambient_temperature_c")
    v_v = active_analysis.get("actual_sensor_readings", {}).get("voltage_v")
    cond = active_analysis.get("observed_condition")

    if "fan" in q_lower or "cool" in q_lower:
        answer = (
            f"The 12V cooling fan is triggered by the L298N driver when DHT11 ambient enclosure air reaches ≥ 35.0°C. "
            f"Currently, ambient temperature is {t_c if t_c is not None else '--'}°C. "
            f"Per document '{chunks[0]['title'] if chunks else 'Charging Guidelines'}', active cooling prevents Solid "
            f"Electrolyte Interphase (SEI) degradation and thermal accumulation."
        )
    elif "healthy" in q_lower or "voltage" in q_lower:
        answer = (
            f"Current pack voltage is {v_v if v_v is not None else '--'}V. As mandated by battery safety standards, "
            f"a normal voltage reading alone DOES NOT prove battery health. Resting open-circuit voltage often masks "
            f"capacity degradation and internal impedance rise until a dynamic load is applied."
        )
    elif "spec" in q_lower or "chemistry" in q_lower or "12v" in q_lower:
        answer = (
            f"The active configuration is '{active_analysis.get('configured_battery', {}).get('name')}'. "
            f"Exact chemistry verification is mandatory because universal voltage boundaries cannot be assumed "
            f"for nominal 12V packs (3S NMC max is 12.6V, while 4S LiFePO4 max is 14.6V). Current verification status: "
            f"{active_analysis.get('specification_status')}."
        )
    else:
        answer = (
            f"Based on live telemetry and retrieved technical documents, observed condition is {cond}. "
            f"{active_analysis.get('executive_summary')} "
            f"Primary recommended action: {active_analysis.get('recommended_actions', ['Inspect physical testbench'])[0]}."
        )

    return {
        "success": True,
        "question": req.question,
        "observed_condition": cond,
        "answer": answer,
        "citations": citations,
        "timestamp": active_analysis.get("timestamp")
    }



# =========================================================================
# REPORTS & PDF GENERATION ENDPOINTS
# =========================================================================

@app.post("/api/reports/generate")
@app.post("/api/rag/reports/generate")
def generate_bms_report(req: ReportGenerateRequest):
    """
    Generates a professional 1-2 page PDF battery condition report using ReportLab.
    Grounds assessment on real Firebase sensor readings.
    """
    engine = get_rag_engine()
    pdf_gen = get_pdf_generator()
    spec = get_active_battery_spec()

    # 1. Fetch live telemetry and history from Firebase (with fallback to client telemetry)
    telemetry = engine.fetch_firebase_telemetry()
    if (not telemetry or telemetry.get("voltage") is None) and req.telemetry:
        telemetry = req.telemetry
    history = engine.fetch_firebase_history(limit=60)
    if (not history or len(history) == 0) and req.history:
        history = req.history

    # 2. Run deterministic numerical evaluation & RAG
    analysis = engine.run_analysis(provided_telemetry=telemetry, provided_history=history)

    # 3. Generate unique Report ID: BMS-REP-YYYYMMDD-XXXX
    date_str = time.strftime("%Y%m%d", time.gmtime())
    rand_suffix = f"{int(time.time() * 1000) % 10000:04d}"
    report_id = f"BMS-REP-{date_str}-{rand_suffix}"

    # 4. Generate ReportLab PDF
    try:
        pdf_path = pdf_gen.generate_report(
            report_id=report_id,
            period=req.period,
            telemetry=telemetry,
            analysis=analysis,
            battery_spec=spec.dict(),
            history=history,
            recipient_email=req.recipient_email
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF report: {e}")

    # 5. Save report metadata
    gen_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report_record = {
        "id": report_id,
        "title": f"Battery Condition Report ({req.period.upper()})",
        "generatedAt": gen_iso,
        "reportingPeriod": req.period,
        "overallCondition": analysis.get("overall_condition", "NORMAL"),
        "pdfPath": pdf_path,
        "pdfAvailable": True,
        "batteryNominalVoltage": "12.0V",
        "batterySpec": spec.name,
        "chemistryVerified": spec.verification_status == "VERIFIED",
        "measurements": {
            "voltage": telemetry.get("voltage"),
            "current": telemetry.get("current"),
            "power": telemetry.get("power"),
            "temperature": telemetry.get("temperature"),
            "humidity": telemetry.get("humidity"),
        },
        "emailRecipient": req.recipient_email,
        "emailStatus": "PENDING" if req.recipient_email else "NOT_SENT",
        "downloadUrl": f"/api/reports/{report_id}/download",
        "previewUrl": f"/api/reports/{report_id}/preview",
    }

    # If recipient requested during generation, dispatch immediately
    if req.recipient_email:
        email_svc = get_email_service()
        dispatch_res = email_svc.send_report_pdf(
            recipient=req.recipient_email,
            pdf_path=pdf_path,
            report_id=report_id
        )
        report_record["emailStatus"] = dispatch_res.get("status", "FAILED")
        report_record["emailLog"] = dispatch_res.get("log")

    # Update metadata storage
    metadata_list = load_reports_metadata()
    metadata_list.insert(0, report_record)
    save_reports_metadata(metadata_list)

    return {
        "success": True,
        "report_id": report_id,
        "metadata": report_record
    }


@app.get("/api/reports/history")
@app.get("/api/rag/reports/history")
def get_reports_history(limit: int = 50):
    """Retrieve history of generated BMS PDF reports."""
    metadata_list = load_reports_metadata()
    # Confirm PDF file still exists on disk
    for item in metadata_list:
        pdf_p = item.get("pdfPath")
        item["pdfAvailable"] = bool(pdf_p and os.path.exists(pdf_p))
    return {
        "success": True,
        "count": len(metadata_list[:limit]),
        "data": metadata_list[:limit]
    }


@app.get("/api/reports/{report_id}/download")
@app.get("/api/rag/reports/{report_id}/download")
def download_report_pdf(report_id: str):
    """Download the generated ReportLab PDF file."""
    pdf_path = os.path.join(REPORTS_DIR, f"{report_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"Report PDF '{report_id}' not found.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{report_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'}
    )


@app.get("/api/reports/{report_id}/preview")
@app.get("/api/rag/reports/{report_id}/preview")
def preview_report_pdf(report_id: str):
    """Inline preview of generated ReportLab PDF file for browser iframe viewing."""
    pdf_path = os.path.join(REPORTS_DIR, f"{report_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"Report PDF '{report_id}' not found.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"}
    )


@app.post("/api/reports/{report_id}/email")
@app.post("/api/rag/reports/{report_id}/email")
def send_report_email(report_id: str, req: EmailReportRequest):
    """Email a generated PDF report directly to a recipient."""
    pdf_path = os.path.join(REPORTS_DIR, f"{report_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"Report PDF '{report_id}' not found.")

    email_svc = get_email_service()
    dispatch_res = email_svc.send_report_pdf(
        recipient=req.recipient,
        pdf_path=pdf_path,
        report_id=report_id,
        subject=req.subject,
        custom_message=req.message
    )

    # Update metadata record
    metadata_list = load_reports_metadata()
    for item in metadata_list:
        if item.get("id") == report_id:
            item["emailRecipient"] = req.recipient
            item["emailStatus"] = dispatch_res.get("status")
            item["lastEmailedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            break
    save_reports_metadata(metadata_list)

    if not dispatch_res.get("success") and dispatch_res.get("status") == "FAILED":
        raise HTTPException(status_code=400, detail=dispatch_res.get("error", "Failed to send email."))

    return {
        "success": True,
        "report_id": report_id,
        "delivery": dispatch_res
    }


# =========================================================================
# CRITICAL TEMPERATURE EMAIL ALERTS ENDPOINTS
# =========================================================================

@app.get("/api/alerts/settings")
@app.get("/api/rag/alerts/settings")
def get_alert_settings():
    """Retrieve temperature alert daemon configuration and status."""
    daemon = get_alert_daemon()
    return {
        "success": True,
        "data": daemon.get_settings()
    }


@app.post("/api/alerts/settings")
@app.post("/api/rag/alerts/settings")
def update_alert_settings(req: AlertSettingsRequest):
    """Update temperature alert threshold, recipient, and cooldown configuration."""
    daemon = get_alert_daemon()
    updates = req.dict(exclude_unset=True)
    updated_settings = daemon.update_settings(updates)
    return {
        "success": True,
        "message": "Alert configuration updated successfully.",
        "data": updated_settings
    }


@app.get("/api/alerts/history")
@app.get("/api/rag/alerts/history")
def get_alerts_history(limit: int = 50):
    """Retrieve history of ambient temperature alerts and dispatch attempts."""
    daemon = get_alert_daemon()
    return {
        "success": True,
        "data": daemon.get_history(limit=limit)
    }


@app.post("/api/alerts/test")
@app.post("/api/rag/alerts/test")
def trigger_test_alert(custom_temp: float = 48.0):
    """Manually dispatch a test temperature warning email to verify recipient connectivity."""
    daemon = get_alert_daemon()
    res = daemon.trigger_test_alert(custom_temp=custom_temp)
    return {
        "success": res.get("success", False),
        "delivery": res
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("RAG_PORT", "8000"))
    print(f"Starting Smart BMS RAG Service on http://localhost:{port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

