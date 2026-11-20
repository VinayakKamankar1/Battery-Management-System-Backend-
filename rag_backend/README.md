# Smart BMS RAG-Based AI Battery Health Analysis Service

## 1. Overview
This service implements **Retrieval-Augmented Generation (RAG)** for the Smart Battery Management System (BMS). It analyzes real sensor telemetry from a nominal 12V lithium-ion battery, identifies abnormal operating conditions, explains possible causes, and recommends evidence-grounded maintenance procedures.

### Core Architectural Principles
- **No Machine-Learning Predictions Fabricated:** Does not guess or hallucinate SOC, SOH, RUL, or probabilistic failure curves.
- **Specification-Grounded:** Universal voltage limits are never assumed for nominal 12V packs. If chemistry is unverified, condition is strictly classified as **INSUFFICIENT DATA / SPECIFICATIONS UNVERIFIED**.
- **Deterministic Numerical Checks:** Derives physical trends ($dT/dt$, $\Delta V_{\text{sag}}$, $R_{\text{int}}$, $I_{\text{rms}}$) with zero tolerance for corrupted or stale readings.
- **Evidence-Backed Citations:** Every conclusion links directly to technical documentation chunks indexed in FAISS with exact document titles and sections.
- **Ambient vs. Core Temperature:** Explicitly maintains the physical distinction between DHT11 ambient enclosure air and internal cell core temperatures.

---

## 2. Directory Structure
```
rag_backend/
├── battery_config.py           # Battery specifications (Unverified 12V, 3S NMC, 4S LiFePO4)
├── deterministic_evaluator.py  # Data validation, trend derivations, and condition classification
├── vector_store.py             # FAISS vector store with Sentence-Transformers & TF-IDF
├── rag_engine.py               # RAG ingestion, document retrieval, and grounded synthesis
├── main.py                     # FastAPI application endpoints
├── test_rag.py                 # Automated unit and integration test suite
├── knowledge_base/             # Technical battery documentation markdown files
│   ├── 01_battery_specifications_12v.md
│   ├── 02_charging_discharging_guidelines.md
│   ├── 03_thermal_safety_and_runaway.md
│   ├── 04_fault_diagnosis_procedures.md
│   └── 05_cycle_life_benchmark_degradation.md
├── requirements.txt
├── .env.example
└── README.md
```

---

## 3. Setup & Running Instructions

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Run Automated Tests
```bash
python test_rag.py
```

### Step 3: Start the RAG FastAPI Server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Or directly:
python main.py
```
Server will be accessible at: `http://localhost:8000`
API Documentation (Swagger UI): `http://localhost:8000/docs`

---

## 4. API Endpoints Reference
- `GET /health`: Service health, vector store indexing status, active battery spec.
- `GET /api/battery-specs`: Retrieve active specification and available profiles.
- `POST /api/battery-specs/select`: Switch active profile (`unverified_12v`, `verified_3s_nmc`, `verified_4s_lifepo4`).
- `POST /api/battery-specs/custom`: Register verified custom battery specification.
- `POST /api/rag/analyze`: Trigger on-demand RAG analysis.
- `GET /api/rag/latest`: Fetch latest cached RAG analysis.
- `GET /api/rag/knowledge-base`: Browse indexed knowledge chunks and citations.
- `POST /api/rag/query`: Grounded conversational Q&A with citations.
