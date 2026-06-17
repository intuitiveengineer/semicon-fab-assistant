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
