# Learning Log

Project history, appended once per task. Format per `plan.md` §0:
**what we built · key things to understand · decision & why (incl. rejected
alternative) · what could break.**

---

## Step 0 — Secure secret handling (`.env` / `.env.example`)

**What we built**
- `.env` (gitignored) holding the real `OPENAI_API_KEY`.
- `.env.example` (committed) — a value-less template documenting required keys.

**Key things to understand**
- The [12-factor](https://12factor.net/config) config pattern: secrets live in the
  *environment*, never hardcoded in source.
- `.env` is matched by `.gitignore`, so it can never be committed/pushed; the
  committed `.env.example` is the "contract" telling anyone what to fill in.

**Decision & why (rejected alternative)**
- Variable named exactly `OPENAI_API_KEY` so the OpenAI SDK auto-reads it from
  the environment — zero key-handling boilerplate in our code.
- Rejected: hardcoding the key or a single committed config file — either leaks
  the secret into git history.

**What could break**
- If `.env` is ever force-added (`git add -f`) the secret leaks. Verified clean:
  the key prefix appears in zero commits across all history.

---

## Step 1 — Verified LLM round-trip (`config.py`, `smoke_test.py`)

**What we built**
- `config.py` — loads `.env`, validates `OPENAI_API_KEY` (fail-fast), and exposes
  `OPENAI_API_KEY` + `DEFAULT_CHAT_MODEL`.
- `smoke_test.py` — a heartbeat that sends one Chat Completions request and prints
  the reply, proving `.env -> config -> SDK -> network -> response` works.

**Key things to understand**
- **Single source of truth:** every later module imports `config` instead of
  re-reading env vars; change it once, everywhere benefits.
- **Fail fast, fail clear:** validating the key up front turns a cryptic deep SDK
  error into a one-line "set OPENAI_API_KEY in .env".
- **The chat request shape:** `model` + a list of `messages`, each with a `role`
  (`system` = persona/instructions, `user` = the ask). This same unit reappears
  in tool calling and the agent loop.
- The SDK reads `OPENAI_API_KEY` from the environment automatically, so we create
  `OpenAI()` with no key argument.

**Decision & why (rejected alternatives)**
- **Chat Completions API** over the newer **Responses API** — far more examples,
  and it maps 1:1 onto tool calling later, which is better for learning.
- **Not** an installable `src/` package yet — packaging machinery isn't worth it
  for two files; files sit at the project root and `import config` resolves
  because Python puts a script's own folder on the import path. Folds into the
  `plan.md` §10 structure at Milestone 1.
- Model `gpt-4o-mini` — cheap/fast default, trivially swappable via
  `DEFAULT_CHAT_MODEL`.

**What could break**
- Blank/invalid key → `RuntimeError` from `config` (intended) or a 401 from the API.
- No network / proxy issues → SDK connection error.
- Model name retired by OpenAI → swap `DEFAULT_CHAT_MODEL`.

**Definition of done:** `uv run python smoke_test.py` prints a reply beginning
with "Connection OK".

---

## Step 2 — Taxonomy seed: representation + tools & chambers (`scripts/taxonomy.py`)

First task of Milestone 1 (Data). The taxonomy is built incrementally; this step
sets the data representation and seeds the equipment roster.

**What we built**
- `scripts/taxonomy.py` with:
  - `MODULE_TYPES` / `PROCESS_TYPES` — the allowed vocabulary (etch + deposition only).
  - A frozen `Tool` dataclass (`tool_id`, `module_type`, `process_type`, `chambers`)
    with a `chamber_ids()` helper deriving fully-qualified ids like `ETCH02_PM3`.
  - `TOOLS` — the fab roster (3 etch + 4 deposition tools) keyed by `tool_id`.
  - A `__main__` dump so `uv run python scripts/taxonomy.py` prints the seed.

**Key things to understand**
- This file is the project's **single source of truth**: the data generator samples
  from it (consistency), the benchmark grades against it (ground truth), and a later
  validation gate rejects docs referencing anything not defined here (the allow-list).
  Small file, very high leverage — a bug here propagates everywhere.
- **Why `@dataclass`:** named, typed fields force every record to be complete, so a
  typo (`subsytem`, a missing field) fails *at construction*, not silently three
  modules downstream. Plus autocomplete and self-documentation, with zero deps.
- **Why `frozen=True`:** seed data must never be mutated at runtime; freezing turns an
  accidental reassignment into an error, enforcing the "source of truth" contract.
- **Derive, don't hand-type:** `chamber_ids()` builds `TOOL/CHAMBER` from structure,
  so the citation/metadata form can never drift from the roster.

**Decision & why (rejected alternatives)**
- **Frozen dataclasses + dict registries** over **Pydantic** — Pydantic's value is
  validating *untrusted, dynamic* input (LLM output → `agent/schemas.py` later). This
  taxonomy is static, hand-authored data read at import; Pydantic would add a
  dependency and parsing cost for validation we don't need, and blur the teaching line
  of introducing it later for the job it's actually good at.
- ...also over **plain dicts/constants** (what `plan.md` literally says): a deliberate
  one-notch upgrade. Same idea (constants in a Python file) but with typo-safety, which
  matters most for a high-leverage seed. We added a safety net, not complexity.
- Naming: chambers vary by tool (`PM#` for etch/most, `Stn#` for the PECVD cluster) on
  purpose, so the generated corpus doesn't look templated.

**What could break**
- Nothing is *enforced* yet — a Tool could declare a `process_type` outside
  `PROCESS_TYPES` and nothing complains. That cross-check is a planned later task
  (the self-check / validation step), not an oversight.
- Later modules importing this will need `scripts/` to be importable (e.g. an
  `__init__.py` or path handling); fine for now since we run it directly.

**Next logical improvement**
- Task 2: add the shared **subsystems** vocabulary, then the alarm-code catalog
  (Task 3) and failure signatures (Task 4), then a self-check tying them together.

**Definition of done:** `uv run python scripts/taxonomy.py` prints all 7 tools with
their fully-qualified chamber ids and `7 tools total`. ✓

---

## Step 3 — Taxonomy: subsystems vocabulary (`scripts/taxonomy.py`)

Second task of Milestone 1. Domain content supplied by the user (real-flavored
subsystem list); deposition-specific entries proposed and confirmed.

**What we built**
- A frozen `Subsystem` dataclass (`subsystem_id`, `name`, `applies_to`) and a
  `SUBSYSTEMS` registry keyed by id — 20 entries: 12 common, 5 etch-only, 3 dep-only.
- `applies_to` defaults to both module families; etch-only / dep-only entries pass
  `ETCH_ONLY` / `DEP_ONLY` shorthands.
- Extended the `__main__` dump to print subsystems with their scope.

**Key things to understand**
- Subsystems are the **connective tissue**: the alarm catalog (Task 3) and failure
  signatures (Task 4) both reference these `subsystem_id`s, so they're defined first.
- **Scope modeling (`applies_to`):** etch and deposition don't share every subsystem.
  Etch *cools* the wafer (ESC + chiller) and adds a bias RF generator/matcher + optical
  endpoint; deposition *heats* it (heated pedestal) and adds precursor delivery +
  remote-plasma clean. Encoding scope here stops a later signature from attributing an
  etch-only subsystem to a deposition tool.
- **Dataclass default field:** `applies_to: tuple[...] = MODULE_TYPES` lets the many
  shared subsystems omit the argument — first use of a defaulted dataclass field here.

**Decision & why (rejected alternative)**
- **No subsystem-specific alarm-code prefixes** (user call): a subsystem is just id +
  name + scope. Rejected baking `RF`/`VAC`-style prefixes into subsystems — keeps the
  alarm-code naming scheme a separate concern we design in Task 3.
- **PVD kept minimal:** `applies_to` is coarse (module-type level), so dep-only
  subsystems formally attach to PVD too, though PVD uses none of them. Rejected adding
  PVD-specific subsystems (target/magnetron/DC supply) — it's a single tool and not
  worth the modeling cost for v1.

**What could break**
- The PVD over-inclusion above is a known simplification; hand-authored signatures
  (Task 4) keep per-tool accuracy, so it shouldn't surface in the corpus.
- Still no enforcement that `applies_to` values are valid `MODULE_TYPES` — folds into
  the planned self-check task.

**Next logical improvement**
- Task 3: the alarm/fault code catalog (~30 codes), each referencing a `subsystem_id`.

**Definition of done:** `uv run python scripts/taxonomy.py` also prints all subsystems
with scope and `20 subsystems total`. ✓

---

## Step 4 — Taxonomy: alarm/fault code catalog (`scripts/taxonomy.py`)

Third task of Milestone 1. The user supplied a per-subsystem alarm skeleton and asked
to flesh it out to ~60 (the deposition alarms were proposed and confirmed).

**What we built**
- A frozen `AlarmCode` dataclass (`code`, `text`, `subsystem`, `typical_causes`) and an
  `ALARMS` registry of **60 codes** keyed by code.
- Extended the `__main__` dump to list alarms and run a light reference check that
  every alarm's `subsystem` exists in `SUBSYSTEMS`.

**Key things to understand**
- **Codes are flat (`ALM-001`…`ALM-060`); the owning subsystem is a *field*, not part
  of the id.** This was a deliberate user call ("no subsystem-specific codes"), so the
  mnemonic-prefix scheme (`RF-2xx`, `VAC-1xx`) from the original plan was dropped.
- **Not every subsystem raises alarms.** Hardware-only subsystems — `rf_cabling`,
  `gas_injector`, `edge_ring`, `foreline` — have *zero* codes. They cause problems but
  don't self-report, so they'll appear as *root causes* in the failure signatures
  (Task 4), not as alarms. This asymmetry is real fab behavior and worth internalizing.
- **`typical_causes` deliberately points across subsystems** (e.g. "high reflected
  power" lists *degraded RF cabling*). That cross-linking is what makes multi-document
  diagnosis possible later — the alarm is on one subsystem, the cause on another.
- **No `severity` field (dropped on review).** Every alarm here is effectively
  critical, so a `severity` column would be a constant — the same value 60 times. A
  field that never varies carries no information, *implies* a distinction that doesn't
  exist (inviting code to branch on it), and is just noise. YAGNI: model the dimension
  only if/when it actually varies; re-adding is trivial since this is a seed file.

**Decision & why (rejected alternative)**
- **Flat codes + subsystem field** over **mnemonic prefixes** — honors the user's
  preference and keeps the subsystem mapping in one place (the field) rather than
  duplicated in the id string, where it could drift.
- **Dropped `severity`** over keeping a uniformly-`critical` field — a constant column
  isn't data. Rejected "keep it for future-proofing": re-adding a field to a seed file
  we own is cheap, and a misleading dead field today is a real cost.
- **60 codes weighted toward alarm-prone subsystems** (RF, vacuum, gas, thermal,
  wafer-handling) rather than one-per-subsystem — rejected even spreading because it
  would misrepresent which subsystems actually throw alarms.

**What could break**
- Reference integrity (alarm→subsystem) is only checked in `__main__`, not enforced at
  import; a bad ref in code wouldn't fail a plain `import`. The dedicated self-check
  task (Task 5) will harden this. (Currently all 60 refs validate.)
- `typical_causes` are first-pass domain judgments — easy to redline later without
  structural change.

**Next logical improvement**
- Task 4: recurring **failure signatures** (symptom → subsystem → root cause, optional
  preceding alarm), referencing real `TOOLS` / `SUBSYSTEMS` / `ALARMS` ids — including
  the hardware-only root causes (particles from edge ring / gas injector, RF cabling).

**Definition of done:** `uv run python scripts/taxonomy.py` prints `60 alarms total`
and `alarm -> subsystem refs valid: True`. ✓

---

## Step 5 — Taxonomy: failure signatures (`scripts/taxonomy.py`)

Final task of Milestone 1 — completes the taxonomy seed. These signatures are the
*ground truth* the benchmark will grade against. Drafted by the assistant from the
plan's examples + domain knowledge, for the user to redline.

**What we built**
- A frozen `FailureSignature` dataclass (`signature_id`, `tools`, `symptom`,
  `root_cause_subsystem`, `root_cause`, `fix`, `preceding_alarm=None`) and a
  `SIGNATURES` registry of **20 signatures** keyed by id.
- Extended `__main__` to print signatures and run a **reference + module-scope** check:
  every `tool`, `root_cause_subsystem`, and `preceding_alarm` must exist, and both the
  root-cause subsystem and the alarm's subsystem must actually exist on each tool's
  module family.

**Key things to understand**
- **This is the linchpin of the whole project.** The generator plants each signature
  *scattered across multiple documents*, so a benchmark question can only be answered
  by synthesizing several docs — that's what proves the RAG/agent value later.
- **Reporting subsystem ≠ broken subsystem.** `preceding_alarm` belongs to the
  subsystem that *reports*; `root_cause_subsystem` is what's *actually* broken. SIG-02
  is the canonical case: the RF match reports high reflected power (ALM-005) but the
  real fault is degraded **RF cabling** (a hardware-only subsystem with no alarm of its
  own). This gap is the diagnostic challenge.
- **Hardware-only root causes are covered:** rf_cabling (SIG-02), edge_ring (SIG-03),
  gas_injector (SIG-12), foreline (SIG-09) — none raise alarms, all are root causes.
- **`preceding_alarm` is optional** (`None`) — some failures (particle/PM issues) show
  up as symptoms with no alarm. SIG-03 and SIG-12 model that.

**Decision & why (rejected alternative)**
- **Signatures reference a list of `tools`** rather than a whole module type — the
  ground truth is tool-specific and the benchmark verifies per tool. Rejected
  module-level scoping as too coarse to grade against.
- **Validated scope in `__main__` now** (not deferred entirely to Task 5's self-check) —
  hand-authoring 20 cross-referenced entries is exactly where a typo or an etch-only
  subsystem on a dep tool would slip in; checking immediately caught nothing but proves
  the seed is internally consistent.

**What could break**
- Domain accuracy is first-pass — symptoms/causes/fixes are the assistant's draft and
  the **user's redline is expected**. Structure is stable regardless of wording edits.
- Scope checks live in `__main__`, not enforced at import (a bad ref wouldn't fail a
  plain `import`). A dedicated importable self-check is the natural next step.

**Next logical improvement**
- Milestone 1 is complete. Next: a small importable validator (or pytest) over the whole
  taxonomy, then Milestone 1's other half — `scripts/generate_data.py` (synthetic
  corpus) that samples these seeds and plants the signatures across documents.

**Definition of done:** `uv run python scripts/taxonomy.py` prints `20 signatures total`
and `signature refs + scope valid: True`. ✓

---

## Step 6 — Taxonomy consistency as pytest (`tests/test_taxonomy.py`)

Promoted the `__main__` "valid: True/False" checks into a real, enforced test suite —
"we're building real software."

**What we built**
- `tests/test_taxonomy.py` — parametrized tests covering: each registry is keyed by its
  own id; tools declare known module/process types and have chambers; subsystem
  `applies_to` is a non-empty subset of `MODULE_TYPES`; every alarm references a real
  subsystem; every signature's tools/subsystem/alarm resolve; and signature module
  scope is consistent (no etch-only subsystem on a dep tool, etc.).
- `[tool.pytest.ini_options]` in `pyproject.toml`: `pythonpath = ["."]` (so tests can
  `import scripts.taxonomy`) and `testpaths = ["tests"]`.
- Removed the two validation blocks from `taxonomy.py`'s `__main__`, keeping only the
  human-readable dump (now annotated that tests do the enforcing).

**Key things to understand**
- **Why tests beat `__main__` prints:** the checks now run automatically, fail with a
  non-zero exit (CI/pre-commit can gate on them), and pinpoint the exact failing item.
- **`@pytest.mark.parametrize(..., ids=...)`** turns one test into one case *per* tool /
  alarm / signature, so a failure reports e.g. `SIG-07` by name — far better than a
  lumped boolean. 234 cases pass (7 tools + 20 subsystems + 60 alarms + 20 signatures
  across the suites).
- **`pythonpath = ["."]`** makes the project root importable in tests; `scripts/` works
  as an implicit namespace package (no `__init__.py` needed on 3.11).

**Decision & why (rejected alternative)**
- **Tests in `tests/`** over **`assert`s at import time in `taxonomy.py`** — import-time
  asserts would enforce too, but they crash any import on bad data and mix test logic
  into the data module. Tests keep concerns separate and run on demand.
- **Kept the `__main__` dump** rather than deleting it — it's a handy human glance at the
  seed and isn't a correctness check, so it doesn't belong in the test file.

**What could break**
- Tests run via `uv run pytest`; they assume the `pythonpath`/`testpaths` config. A
  future move of `taxonomy.py` out of `scripts/` would need the import path updated.

**Next logical improvement**
- Merge `feat/taxonomy` to `main`, then start `scripts/generate_data.py` (synthetic
  corpus) in a fresh session.

**Definition of done:** `uv run pytest` passes (234 cases); `scripts/taxonomy.py` no
longer prints "valid" lines. ✓

---

## Milestone 2, Step 1 — Generator scaffold (`scripts/generate_data.py`, `data/` dirs)

First task of Milestone 2 (synthetic corpus). Establishes the skeleton before any LLM
calls are made.

**What we built**
- `scripts/generate_data.py` — module with `--dry-run` / `--seed` CLI args and a
  module-level `rng = random.Random(SEED)` instance (seed 42).
- `data/{raw,corpus,structured}/` — output directories tracked via `.gitkeep`; contents
  gitignored so generated files never land in version control.
- Updated `.gitignore`: `data/raw/*` / `data/corpus/*` / `data/structured/*` with
  `!.gitkeep` exceptions — ignores *contents*, not the directory itself.

**Key things to understand**
- **`data/raw/`** will cache one file per LLM call. On a rerun, we skip cached calls so
  we only pay the API once. `data/corpus/corpus.jsonl` is the final assembled corpus;
  `data/structured/` holds non-LLM records (tool summaries) in tidy JSON for the agent
  tool layer.
- **`data/raw/*` vs `data/raw/`:** gitignoring a *directory* blocks all `!exceptions`
  inside it. Using `/*` ignores the *contents* instead, which lets `!.gitkeep` work.
  A subtle but important `.gitignore` behaviour.
- **Seeded RNG:** constructing `random.Random(SEED)` at module level means every import
  gets the same starting state. Re-seeding in `main()` via `--seed` overrides for
  experiments without touching the global default.

**Decision & why (rejected alternative)**
- `sys.path` manipulation at the top of the script (`sys.path.insert(0, str(_ROOT))`)
  rather than running via `python -m scripts.generate_data` — keeps the familiar
  `uv run python scripts/generate_data.py` invocation consistent with the rest of the
  project.

**What could break**
- Nothing in this step calls the LLM or writes real corpus content; all risk is deferred.

**Definition of done:** `--dry-run` prints plan; bare run prints "not yet implemented";
dirs exist; no unintended files staged. ✓

---

## Milestone 2, Step 2 — Tool summary generator (`generate_tool_summaries`)

First real generator — no LLM, pure taxonomy-to-document transform. Proves the document
envelope before spending API credits.

**What we built**
- `generate_tool_summaries()` in `scripts/generate_data.py`: one doc per tool (7 total),
  MTBF + last-PM date from seeded RNG, open issues anchored to the tool's failure
  signatures (60% of the time) or a random applicable subsystem (40%).
- `write_corpus()` helper: appends JSON lines to `data/corpus/corpus.jsonl`.
- `data/structured/tool_summaries.json`: the raw structured records written separately
  for the agent tool layer (no `text` field — just the machine-readable payload).
- `tests/test_generate_data.py` (13 cases): one doc per tool, unique IDs, all envelope
  fields present, chambers match taxonomy, JSON-serialisable.

**Key things to understand**
- **`text` vs `metadata` — two jobs, same document.**
  `text` is prose written for the embedding model: it's what semantic search runs
  against, so converting structured data to clear sentences here ("MTBF: 70 days" →
  "Mean time between failures (MTBF): 70 days.") directly affects retrieval quality.
  `metadata` stays structured and lands in Qdrant as a payload — never embedded, only
  filtered (e.g., `tool_id = "ETCH02"`). Together they give best-of-both-worlds:
  semantic recall + exact structured filtering.
- **Document envelope fields** (every corpus doc has these): `doc_id`, `doc_type`,
  `tool_id`, `chamber`, `alarm_codes`, `subsystem`, `date`, `text`, `metadata`.
  Consistency here is what makes the ingest pipeline simple: one schema, five doc types.
- **Open issues tied to signatures:** when a tool has a known failure signature (e.g.,
  ETCH02 / RF instability), there's a 60% chance its open-issue text references that
  signature's symptom and subsystem. This means benchmark-relevant clues appear even in
  tool summary docs — another path for the retriever to find corroborating evidence.

**Decision & why (rejected alternative)**
- **Tool summaries first** over any LLM-backed doc type — zero API cost, zero network
  failure surface. Proves the envelope shape and test harness before we introduce
  variability. Rejected starting with alarm logs (second simplest): they do need minimal
  LLM templating and would have mixed two concerns in the first real step.
- **Corpus wiped on each full run** (`CORPUS_FILE.write_text("")`) — the corpus is fully
  deterministic from the seed, so there's no value in appending; a fresh run should
  always produce the same output. Rejected append-only: stale docs from a previous
  partial run would corrupt the benchmark.

**What could break**
- `data/corpus/corpus.jsonl` is truncated at the start of `main()`. A crash mid-run
  leaves a partial corpus. Later steps will add a staging / atomic-write pattern if
  needed.

**Definition of done:** `uv run python scripts/generate_data.py` writes 7 docs;
`uv run pytest` passes (247 cases, 13 new). ✓

---

## Milestone 2, Step 3 — Alarm log generator (`generate_alarm_logs`)

First LLM-backed generator. Produces machine-formatted alarm event logs; plants the
`preceding_alarm` from each failure signature into the corpus.

**What we built**
- `_cache_path(prompt)` — hashes the prompt (SHA-256, first 20 hex chars) to a filename
  in `data/raw/`. Used by `_llm_call()`.
- `_llm_call(prompt, model)` — calls `gpt-4o-mini`, writes raw response to cache, returns
  cached content on reruns. Lazy-imports `config` and `openai` so dry-run never touches
  the API or validates the key.
- `_ALARM_LOG_PROMPT` — template injecting tool_id, chamber, alarm_code, alarm text,
  subsystem name, typical causes, and datetime. LLM writes terse pipe-delimited log lines
  with plausible sensor readings; we supply all taxonomy facts.
- `generate_alarm_logs(dry_run=False)` — 18 planted docs (one per signature×tool that
  has a `preceding_alarm`) + up to 22 distractors (random tool+alarm pairs, skipped when
  the alarm's subsystem doesn't apply to the tool's module type). Total: 37 docs.
- `main()` refactored to pass `dry_run` through to each generator; dry-run now prints
  planned doc counts without writing files or calling the API.

**Key things to understand**
- **LLM as a prose writer, not a fact inventor.** Every taxonomy entity (tool_id,
  chamber, alarm_code, subsystem) is injected by us into the prompt. The model varies
  phrasing and invents plausible sensor values — the two things it's good at. If we let
  the model choose alarm codes, it would hallucinate codes outside our taxonomy,
  breaking the validation gate we'll add later.
- **The raw cache pattern.** Each LLM response is stored as a JSON file keyed by prompt
  hash. A rerun with the same seed skips every API call — the corpus is free to
  regenerate after the first run. This is the same pattern production ML pipelines use
  for expensive preprocessing. The `data/raw/` directory is gitignored, so the cache
  is local only.
- **Planted vs distractor.** `is_planted: True` in metadata marks docs that contain
  deliberate signature evidence. Distractors are real-alarm-code events on real tools
  but not tied to any signature — they make retrieval harder (the model must distinguish
  relevant from plausible-but-irrelevant). Both types are necessary for the benchmark
  to be meaningful.
- **Scope filtering for distractors.** When picking a random alarm for a distractor,
  we skip the combination if the alarm's subsystem doesn't apply to the tool's module
  type (e.g., don't assign an etch-only ESC alarm to PECVD01). This respects the
  taxonomy's `applies_to` logic and keeps generated text physically plausible.

**Decision & why (rejected alternative)**
- **`gpt-4o-mini` for generation** over `gpt-4o` — the alarm log format is tightly
  constrained by the prompt (pipe-delimited, terse, numeric values). Mini handles this
  well and costs ~20× less; the quality difference appears only in open-ended prose where
  we'd use a larger model anyway. Easy to swap via `_llm_call(model=...)`.
- **Lazy config/openai import inside `_llm_call`** over top-level import — keeps
  dry-run clean (no key validation, no import cost) and keeps the module importable in
  tests without a valid `.env`.
- **One alarm log per signature×tool** over batching multiple alarms per doc — keeps
  each doc focused on one event and one alarm code, which simplifies metadata tagging
  and retrieval filtering. A single-alarm doc is also a cleaner unit for the chunker
  (Milestone 3) to handle.

**What could break**
- LLM output format varies slightly between calls even at temperature 0.7. The cache
  locks it in after the first run, but a cache-clear rerun may produce slightly different
  text (not a problem for the benchmark since we score on metadata fields, not exact
  text).
- Distractor count can be <22 if many random picks are skipped by scope filtering.
  Currently yields 19 distractors. Acceptable for now; can be bumped by increasing the
  loop count.

**Definition of done:** `uv run python scripts/generate_data.py` writes 44 docs (7
tool summaries + 37 alarm logs); all 37 LLM outputs cached in `data/raw/`; 247 tests
pass. ✓

---

## Milestone 2, Step 4 — Work order generator (`generate_work_orders`)

The most information-dense doc type: contains the root cause and fix from each failure
signature — the "answer" half of the benchmark.

**What we built**
- `_WORK_ORDER_PROMPT` — template injecting tool_id, chamber, process_type, dates,
  technician, symptom, root_cause_subsystem, root_cause, and fix. LLM writes in four
  fixed sections: PROBLEM DESCRIPTION / FINDINGS / ACTIONS TAKEN / RESULT.
- `_DISTRACTOR_WO_PROMPT` — lighter template for routine PM checks on a random subsystem;
  no signature facts injected.
- `generate_work_orders(dry_run=False)` — 20 planted docs (one per signature, tool and
  chamber chosen by seeded RNG) + 20 distractor routine maintenance docs. Total: 40 docs.
- Corpus: 84 docs total after this step (7 + 37 + 40).

**Key things to understand**
- **Work orders complete the evidence triangle.** For signatures with a `preceding_alarm`:
  the alarm log doc shows *that* the alarm fired; the work order shows *what was found and
  fixed*. Together they are the multi-document chain the agent must synthesize to answer
  "what caused the etch-rate drift on ETCH02?" — neither doc alone is sufficient.
- **Planted work orders reference the alarm code in metadata.** `alarm_codes` on a planted
  WO is set to `[sig.preceding_alarm]` when one exists. This lets the retriever find WOs
  by alarm code even though the alarm code may not appear in the prose text (the LLM was
  told not to invent codes). Metadata filtering is doing work here that semantic search
  alone can't.
- **Distractor WOs use a separate lighter prompt.** Injecting full signature facts into a
  distractor would accidentally plant evidence. A separate prompt for distractors keeps
  them realistic (real fab maintenance language) without carrying benchmark-relevant
  answers.
- **The cache means reruns are free.** All 37 alarm log calls hit cache; only the 40 work
  order calls were new API calls this run. After this run those 40 are also cached.

**Decision & why (rejected alternative)**
- **Fixed section headings (PROBLEM DESCRIPTION / FINDINGS / etc.)** over free-form prose
  — headings give the chunker (Milestone 3) clean split points and make it easier for the
  agent to cite which section the evidence came from. Free-form prose is harder to parse
  and would require smarter chunking later.
- **One planted WO per signature** (not one per signature×tool) — work orders capture the
  root cause + fix, which is the same regardless of which specific tool surfaced the
  failure. Generating duplicates per tool would dilute the benchmark signal. Alarm logs
  got one-per-tool because alarms fire on specific chambers; diagnoses are shared.

**What could break**
- The LLM occasionally bolds headings (`**FINDINGS:**`) rather than plain text. This is
  cosmetic and doesn't affect retrieval. The chunker will strip markdown if needed.
- Distractor WO doc_ids are `WO-DIST-000` through `WO-DIST-019`. If the distractor loop
  count ever changes, these ids shift — not a problem now, but worth noting if we add
  id-based lookups later.

**Definition of done:** `uv run python scripts/generate_data.py` writes 84 docs (7 + 37
+ 40); planted WO for SIG-01 contains correct symptom/root-cause/fix prose; 247 tests
pass. ✓

---

## Milestone 2, Step 5 — Shift note generator (`generate_shift_notes`)

The "tribal knowledge" doc type: informal first-person observations written at shift end,
before root causes are known. The hardest retrieval challenge in the corpus.

**What we built**
- `_SHIFT_NOTE_PROMPT` — instructs the LLM to write as a tired technician briefing the
  incoming crew: natural prose, no alarm codes, no headings, 3–6 sentences. Injects
  tool, chamber, symptom, and subsystem of concern.
- `_DISTRACTOR_SHIFT_PROMPT` — lighter version for routine uneventful shift notes.
- `generate_shift_notes(dry_run=False)` — 20 planted + 20 distractor docs. Corpus: 124
  docs total (7 + 37 + 40 + 40).

**Key things to understand**
- **Shift notes are the semantic search test.** A planted shift note for SIG-01 says
  "etch-rate drift and across-wafer non-uniformity... might be related to the RF matcher"
  — no alarm code `ALM-005`, no formal subsystem label `rf_match`. Keyword/BM25 search
  will struggle here; the dense vector retriever is what finds this doc by meaning. This
  is why we need hybrid search (dense + sparse), not just keyword search.
- **Three planted docs now exist for most signatures.** Alarm log (the alarm that fired) +
  work order (root cause + fix) + shift note (first observation, informal). The benchmark
  question "what caused the etch-rate drift on ETCH02?" now requires the agent to
  synthesize across all three — that's multi-document reasoning, which is the whole
  point of this architecture.
- **The prompt voice matters for retrieval quality.** Instructing the LLM to write
  informally ("you are briefing the incoming crew, not writing a formal report") produces
  vocabulary closer to how a technician would *query* the system — which improves
  semantic similarity between queries and documents at retrieval time.

**Decision & why (rejected alternative)**
- **No alarm codes in shift note prompt** — we explicitly told the LLM not to use them.
  Injecting an alarm code would make this doc retrievable by BM25 keyword match, hiding
  the retrieval challenge. The whole point is that shift notes are the fuzzy-language
  evidence that *only* semantic search can surface.
- **Same 20-distractor pattern as work orders** — consistency across doc types makes the
  corpus statistics predictable (signal-to-noise ratio is roughly equal across types).

**What could break**
- The LLM sometimes slips in slightly formal language despite the prompt. Acceptable
  variation; the semantic content (symptom + subsystem hints) is always present.

**Definition of done:** `uv run python scripts/generate_data.py` writes 124 docs;
planted shift note for SIG-01 is informal prose with no alarm code; 247 tests pass. ✓

---

## Milestone 2, Step 6 — SOP excerpt generator (`generate_sop_excerpts`)

The fifth and final doc type: procedural reference material indexed by subsystem, not
by failure event.

**What we built**
- `_SOP_PROMPT` — generates a 180–250-word OEM-style procedure with fixed headings:
  PURPOSE / SCOPE / PROCEDURE (numbered steps + thresholds) / ESCALATION. Injects
  subsystem name, applicable module types, procedure type, and a fake document ID.
- `_SOP_EXTRA_PROMPT` — shorter tool-specific checklist variant (120–180 words) for
  process-type-specific SOPs.
- `_SOP_PROCEDURE_TYPES` — five procedure flavours (inspection, PM, fault response,
  replacement, calibration) picked by RNG so not all SOPs read the same.
- `generate_sop_excerpts(dry_run=False)` — 20 primary SOPs (one per subsystem) +
  15 tool-specific extras = 35 docs. Corpus: 159 docs total.

**Key things to understand**
- **SOPs are the "recommended checks" source.** When the agent proposes next actions
  in its structured output (`recommended_checks`), it should be citing SOP procedures.
  A retrieved RF match SOP tells the agent to "verify impedance at 50 ± 2 Ω" — a
  concrete, actionable check it wouldn't generate from general knowledge alone.
- **SOPs are subsystem-indexed, not event-indexed.** Every subsystem has reference
  material regardless of whether it appears in a failure signature. This prevents the
  retriever from only returning docs that mention the failure — sometimes the most useful
  retrieved doc is a procedure, not a maintenance record.
- **`tool_id: None` on primary SOPs.** Subsystem SOPs apply across tools of the right
  module type, not to one specific tool. Setting `tool_id` to `None` means the Qdrant
  filter won't accidentally exclude them when the agent queries by tool — they'll always
  be in the pool for semantic retrieval. The 15 extras do carry a `tool_id` since they
  are process-specific.
- **159 docs is below the 300–350 target.** All five doc types are now seeded. The gap
  to target is filled in Step 7 (volume boost) by increasing distractor counts — no new
  doc types needed.

**Decision & why (rejected alternative)**
- **One SOP per subsystem** over one per signature — SOPs are reference material, not
  incident records. Tying them to signatures would mean most subsystems have no SOP and
  we'd miss the "recommended checks" retrieval case entirely.
- **Two-tier structure (primary + tool-specific extras)** over just 20 generic SOPs —
  tool-specific checklists add realistic variety and give the retriever something more
  specific to return when the query names a tool like "ALD01 precursor delivery."

**What could break**
- Primary SOPs have `tool_id: None`. The existing test suite checks tool_id is in
  `TOOLS` only for tool_summary docs, so this is fine. A future test for SOP docs
  should allow `None` explicitly.

**Definition of done:** `uv run python scripts/generate_data.py` writes 159 docs;
RF match SOP contains numbered steps with numeric thresholds; 247 tests pass. ✓

---

## Milestone 2, Step 7 — Volume boost + validation gate

Final step of Milestone 2. Brings corpus to target size and enforces taxonomy
consistency as a hard gate on every generation run.

**What we built**
- Increased distractor loop counts: alarm logs 22 → 110 iterations (~85 pass scope
  filter), work orders 20 → 70, shift notes 20 → 70, SOP extras 15 → 35.
- `validate_corpus(path)` — reads every line of corpus.jsonl and checks: `tool_id`
  (when not None) is in `TOOLS`; every entry in `alarm_codes` is in `ALARMS`. Returns
  a list of violation strings; empty list = clean.
- `main()` calls `validate_corpus()` after generation and exits non-zero on any
  violation — making the gate automatic on every full run.
- `TestCorpusValidation` in `tests/test_generate_data.py` (4 cases, skipif corpus
  absent): no taxonomy violations, ≥300 docs, all envelope fields present, unique
  doc_ids. 251 total tests pass.
- Final corpus: **345 docs** — 7 tool summaries + 103 alarm logs + 90 work orders +
  90 shift notes + 55 SOPs.

**Key things to understand**
- **The validation gate closes the consistency loop.** The taxonomy is the allow-list;
  the generator is the writer; the gate is the enforcer. Without it, an LLM that
  hallucinated "ALM-999" or "ETCH09" would silently corrupt the corpus. With it, bad
  refs fail the run loudly and get fixed before any doc reaches Qdrant.
- **Volume vs planted ratio.** Of 345 docs, 80 are planted signal (20 alarm logs +
  20 work orders + 20 shift notes + 20 tool summaries that reference signature issues)
  and 265 are noise. That's roughly a 1:3 signal-to-noise ratio — realistic for a
  working retrieval benchmark where recall isn't trivially easy.
- **Skipping corpus tests when the file doesn't exist** (`pytest.mark.skipif`) is the
  right pattern for tests that depend on generated artifacts. It keeps `uv run pytest`
  clean for anyone who hasn't run the generator yet, without hiding the tests.

**Decision & why (rejected alternative)**
- **Validation at generation time** (called from `main()`) over **validation only in
  pytest** — the generator is the production path; catching violations there prevents
  bad docs from ever being written to the corpus. The pytest is a second line of
  defence, not the primary one.

**Definition of done:** `uv run python scripts/generate_data.py` writes 345 docs and
prints "Validation passed"; `uv run pytest` → 251 passed. Milestone 2 complete. ✓

---

## Milestone 3, Step 1 — Qdrant via Docker + project README

**What we built**
- `docker-compose.yml` — pins Qdrant at `v1.18.2`, exposes ports 6333 (REST) and 6334
  (gRPC), and mounts a named Docker volume (`qdrant_storage`) so the index survives
  container restarts.
- `README.md` — full local setup guide: prerequisites, clone, `uv sync`, `.env`,
  `docker compose up -d`, corpus generation, index build, and repo structure map.

**Key things to understand**
- **Docker Compose** describes one or more containers in a single file and starts them
  with `docker compose up -d`. For us it's one container: Qdrant.
- **Named volumes** (`qdrant_storage:/qdrant/storage`) persist data on the host managed
  by Docker. If the container is deleted and recreated, the index is still there.
- **Port mapping** format is `host:container`. `"6333:6333"` means port 6333 on your
  machine routes to port 6333 inside the container.
- **Pinning the image version** (`v1.18.2` not `latest`) makes the setup reproducible —
  a new Qdrant release can't silently break the schema.

**Decision & why (rejected alternative)**
- **Pinned version** over `latest` — `latest` is convenient but means the server version
  can change between installs. We discovered this the hard way: the initial pin of `v1.9.2`
  was incompatible with `qdrant-client 1.18.0`, causing a storage format panic on upgrade.
  Fixed by aligning both to `v1.18.2`.

**What could break**
- If Qdrant releases a major version that changes the on-disk storage format, upgrading
  the Docker image requires deleting the volume and re-indexing (`--recreate`).

**Definition of done:** `docker compose up -d` → `curl localhost:6333/healthz` returns
`healthz check passed`. ✓

---

## Milestone 3, Step 2 — Embedding wrapper (`rag/embeddings.py`)

**What we built**
- `rag/embeddings.py` — a thin module wrapping OpenAI's `text-embedding-3-small`.
  Single public function: `embed(texts: list[str]) -> list[list[float]]`.
  Batches requests at 100 texts per API call to stay within limits.

**Key things to understand**
- **Embeddings** convert text into a fixed-length list of numbers (a vector). For
  `text-embedding-3-small`, each text → 1536 floats. Texts with similar meaning produce
  vectors that are geometrically close; dissimilar texts produce vectors far apart.
- **Why batch?** The API accepts up to 2048 texts per call. Batching at 100 is
  conservative and keeps memory usage predictable for large corpora.
- **Module-level client** (`_client = OpenAI()`) — created once on import, not on every
  call. Avoids repeated connection overhead.

**Decision & why (rejected alternative)**
- **Interface over direct calls** — callers use `embed()`, not `OpenAI().embeddings.create(...)`.
  This means swapping to a local model (e.g. `bge-small`) only requires changing this one
  module. The `_` prefix on `_client` signals it's an internal detail.

**What could break**
- `text-embedding-3-small` has an 8191-token context limit. Very long chunks would be
  silently truncated by the API. Our longest chunks (~2040 chars, ~500 tokens) are well
  within limit.

**Definition of done:** `embed(["test"])` returns one vector of length 1536. ✓

---

## Milestone 3, Step 3 — Structure-aware chunker (`ingest/chunk.py`)

**What we built**
- `ingest/chunk.py` — reads `corpus.jsonl` and produces 473 chunks from 345 documents.
  Short doc types (alarm_log, shift_note, tool_summary, work_order) are kept whole.
  SOP excerpts are split by section heading (PURPOSE / SCOPE / PROCEDURE / ESCALATION /
  CHECKLIST / NOTES) using a regex, yielding ~3–4 chunks per SOP.
- Every chunk carries the parent `doc_id` plus a `chunk_id` (`doc_id-N`) and all
  metadata fields (tool_id, subsystem, date, alarm_codes, etc.).

**Key things to understand**
- **Why chunk at all?** Embedding a 2000-character SOP as one vector averages across
  all its content. The PROCEDURE section (the useful bit) gets diluted by PURPOSE and
  SCOPE. Splitting by section lets retrieval surface the exact section that matches.
- **Why keep short docs whole?** alarm_logs (avg 307 chars) and shift_notes (avg 324
  chars) are too short to meaningfully split — you'd lose context and create tiny orphan
  chunks.
- **`doc_id` vs `chunk_id`** — the agent cites `doc_id` (the source document). `chunk_id`
  is internal to the index. Multiple chunks from one SOP share a `doc_id`.
- **Chunk sizes by type** (measured): alarm_log 236–412 chars; shift_note 198–531;
  work_order 847–1450; sop_excerpt 963–2040. Only SOPs warranted splitting.

**Decision & why (rejected alternative)**
- **Section-heading split** over fixed-size character chunking — fixed-size splits can
  cut mid-sentence. Section headings are natural semantic boundaries that the LLM put
  there intentionally. Rejected character-based sliding window chunking as overly
  mechanical for this structured corpus.

**What could break**
- The regex `_SOP_HEADING` relies on the LLM consistently using the heading names
  (PURPOSE, SCOPE, PROCEDURE, ESCALATION). If a generated SOP uses different headings,
  it falls back to a single whole-doc chunk (the `_whole()` fallback). Benign but means
  that SOP gets less precise retrieval.

**Definition of done:** `uv run python ingest/chunk.py` prints 473 total chunks
(103 alarm_log + 90 shift_note + 183 sop_excerpt + 7 tool_summary + 90 work_order). ✓

---

## Milestone 3, Steps 4–5 — Indexer + hybrid retriever (`ingest/index.py`, `rag/retriever.py`)

**What we built**
- `ingest/index.py` — creates a Qdrant collection with two vector slots per point:
  `"dense"` (1536-float OpenAI embedding) and `"bm25"` (sparse BM25 vector via fastembed).
  Upserts all 473 chunks with both vectors plus the full metadata payload.
  `--recreate` flag wipes and rebuilds; default is safe to re-run (skips if exists).
- `rag/retriever.py` — `search(query, k, tool_id?, doc_type?, subsystem?)` runs both
  vector types in parallel via Qdrant `Prefetch`, fuses ranked results with
  Reciprocal Rank Fusion (server-side), returns top-k chunk payloads.

**Key things to understand**
- **Dense search** (semantic): finds chunks whose meaning is close to the query, even
  with no shared words. "etch rate dropped" matches "process rate degraded".
- **Sparse search / BM25**: weighted keyword match. Rare terms score higher. Catches
  exact alarm codes (`ALM-005`), tool IDs, and jargon that semantic search might miss.
- **Reciprocal Rank Fusion**: for each result, computes `1 / (rank + 60)` from each
  sub-search and sums. Results appearing in both lists float to the top. The constant
  60 dampens the advantage of very high individual ranks.
- **Named vectors** — because we store two vector types, the collection uses a dict
  config (`{"dense": VectorParams(...), }`) and `sparse_vectors_config`. Each `PointStruct`
  carries `vector={"dense": [...], "bm25": SparseVector(...)}`.
- **`Modifier.IDF`** on the sparse config — tells Qdrant to apply Inverse Document
  Frequency weighting, so rare terms matter more than common ones (the defining property
  of BM25).
- **Metadata filter** (`_build_filter`) applied inside each `Prefetch` — scopes both
  searches before RRF runs. Filtering pre-index rather than post-retrieval is faster
  and more precise.
- **`Prefetch` limit of `k*3`** — each sub-search fetches 3× candidates so RRF has
  enough material to re-rank. If both returned only `k`, there'd be nothing to fuse.

**Decision & why (rejected alternative)**
- **Qdrant native BM25 sparse vectors** over client-side RRF with two separate searches —
  native sparse vectors let Qdrant do the fusion server-side (one round-trip, consistent
  scoring). Client-side RRF would require two API calls and manual merge logic.
- **fastembed `Qdrant/bm25`** over SPLADE neural sparse — BM25 is deterministic, needs
  no GPU, and adds no download overhead beyond a small tokenizer. SPLADE gives
  marginally better recall but adds model download complexity not needed at this scale.

**What could break**
- Changing `DIMENSIONS` or adding/removing vector slots requires `--recreate` and
  a full re-index. The collection schema is fixed at creation time.
- BM25 tokenizer files are cached in `~/.cache/fastembed` after first download. On a
  fresh machine the first `index.py` or `retriever.py` call fetches them (small, ~10MB).

**Definition of done:** `uv run python ingest/index.py` → 473 points in Qdrant;
smoke test returns planted SIG-01 documents as top hits for "etch rate drift". ✓

---

## Milestone 3, Step 6 — Retrieval smoke test (`scripts/smoke_retrieval.py`)

**What we built**
- `scripts/smoke_retrieval.py` — five representative queries printed with top-3 results,
  doc_id, doc_type, tool, subsystem, date, and a 200-char text preview.
  Tests: semantic symptom match, exact alarm code, subsystem failure phrase,
  tool+doc_type filter, subsystem+doc_type filter.

**Key things to understand**
- The smoke test is not a unit test — it's a manual sanity check that the full stack
  (corpus → chunker → embedder → Qdrant → retriever) produces sensible results for
  realistic queries before we build the agent on top.
- Planted documents (SIG-01 alarm log, work order, shift note) all surfaced in the
  top-3 for their corresponding queries. This confirms the corpus design works.
- BM25 correctly ranked `ALM-005` alarm logs at #1 for the exact code query; the dense
  component also pulled in a semantically related but code-free doc at #2 (expected).
- SOP chunking produced three chunks from one doc (SCOPE, PROCEDURE, PURPOSE) as
  separate results for the rf_source SOP query — the most relevant section (SCOPE) at #1.

**What could break**
- Results are non-deterministic if the corpus is regenerated with a different seed or
  if OpenAI embedding outputs change between model versions. The smoke test is
  qualitative, not asserted.

**Definition of done:** all five queries return relevant results; planted docs surface
for symptom queries; filters exclude non-matching doc types and tools. Milestone 3 complete. ✓

---

## Milestone 4, Step 1 — Output schema (`agent/schemas.py`)

**What we built**
- `agent/schemas.py` — two Pydantic models: `Cause` (cause description, confidence 0–1,
  supporting doc_ids) and `Diagnosis` (summary, ranked causes, recommended checks,
  citations, overall confidence).
- Both models export a JSON Schema via `model_json_schema()` that is passed directly
  to OpenAI's structured outputs API.

**Key things to understand**
- **Pydantic** validates data against type annotations at runtime. If the LLM returns
  a float where a string is expected, Pydantic raises immediately rather than letting
  bad data flow silently downstream.
- **JSON Schema export** — `Diagnosis.model_json_schema()` generates a standard JSON
  Schema dict. OpenAI's `response_format` parameter accepts this directly, instructing
  the model to return JSON that matches the shape exactly. No freeform text parsing.
- **`Field(ge=0.0, le=1.0)`** — Pydantic constraint that becomes `minimum`/`maximum`
  in the JSON Schema. The API rejects any response where confidence is out of range.
- **`description=` on every field** — these strings are model-facing instructions the
  LLM reads when deciding what to put in each field. They are part of the prompt.
- **Define the schema first** — the agent loop, UI, and eval harness all depend on this
  shape. Defining it last would mean retrofitting three components.

**Decision & why (rejected alternative)**
- **Pydantic over plain dataclasses** — Pydantic gives JSON Schema export for free,
  plus runtime validation. Plain dataclasses would require hand-writing the schema dict
  and add manual validation code.

**What could break**
- OpenAI structured outputs with `beta.chat.completions.parse` requires a model that
  supports the feature (gpt-4o and gpt-4o-mini do; older models don't).

**Definition of done:** `Diagnosis.model_json_schema()` returns valid JSON Schema with
all required fields and constraints. ✓

---

## Milestone 4, Step 2 — Agent tools (`agent/tools.py`)

**What we built**
- `agent/tools.py` — five tools, each with an OpenAI function schema and a Python
  implementation, plus a `dispatch(name, args)` router.
- `search_maintenance_docs` → calls `rag/retriever.search()` with optional filters.
- `lookup_alarm_code` → looks up a code in the taxonomy `ALARMS` dict.
- `get_tool_status` → reads `data/structured/tool_summaries.json`.
- `get_recent_alarms` → scrolls Qdrant for alarm_log chunks by tool + date window.
- `compute_mtbf` → computes days since last PM and whether the tool is overdue.

**Key things to understand**
- **OpenAI tool schema format** — each tool is a dict with `"type": "function"` and
  a `"function"` sub-dict containing `name`, `description`, and `parameters` (a JSON
  Schema object). The LLM reads `description` to decide when to call the tool and
  `parameters` to know what arguments to pass.
- **Two sides to every tool** — the schema (what the LLM sees) and the implementation
  (what Python runs). They are deliberately separate: the schema is model-facing
  prompt engineering; the implementation is deterministic data retrieval.
- **Error returns, not exceptions** — implementations return `{"error": "..."}` for
  bad inputs so the LLM sees the failure as a tool result and can recover (try a
  different argument, skip the tool, etc.) rather than crashing the whole run.
- **`dispatch(name, args)`** — a single entry point that maps tool name → function.
  The loop calls `dispatch(tc.function.name, json.loads(tc.function.arguments))` for
  every tool call the LLM makes. This keeps the loop generic — it doesn't know about
  individual tools.
- **`_` prefix on implementations** — signals they're internal; callers use `dispatch`.

**Decision & why (rejected alternative)**
- **Deterministic local data** for `get_tool_status`, `compute_mtbf`, `lookup_alarm_code`
  rather than letting the LLM infer from context — deterministic tools give the agent
  ground truth it can trust; hallucinated tool results would corrupt the diagnosis.
- **`get_recent_alarms` via Qdrant scroll** with client-side date filter — Qdrant stores
  dates as strings; ISO format sorts lexicographically so string comparison is correct.
  A numeric timestamp field would allow a `Range` filter server-side but adds indexing
  complexity not needed at this scale.

**What could break**
- `get_tool_status` and `compute_mtbf` read from `data/structured/tool_summaries.json`,
  which is gitignored. A fresh clone must run `generate_data.py` before the agent works.

**Definition of done:** all five tools return correct results via `dispatch()`; error
paths return `{"error": "..."}` dicts; unknown tool name handled. ✓

---

## Milestone 4, Steps 3–4 — Agent loop + tracer (`agent/loop.py`, `agent/traces.py`)

**What we built**
- `agent/loop.py` — the tool-calling loop in plain Python. Takes a query, alternates
  between LLM calls and tool execution until the LLM stops calling tools, then makes
  one final `beta.chat.completions.parse` call to extract a validated `Diagnosis`.
  Accepts an optional `Tracer` and a `verbose` flag.
- `agent/traces.py` — `Tracer` class that records query, tool calls (name/args/result/
  latency), iterations, usage, and total latency. `tracer.save()` appends one JSON line
  to `data/traces/traces.jsonl`.

**Key things to understand**
- **The loop pattern** — each iteration: send messages → LLM responds with tool_calls
  OR plain text → if tool_calls: execute + append results + loop → if no tool_calls:
  break. This is the primitive that LangGraph (Milestone 7) abstracts into a state graph.
- **Messages as a conversation** — the `messages` list grows with every turn: system
  prompt, user query, assistant tool_calls, tool results, next assistant turn... The LLM
  sees the full history each time, so it can reason about what it already tried.
- **Tool call message format** — the assistant message must include `"tool_calls"` with
  the call id, name, and arguments. The tool result message must reference the same
  `"tool_call_id"`. The API enforces this pairing — mismatched ids cause an error.
- **`for/else`** — Python runs the `else` block when a `for` loop completes without
  hitting `break`. Here it fires when `max_iterations` is reached, meaning the LLM never
  stopped calling tools voluntarily. We still proceed to get a structured answer.
- **`beta.chat.completions.parse`** — the OpenAI SDK's structured output helper. Pass
  `response_format=Diagnosis` (the Pydantic class) and it returns `message.parsed` as a
  validated `Diagnosis` instance. No `json.loads`, no manual schema dict, no validation code.
- **`tool_choice="auto"`** — LLM decides each turn whether to call a tool or not.
  `"required"` forces a call every turn; `"none"` disables tools.
- **Tracer is optional** — passing `tracer=None` (default) makes the loop behave
  identically without tracing. The eval harness will always pass a tracer.
- **JSONL traces** — one line per run, append-only. The eval harness reads these to
  score recall (were the right doc_ids cited?) and accuracy (did the diagnosis match?)
  without re-running the agent.

**Decision & why (rejected alternative)**
- **Two-phase approach** (tool loop then one final structured-output call) over
  combined `tools + response_format` in every call — the two-phase approach is simpler
  to reason about: phase 1 gathers evidence, phase 2 extracts the answer. Combining them
  requires careful prompt engineering to tell the model when to stop calling tools.
- **Messages as plain dicts** over passing `ChatCompletionMessage` objects — the SDK
  response object (`ChatCompletionMessage`) has a different type from the input
  parameter (`ChatCompletionMessageParam`). Building dicts explicitly keeps the structure
  visible and avoids implicit SDK coercion.

**What could break**
- `data/traces/` is gitignored (as it should be — generated data). The `.gitkeep` file
  ensures the directory exists in a fresh clone.
- Token limits: very long tool results or many iterations grow the `messages` list.
  At `max_iterations=8` with our tool payloads, we stay well within gpt-4o-mini's
  128k context window.

**Definition of done:** agent correctly identifies planted SIG-01 root cause (RF match
network, worn vacuum capacitor) at ≥85% confidence from a symptom query; trace saved to
JSONL with tool call sequence, token usage, and citations. ✓

---

## Milestone 4, Step 5 — End-to-end smoke test (`scripts/smoke_agent.py`)

**What we built**
- `scripts/smoke_agent.py` — runs three queries end-to-end with verbose output and
  tracing. Covers: planted etch signature (SIG-01), a particle contamination query
  (SIG-03 + SIG-20), and a deposition tool query (PECVD01).

**Key things to understand**
- The smoke test confirmed three system behaviours: (1) the agent recovers from a failed
  tool call (`lookup_alarm_code('ALM-XXX')` → error → agent continues correctly);
  (2) the retriever surfaces multiple distinct planted signatures for the same tool
  (SIG-03 edge ring + SIG-20 wafer handler both appeared for the particle query);
  (3) the agent generalises to deposition tools with no code changes.
- Three traces are saved to `data/traces/traces.jsonl` — one per run, appended.

**What could break**
- Results are non-deterministic (LLM temperature=default). Different runs may call
  slightly different tools or rank causes differently. The planted root causes should
  always surface, but exact confidence values will vary.

**Definition of done:** three queries return grounded diagnoses with planted doc_ids
in citations; traces saved; Milestone 4 complete. ✓

---

## Milestone 5 — Streamlit UI (`app/streamlit_app.py`)

**What we built**
- `app/streamlit_app.py` — a single-file web app that: takes a symptom query in a
  text area, runs the agent loop with a spinner, and renders the structured Diagnosis
  (summary, causes with confidence progress bars, recommended checks, citations).
- Sidebar filters for Tool ID and Subsystem — prepended to the query as context hints
  so the agent naturally uses them when calling `search_maintenance_docs`.
- Expandable "Tool calls" panel showing each tool name, latency, args, and result.
- Expandable "Run metadata" panel showing run_id, iterations, token usage, latency.
- `st.session_state` stores the diagnosis and trace between Streamlit reruns so
  results persist when the user interacts with expanders.

**Key things to understand**
- **Streamlit's execution model** — the entire script re-runs from top to bottom on
  every user interaction (button click, text input, expander toggle). `st.session_state`
  is a dict that persists across reruns, which is why we store the diagnosis there
  after the agent finishes rather than re-running the agent on every interaction.
- **No separate backend needed** — Streamlit runs in the same Python process as the
  agent. `from agent.loop import run` is a plain import. There is no HTTP API between
  the UI and the agent — for a local/portfolio tool this is the right tradeoff.
- **SSH port forwarding for remote access** — the app binds to `localhost:8501` on the
  server. To access it from a laptop without exposing the port publicly (which would
  bypass the firewall and allow unauthenticated access), use:
  `ssh -L 8501:localhost:8501 user@server`. Traffic travels over the encrypted SSH
  tunnel. Never open port 8501 on the firewall for a dev app with no auth.
- **Sidebar filters as query hints** — rather than adding `tool_id`/`subsystem`
  parameters to `run()`, we prepend them to the query string (e.g. "Tool: ETCH02.
  Subsystem: rf_source. [symptom]"). The agent reads them as context and passes them
  to `search_maintenance_docs` naturally. This keeps `run()` simple.

**Decision & why (rejected alternative)**
- **Single-file app** over splitting into components — Streamlit apps are naturally
  script-like. At this scale, splitting into multiple files adds navigation complexity
  with no benefit. One file is easy to read top to bottom.
- **SSH tunnel over opening port 8501** — exposing the port publicly would allow
  anyone to use the app and make API calls on our key. The tunnel gives the same access
  with no security tradeoff.

**What could break**
- Streamlit's rerun model means if the user edits the query while results are
  displayed, the old results stay until "Diagnose" is clicked again. This is expected
  behaviour, not a bug.
- The app requires both Qdrant (Docker) and a valid `OPENAI_API_KEY` to be running.
  Errors are caught and displayed via `st.error()`.

**Definition of done:** query entered in browser → agent runs → Diagnosis rendered
with causes, confidence bars, checks, citations, and tool call trace. Verified live
with "ETCH02 etch-rate drift" query returning correct root cause. Milestone 5 complete. ✓
