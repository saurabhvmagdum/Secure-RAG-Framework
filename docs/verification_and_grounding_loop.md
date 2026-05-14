Overview of Layer 3 flow
Input: UserQuery (normalized) and ConsolidatedEvidenceSet containing ranked chunks from keyword, semantic, and graph retrieval along with their provenance and metadata.

Output: VerifiedAnswer object containing final answer text, explicit source links, confidence score, and routing decision (HIGH_CONFIDENCE or FALLBACK_PARTIAL), all logged through the security and governance layer.

Initial draft answer generation
Data structures
python
class EvidenceChunk(TypedDict):
  doc_id: str
  chunk_id: str
  text: str
  rank: int
  index_type: str            # "keyword" | "semantic" | "graph"
  score: float
  metadata: dict             # domain_tag, sensitivity_level, version, origin

class ConsolidatedEvidenceSet(TypedDict):
  query_id: str
  user_query: str
  chunks: list[EvidenceChunk]

class DraftAnswer(TypedDict):
  query_id: str
  text: str
  cited_chunks: list[str]    # chunk_ids explicitly referenced
Generation algorithm (pseudocode)
python
def generate_draft_answer(evidence: ConsolidatedEvidenceSet) -> DraftAnswer:
    # 1. Select top-N diverse chunks using MMR or similar
    selected = select_mm_reranked_chunks(evidence.chunks, k=K_PRIMARY)

    # 2. Build structured prompt containing:
    #    - normalized user query
    #    - ordered list of selected text chunks with doc/chunk IDs
    prompt = build_grounded_prompt(evidence.user_query, selected)

    # 3. Call on-prem quantized LLM with deterministic parameters
    llm_output = local_llm_generate(
        prompt=prompt,
        max_tokens=MAX_TOKENS,
        temperature=0.1,
        top_p=0.9
    )

    # 4. Post-process to ensure explicit citations in the answer body
    answer_text, cited_chunk_ids = enforce_citations(llm_output, selected)

    return DraftAnswer(
        query_id=evidence.query_id,
        text=answer_text,
        cited_chunks=cited_chunk_ids
    )
LLM is forced to answer strictly based on provided chunks, with instructions forbidding speculation and requiring citation markers such as [doc_id:chunk_id] embedded in the text.

Verification and fact-checking loop
Metrics and criteria
For each iteration, the system evaluates:

Relevance: Degree to which cited chunks match the user query intent.

Coverage: Fraction of key query aspects addressed by the answer using distinct evidence chunks.

Similarity: Semantic similarity between answer statements and source chunks.

Consistency: Internal consistency across answer sentences and cross-chunk consistency; detection of contradictions.

Domain-specific rules: Specialized validators for procurement, telemetry, failure analysis, etc., checking format, rule references, and mandatory fields.

Algorithm (high level)
python
class VerificationResult(TypedDict):
  relevance: float
  coverage: float
  similarity: float
  consistency: float
  domain_rules: float
  issues: list[str]
  iterations: int

def verify_and_ground(evidence: ConsolidatedEvidenceSet,
                      draft: DraftAnswer,
                      max_iterations: int = 3) -> tuple[DraftAnswer, VerificationResult]:
    current_answer = draft
    for i in range(max_iterations):
        metrics, issues = compute_verification_metrics(evidence, current_answer)
        if is_acceptable(metrics):
            return current_answer, VerificationResult(
                **metrics, issues=issues, iterations=i+1
            )
        # If not acceptable, regenerate answer with corrective feedback
        feedback = build_feedback_from_issues(issues)
        current_answer = regenerate_with_feedback(evidence, current_answer, feedback)
    # Return best-effort result after max iterations
    metrics, issues = compute_verification_metrics(evidence, current_answer)
    return current_answer, VerificationResult(
        **metrics, issues=issues, iterations=max_iterations
    )
Metric computation details
Relevance: average of BM25 scores and semantic similarity scores for cited chunks normalized to, weighted by rank.

Coverage: proportion of query intents (identified via query decomposition into sub-intents) that have at least one cited chunk supporting them.

