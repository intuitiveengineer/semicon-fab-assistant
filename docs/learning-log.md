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
