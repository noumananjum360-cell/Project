# AI pipeline

## Providers

`app/ai/base.py` defines `AIProvider` (`complete_structured`, `embed`). Implementations:

* `OpenAIProvider`: OpenAI or any OpenAI-compatible API (`AI_PROVIDER=openai_compatible` + `OPENAI_BASE_URL`). JSON mode, Pydantic validation, one corrective retry on invalid JSON, SDK-level bounded retries with backoff for 429/5xx/timeouts, configurable timeout. Errors map to `ai_auth_failed`, `ai_rate_limited`, `ai_timeout`, `ai_connection_failed`, `ai_error`.
* `MockProvider`: deterministic and offline. Completions are assembled only from the supplied context; embeddings use hashed n-gram features. Allowed only when `ENVIRONMENT=test` or `DEMO_MODE=true` (never in production). Every result carries `is_simulated=true`, which the UI shows as **Simulated AI**.

Every call goes through `services/ai_runner.py`, which enforces the per-user daily limit, logs model/tokens/latency/success to `ai_usage_logs`, and estimates cost from `AI_PRICING_JSON` (left `null` when pricing is unknown).

## Fit Score (scoring v1.0.0)

Deterministic (`services/scoring.py`); default weights are admin-configurable:

| Factor | Weight | Score in [0,1] | Unknown when |
| --- | --- | --- | --- |
| Required-skill match | 30 | (matched + 0.5·partial) / required. Partial = same skill family or alias | Job has no identifiable skills, or profile has none |
| Portfolio evidence | 20 | 0.7·f(top similarity) + 0.3·f(mean top-3), f = linear between `similarity_floor` and `similarity_ceiling` | User has no portfolio |
| Experience & complexity | 15 | Level gap from years → entry/intermediate/expert (meets = 1.0, one below = 0.5, two below = 0.1) | Job level or user years missing |
| Budget & rate | 15 | ratio = client max / your rate (hourly) or minimum (fixed): ≥1 → 1.0, ≥0.8 → 0.7, ≥0.6 → 0.4, else 0.1 | Budget/type missing, currency mismatch, or no rate/minimum |
| Scope clarity | 10 | Length, deliverable cues and lists, minus broad scope (>12 skills) or very short deadlines | Never (description is required) |
| Client & posting risk | 10 | 1.0 minus penalties for evidence-backed warning signs (high 0.5, medium 0.25, low 0.1) and weak client signals | Never |

**Redistribution rule:** `score = 100 · Σ(wᵢ·sᵢ, known) / Σ(wᵢ, known)`; `confidence = Σ(wᵢ, known) / Σ(wᵢ)`. Unknown information is neither rewarded nor penalised; it lowers confidence.

**Recommendation:** confidence < `min_confidence` (0.5) → *Insufficient Information*; score ≥ 75 and no high-severity flag → *Strong Match*; ≥ 50 → *Possible Match*; otherwise *Weak Match*.

**No double counting:** budget shortfall affects only the budget factor; broad scope and short deadlines only the scope factor; communication/payment/sensitive-data patterns only the risk factor. AI-identified warnings are shown (labelled "AI-identified") but do not change the score.

Warning signs use cautious language ("Potential warning sign: …") with the quoted evidence. Clients are never labelled fraudulent.

Each analysis stores the result, weights, scoring version, provider/model, embedding model, profile version and simulated flag. The UI marks an analysis stale when the profile or portfolio changed afterwards.

## Portfolio vector search

1. A project becomes a document (title, category, role, skills, description, outcomes).
2. `content_hash = sha256(model + document)`; unchanged projects are skipped, so embeddings are not duplicated.
3. Vectors are upserted to the collection `portfolio__<embedding model>` with metadata `user_id`.
4. The job (title, skills, description) is embedded and queried with a `user_id` filter.
5. Hits are re-validated against the user's projects in PostgreSQL; evidence includes shared skills and the best-matching sentence.
6. Failures mark projects `failed` with an error; **Rebuild index** (`POST /portfolio/reindex`) retries.

Deleting a project deletes its vector; deleting an account deletes all of the user's vectors.

## Proposal generation

Payload: job (no client data), profile facts, up to 3 portfolio projects (auto-retrieved or user-selected), matched skills and options. Output schema: `hook`, `solution`, `proof`, `call_to_action`, `used_project_ids`. Post-validation:

* `used_project_ids` must be a subset of the supplied projects.
* Numbers/percentages that don't appear in the supplied evidence produce a visible warning ("Review these figures…").
* Excluded terms that appear produce a warning.
* A custom opening is guaranteed to start the hook.

Every generation, regeneration (full or one section) and manual snapshot is an immutable version with provider, model, prompt version, tokens and estimated cost. Before regeneration, unsaved edits are snapshotted.

## Prompt-injection containment

* Untrusted text (job posts, resumes) is serialised inside a `<context_json>` block that cannot be closed early, and the system prompt says that instructions inside it are data.
* The model has no tools and no access to other users' data. Outputs are schema-validated and post-checked.
* Scores are deterministic, so injected text cannot change them.
* Secrets are never placed in prompts.
