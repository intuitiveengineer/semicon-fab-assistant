# Semiconductor Fab Maintenance Assistant

An AI agent that diagnoses semiconductor equipment failures from maintenance records.
Given a symptom query (e.g. "ETCH02 showing etch-rate drift"), the agent retrieves
relevant work orders, alarm logs, and SOPs, then returns a structured diagnosis with
likely causes, recommended checks, and citations.

**Stack:** Python · OpenAI API · Qdrant · Streamlit · Docker

---

## Project Status

| Milestone | Description | Status |
|-----------|-------------|--------|
| 1 | Domain taxonomy (tools, subsystems, alarms, failure signatures) | Done |
| 2 | Synthetic corpus generator (5 doc types, 345 documents) | Done |
| 3 | Retrieval layer (Qdrant + hybrid search) | Done |
| 4 | Agent v0 (tool-calling loop + structured output) | Done |
| 5 | Streamlit UI | Done |
| 6 | Evaluation benchmark | Planned |
| 7 | Agent v1 (LangGraph refactor) | Planned |

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Qdrant)
- An OpenAI API key

---

## Setup

### 1. Clone the repo

```bash
git clone git@github.com:intuitiveengineer/semicon-fab-assistant.git
cd semicon-fab-assistant
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your OpenAI API key:

```
OPENAI_API_KEY=sk-...
```

### 4. Start Qdrant

Qdrant runs as a local Docker container. Make sure Docker Desktop is running, then:

```bash
docker compose up -d
```

This starts Qdrant at `http://localhost:6333`. The dashboard is available at
`http://localhost:6333/dashboard`.

To stop it:

```bash
docker compose down
```

Data is persisted in a Docker volume (`qdrant_storage`) so the index survives restarts.

---

## Generating the Corpus

The synthetic document corpus is not committed to the repo (it lives in `data/`, which is
gitignored). To regenerate it:

```bash
uv run python scripts/generate_data.py
```

This calls the OpenAI API to generate ~345 documents across 5 doc types and writes them
to `data/corpus/corpus.jsonl`. Results are cached in `data/raw/` so re-runs are free.

To preview the generation plan without making API calls:

```bash
uv run python scripts/generate_data.py --dry-run
```

---

## Building the Search Index

Once the corpus is generated and Qdrant is running, ingest the corpus into Qdrant:

```bash
uv run python ingest/index.py
```

This chunks the documents, embeds them via OpenAI, and upserts them into a Qdrant
collection. Only needs to be run once (or after regenerating the corpus).

---

## Running the App

```bash
uv run streamlit run app/streamlit_app.py
```

The app runs on `http://localhost:8501`.

**On a remote server:** use SSH port forwarding to access it securely without opening firewall ports:

```bash
ssh -L 8501:localhost:8501 user@your-server-ip
```

Then open `http://localhost:8501` in your local browser.

---

## Running Tests

```bash
uv run pytest
```

---

## Repo Structure

```
data/{raw,corpus,structured}/   generated corpus (gitignored)
scripts/taxonomy.py             domain vocabulary (tools, alarms, signatures)
scripts/generate_data.py        synthetic corpus generator
ingest/{chunk,index}.py         build the Qdrant collection
rag/{embeddings,retriever}.py   hybrid search layer (dense + BM25)
agent/{tools,schemas,loop}.py   tool-calling agent
app/streamlit_app.py            Streamlit UI
eval/                           benchmark + evaluation harness
docker-compose.yml              Qdrant
.env.example                    environment variable template
docs/learning-log.md            decision history
```