Similarity: sentence-level embedding similarity between answer spans and their referenced chunks, penalizing unsupported spans.

Consistency:

Cross-chunk consistency: graph-based and rule-based checks to ensure no conflicting values (e.g., different root cause IDs or rule numbers) for the same entity.

Temporal/logical consistency: simple constraint solver checks over dates, numeric ranges, and dependency relations.

Domain-specific rules: pluggable validators, e.g.,

Procurement: ensure all referenced rules map to valid rule IDs and sections; check mandatory fields (financial limits, approval levels).

Telemetry/failure: ensure anomaly descriptions reference valid subsystem IDs, telemetry parameter names, and time ranges present in evidence.

Confidence score computation
Formula
We compute a scalar confidence score 
C
∈
[
0
,
1
]
C∈[0,1] as a weighted aggregation:

C
=
w
r
R
+
w
c
C
v
+
w
s
S
+
w
k
K
+
w
d
D
C=w 
r
​
 R+w 
c
​
 C 
v
​
 +w 
s
​
 S+w 
k
​
 K+w 
d
​
 D
where:

\( R \) = relevance score,

C
v
C 
v
​
  = coverage score,

\( S \) = similarity score,

\( K \) = consistency score,

\( D \) = domain-rules score,

w
r
,
w
c
,
w
s
,
w
k
,
w
d
w 
r
​
 ,w 
c
​
 ,w 
s
​
 ,w 
k
​
 ,w 
d
​
  are governance-tuned weights summing to 1.

Implementation sketch:

python
def compute_confidence(metrics: dict, weights: dict) -> float:
    return (
        weights["relevance"]  * metrics["relevance"] +
        weights["coverage"]   * metrics["coverage"] +
        weights["similarity"] * metrics["similarity"] +
        weights["consistency"]* metrics["consistency"] +
        weights["domain_rules"]*metrics["domain_rules"]
    )
Weights and minimum acceptable per-metric scores are defined in a configuration store managed by governance, different per domain_tag and sensitivity_level.

Confidence score, metric breakdown, and governing parameters are stored in the audit log for each query.

Threshold check and routing decision tree
Configuration
text
RoutingPolicy:
  default_threshold: 0.8
  per_domain_thresholds:
    "procurement": 0.9
    "telemetry": 0.85
    "failure_analysis": 0.9
  allow_partial_when_below_threshold: true
  hard_block_below: 0.5
Decision logic
python
class RoutingDecision(TypedDict):
    route: str                 # "HIGH_CONFIDENCE" | "FALLBACK_PARTIAL" | "BLOCKED"
    confidence: float
    explanation: str

def route_answer(domain_tag: str,
                 confidence: float,
                 metrics: dict,
                 policy: RoutingPolicy) -> RoutingDecision:
    threshold = policy.per_domain_thresholds.get(
        domain_tag, policy.default_threshold
    )

    if confidence < policy.hard_block_below:
        return {
            "route": "BLOCKED",
            "confidence": confidence,
            "explanation": "Confidence below hard safety threshold; surface evidence-only view."
        }

    if confidence >= threshold:
        return {
            "route": "HIGH_CONFIDENCE",
            "confidence": confidence,
            "explanation": f"Confidence {confidence:.2f} ≥ threshold {threshold:.2f}."
        }

    if policy.allow_partial_when_below_threshold:
        return {
            "route": "FALLBACK_PARTIAL",
            "confidence": confidence,
            "explanation": (
                f"Confidence {confidence:.2f} below threshold {threshold:.2f}; "
                "return curated evidence snippets and caveats instead of a synthesized answer."
            )
        }

    return {
        "route": "BLOCKED",
        "confidence": confidence,
        "explanation": "Sub-threshold answer not permitted for this domain."
    }
Routed outputs
Verified Answer with High Confidence: full natural-language response generated by the LLM, with inline citations to chunk IDs, summarized metric breakdown, and explicit confidence label; delivered to UI and logged with full verification context.

Fallback Response with Partial Evidence: UI presents a structured evidence viewer listing top chunks, their scores, and provenance, plus a short, conservative summary or explanation that the system cannot confidently synthesize a complete answer; encourages human expert review before action.