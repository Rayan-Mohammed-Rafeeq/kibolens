# KiboLens Free-Only Multi-Provider AI Routing & Fallback System

## 1. Overview & Architecture

KiboLens uses cloud inference rather than local Ollama models to prevent CPU/GPU heat and resource contention on the Kibo server.
The AI subsystem is structured as a **provider-first, free-only multi-provider router** with circuit breakers, capability routing, and zero-cost policy enforcement.

```
Incoming Request (Text / Vision / Embedding)
                     │
         Capability & Modality Check
                     │
           Zero-Cost Filter (:free & price=0)
                     │
    ┌────────────────┴────────────────┐
    ▼                                 ▼
Text / Vision                      Embedding
    │                                 │
Provider 1: Google Gemini          Gemini Embedding 2
  - ADVANCED: gemini-3.6-flash       - Model: gemini-embedding-2
  - BALANCED: gemini-3.5-flash       - Output dimension: 768
  - FAST: gemini-3.5-flash-lite      - Canonical & solitary
    gemini-3.1-flash-lite             - Bounded exponential retry
  (Exhaust ALL before switching)      - NO cross-model fallback
    │                                 │
    ▼ (Only when Gemini exhausted)    ▼
Provider 2: OpenRouter             Status: Ingestion Pending
  - ADVANCED: Llama 3.3 70B, etc.
  - BALANCED: Llama 3.1 8B, etc.
  - FAST: Llama 3.2 3B, etc.
  - Final: openrouter/auto
    │
    ▼ (All free candidates exhausted)
Graceful 503 Service Unavailable (Zero Paid Fallback)
```

---

## 2. Required API Keys & Configuration

Add these variables to your production `.env` (never commit real values):

```ini
# Primary Provider: Google Gemini Direct API
GEMINI_API_KEY=your_gemini_api_key_here

# Fallback Provider: OpenRouter (Single API key across all OpenRouter models)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Strict Free-Only Enforcement
KIBOLENS_AI_FREE_ONLY=true
KIBOLENS_AI_ALLOW_PAID_MODELS=false

# Routing Parameters
KIBOLENS_AI_MAX_MODEL_ATTEMPTS=4
KIBOLENS_AI_PROVIDER_TIMEOUT_SECONDS=45
KIBOLENS_AI_MODEL_CATALOG_REFRESH_HOURS=24

# Active Provider: "cloud" (default) or "ollama" (legacy rollback)
KIBOLENS_LLM_PROVIDER=cloud
```

> **Security Note:** In production, `KIBOLENS_AI_ALLOW_PAID_MODELS` is validated at application startup. Attempting to set it to `true` in production raises a `ValidationError` unless explicitly disabled in code after review.

---

## 3. Strict Zero-Cost Enforcement Policy

1. **Default Flags:** `AI_FREE_ONLY=true` and `AI_ALLOW_PAID_MODELS=false`.
2. **OpenRouter Requirement:** Models must have the `:free` suffix AND explicitly report zero prompt price (`prompt == 0.0`) and zero completion price (`completion == 0.0`).
3. **Missing Pricing Rejection:** Any model with missing, unparseable, or "contact sales" pricing is rejected immediately.
4. **No Silent Upgrades:** Quota exhaustion on free tiers returns a clear `503 Unavailable` response; the router never automatically falls back to paid tiers.
5. **Secret Redaction:** API keys are wrapped in `SecretStr` and redacted in logs, operational context, and diagnostic responses.

---

## 4. Provider-First Fallback Order

The routing system strictly implements **provider-first** traversal, not interleaved model-first traversal.

### Text Generation Chain
1. **Google Gemini** is selected first.
2. Every eligible, active, verified free Gemini text model is attempted in configured priority order:
   - **ADVANCED:** `gemini-3.6-flash`, `gemini-2.5-flash`
   - **BALANCED:** `gemini-3.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`
   - **FAST:** `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-1.5-flash-8b`
3. A failure on a single Gemini model does **not** switch to OpenRouter; the router continues through Gemini's eligible list.
4. Only when Gemini's models are exhausted or Gemini is marked provider-down by its circuit breaker does routing proceed to **OpenRouter**.
5. OpenRouter verified free models (`:free` variants with zero pricing) are attempted in priority order.
6. If all candidates fail, a graceful `503 Service Unavailable` response is returned.

### Vision Input Chain
1. A **separate vision registry** is maintained.
2. Only models with confirmed image-input support (`AICapability.VISION_INPUT`) are evaluated.
3. Images are **never** forwarded to text-only models.
4. Follows the same provider-first sequence: Gemini vision models are exhausted before OpenRouter vision models.

