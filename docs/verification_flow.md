# Phase 4 — Detailed Verification & Routing Flow

## Overview 

Phase 4 bridges generation to rendering, explicitly ensuring no speculative code breaches the terminal context window. The verification loop maps heavily to structured metrics on discrete sentences evaluated atomistically before bounding math aggregates them dynamically against rigid threshold boundaries.

---

## 1. Grounding LLM Stub Configurations

The LLM is completely deterministic for testing these bounds natively. By issuing `LLM_STRESS_MODE="MISSING_CITATIONS"` vs `LLM_STRESS_MODE="CONTRADICTORY_CLAIM"`, the verifier isolates repair loops cleanly bounding feedback attempts to maximum limitations.

## 2. Granular Issue Extractions

Claims are evaluated to derive exact violation constants limiting generation.

- `CLAIM_CONTRADICTION` → caps output to `0.40`.
- `NUMERIC_UNSUPPORTED` → caps output to `0.35` (High risk vectors like 1500C in ISRO).
- `DOMAIN_RULE_VIOLATION` → `0.0`. Pluggable boundaries targeting rule enforcement implicitly on document type. No loose procedural mapping allowed.

These map inherently to `IssueSeverity`:
- **REPAIRABLE**: e.g., missing chunks -> The system will cycle up to N iterations correcting this safely in bounded LLM environments.
- **HIGH_RISK**: e.g., Contradiction -> The system aborts trying to coerce failing networks and pushes the result for routing.
- **BLOCKING**: The system halts unconditionally, forcing fallback procedures immediately.

## 3. Threshold Routing & Safe Degradation

**Scaling Matrix**:
- PUBLIC >= 0.70
- INTERNAL >= 0.78
- CONFIDENTIAL >= 0.85
- SECRET >= 0.93

If a generated block falls anywhere below its applicable matrix, the model routes to `FALLBACK_PARTIAL`.

### Fallback Formatting
When a payload degrades gracefully to `FALLBACK_PARTIAL`:

- **All generated hallucinated/free text is deleted**.
- A curated payload extracting strictly the referenced chunks as pure untainted snippets is supplied.
- No chance of speculative execution reaching user eyes.

*Exception*: If the payload is marked `SECRET`, it bypasses `FALLBACK_PARTIAL` and converts aggressively to `BLOCKED`. Secret data is never allowed to exist with uncertain inference contexts. 

## 4. Auditing

Every cycle through the loop triggers the `verification.loop_iteration` checkpoint.
Upon completion (and computation of routing boundaries), a `VERIFICATION_COMPLETE` event maps exactly to `AuditAction.VERIFICATION_COMPLETE` outlining the discrete routing reason codes mapped accurately to `RoutingDecision`.
