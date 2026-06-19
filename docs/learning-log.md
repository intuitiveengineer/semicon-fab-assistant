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