---

## 5. Embedding Vector Compatibility & Qdrant Integrity

### Canonical Model & Space
- **Model:** `gemini-embedding-2` (fallback/alias: `text-embedding-004`)
- **Output Dimensionality:** `768`
- **Supported Task Types:**
  - `RETRIEVAL_DOCUMENT`: For document indexing and chunk storage.
  - `RETRIEVAL_QUERY`: For search and investigation queries.

### Cross-Model Mixing Prevention (CRITICAL)
> [!CAUTION]
> Embedding vector spaces are mathematically incompatible. Mixing vectors from Gemini, Ollama, OpenAI, or BGE in the same collection causes severe retrieval corruption and nonsensical cosine similarity scores.

- If Gemini embedding is temporarily unavailable:
  - Bounded exponential backoff retries are attempted.
  - If still failing, an `EmbeddingUnavailableError` is raised.
  - Ingestion is held **pending**; incompatible alternative vectors are never stored in the Qdrant collection.
  - Future embedding fallback must use a separate named vector or collection with independent retrieval.

---

## 6. Circuit Breaker & Error Classification

Failures are classified into three routing categories:

| Category | HTTP Codes | Action | Circuit Impact |
|---|---|---|---|
| `RATE_LIMITED` | 429 (per-model) | Try next model in list | Model failure +1 |
| `TIMEOUT` | 408, 504 | Try next model in list | Model failure +1 |
| `SERVER_ERROR` | 500, 502, 503 | Try next model in list | Model failure +1 |
| `QUOTA_EXHAUSTED` | 402, 429 (account) | Skip provider; proceed to fallback provider | Provider circuit OPEN |
| `AUTH_FAILURE` | 401, 403 | Skip provider; do not retry same provider | Provider circuit OPEN |
| `SAFETY_REFUSAL` | 200 (finish=SAFETY) | Stop; return policy response | None (request issue) |
| `INVALID_REQUEST` | 400 | Stop; do not cascade | None (schema issue) |

**Circuit Breaker Parameters:**
- Failure threshold before tripping: 5 consecutive failures
- Half-open cooldown probe window: 120 seconds
- Probe successes needed to close circuit: 1

---

## 7. Grok / xAI Policy

- The native xAI / Grok API is token-billed and **disabled** in free-only mode.
- Grok models are only permitted if OpenRouter's live catalogue exposes an xAI model with an explicit `:free` suffix and verified `$0.00` pricing.
- **Enabling Native xAI in the future (Paid Mode):**
  1. Set `KIBOLENS_AI_ALLOW_PAID_MODELS=true` in staging/testing environment.
  2. Implement an `XAIProvider` adapter adhering to `BaseLLMProvider`.
  3. Obtain explicit budget and architectural approval before deploying.

---

## 8. Observability & Health Diagnostics

A protected diagnostic endpoint is available at `GET /api/v1/ai/health`:

```bash
# Requires an active user session cookie
curl -X GET "http://localhost:8080/api/v1/ai/health" \
  -H "Cookie: kibolens_session=<session_token>"
```

### Example Diagnostic Response (Sanitized, No Secrets)
```json
{
  "free_only_mode": true,
  "allow_paid_models": false,
  "max_model_attempts": 4,
  "providers": {
    "gemini": {
      "available": true,
      "api_reachable": true,
      "circuit_breaker": {
        "failures": 0,
        "is_open": false,
        "quota_exhausted": false
      },
      "text_models": [
        {"model_id": "gemini-3.6-flash", "quality_tier": "advanced", "priority": 10},
        {"model_id": "gemini-3.5-flash", "quality_tier": "balanced", "priority": 20},
        {"model_id": "gemini-3.5-flash-lite", "quality_tier": "fast", "priority": 35}
      ],
      "embedding_model": "gemini-embedding-2",
      "embedding_dimension": 768
    },
    "openrouter": {
      "available": true,
      "api_reachable": true,
      "text_models_count": 14,
      "top_text_models": [
        {"model_id": "meta-llama/llama-3.3-70b-instruct:free", "quality_tier": "advanced"}
      ]
    }
  }
}
```

The legacy backward-compatible endpoint is also maintained at `GET /api/v1/llm/health`.

---

## 9. Rollback to Ollama

If needed for offline or local air-gapped development:
1. In `.env`, set:
   ```ini
   KIBOLENS_LLM_PROVIDER=ollama
   KIBOLENS_OLLAMA_BASE_URL=http://localhost:11434
   KIBOLENS_OLLAMA_MODEL=llama3.2:3b
   ```
2. Restart the backend service. No code changes or container rebuilds are required.
