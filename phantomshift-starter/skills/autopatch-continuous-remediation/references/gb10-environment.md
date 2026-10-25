# Dell Pro Max GB10 Environment & Air-Gap Matrix

## 1. Hardware Architecture
- **Target Node**: Dell Pro Max GB10
- **CPU Architecture**: ARM64 (`aarch64`), Grace Blackwell
- **GPU Architecture**: NVIDIA GB10 with Unified Memory Architecture
- **Operating Mode**: Air-gapped / Local-only (zero remote API calls permitted in competition mode)

## 2. Port Allocation
- `8765`: PHANTOMSHIFT Dashboard & 2D BLACKSITE UI (`/payguard/` and `/`)
- `7890`: PHANTOMSHIFT Tool Firewall Listener (`adapter_server.py`)
- `8000`: Local vLLM Inference Server (`/v1/chat/completions`)
- `11434`: Local Ollama Server (Fallback)
- `172.18.0.1:8080`: NemoClaw Docker Bridge Network (requires rootful Docker daemon)

## 3. Local Model Hierarchy
1. **NVIDIA Nemotron 3.5 Lightning 30B NVFP4** (`offline-stage/models/nemotron-3.5-lightning-30b-a3b-nvfp4`):
   - Primary model for root-cause diagnosis, explanation, and minimal candidate policy generation.
2. **NVIDIA Nemotron 3 Nano 4B FP8** (`offline-stage/models/nemotron-3-nano-4b-fp8`):
   - Lightweight triage model for fast local checks.
3. **Deterministic Evaluator**:
   - The absolute authority. LLM outputs are candidates only and must pass deterministic validation before simulation.
