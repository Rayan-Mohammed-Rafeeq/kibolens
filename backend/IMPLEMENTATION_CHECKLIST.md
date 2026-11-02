# KIBOLENS FINAL AI ROUTER - IMPLEMENTATION CHECKLIST

## Phase 1: Remove Artificial Limits ✓ TO DO

### A. Configuration Changes
- [❌] Remove `ai_max_model_attempts` from Settings (config.py)
- [❌] Update .env.example if it references this setting
- [❌] Update test fixtures that use ai_max_model_attempts

### B. Core Router Changes
- [❌] Remove `_DEFAULT_MAX_ATTEMPTS` constant (core.py line 65)
- [❌] Remove `_max_attempts` instance variable (core.py line 83)
- [❌] Remove `max_model_attempts` from health_status response (core.py line 473)
- [❌] Add documentation about operational safeguards vs usage quotas

### C. Keep These (Not AI Usage Limits)
- [✓] `login_max_attempts` - Security protection
- [✓] `otp_max_attempts` - Security protection  
- [✓] `_PER_MODEL_RETRIES` - Transient retry (operational)
- [✓] Circuit breakers - Reliability safeguard
- [✓] Network timeouts - Operational safety

## Phase 2: Verify Exhaustive Fallback ✓ TO DO

- [❌] Confirm Gemini models fully exhausted before Groq
- [❌] Confirm Groq models fully exhausted before OpenRouter
- [❌] Confirm no cross-provider interleaving
- [❌] Verify _try_provider_models exhausts all eligible models

## Phase 3: Model Registry Cleanup ✓ TO DO

### Gemini Retired Models to Remove
- [❌] gemini-2.0-flash-exp
- [❌] gemini-exp-1206
- [❌] gemini-exp-1121  
- [❌] gemini-2.0-flash
- [❌] gemini-1.5-flash variants

### Groq Deprecated Models to Remove
- [❌] llama-3.3-70b-versatile
- [❌] llama-3.1-70b-versatile
- [❌] llama-3.1-8b-instant
- [❌] Deprecated Llama vision previews

## Phase 4: AQ. Key Support ✓ TO DO

- [❌] Verify AQ. prefix accepted
- [❌] Verify AIza prefix accepted
- [❌] Add test for AQ. format
- [❌] Verify x-goog-api-key header used
- [❌] Verify no Bearer token conversion

## Phase 5: Testing ✓ TO DO

- [❌] Run complete test suite (run 1)
- [❌] Run complete test suite (run 2)
- [❌] Verify 200 passed, 4 skipped, 0 failed
- [❌] Verify exit code 0 both runs
- [❌] Add regression test for no attempt limits
- [❌] Add AQ. key format test

## Phase 6: Documentation & Validation ✓ TO DO

- [❌] Update inline documentation
- [❌] Validate Docker Compose
- [❌] Generate final report
- [❌] List all files modified

## Phase 7: Verification Checklist ✓ TO DO

- [❌] Zero artificial attempt limits
- [❌] Exhaustive provider-first fallback verified
- [❌] Retired models excluded
- [❌] AQ. keys supported
- [❌] Vision/text separation confirmed
- [❌] Gemini Embedding 2 @ 768D canonical
- [❌] No paid models selected
- [❌] No Ollama auto-invocation
- [❌] Authentication intact
- [❌] Tests pass (both runs)

## Current Status: READY TO IMPLEMENT

Starting with Phase 1...
