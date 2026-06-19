"""Tests for scripts/generate_data.py — one suite per generator function."""

import json

import pytest

from scripts.generate_data import CORPUS_FILE, generate_tool_summaries, validate_corpus
from scripts.taxonomy import TOOLS

ENVELOPE_FIELDS = {"doc_id", "doc_type", "tool_id", "chamber", "alarm_codes", "subsystem", "date", "text", "metadata"}


class TestToolSummaries:
    docs = generate_tool_summaries()

    def test_one_doc_per_tool(self):
        assert len(self.docs) == len(TOOLS)

    def test_doc_ids_unique(self):
        ids = [d["doc_id"] for d in self.docs]
        assert len(ids) == len(set(ids))

    def test_envelope_fields_present(self):
        for doc in self.docs:
            missing = ENVELOPE_FIELDS - doc.keys()
            assert not missing, f"{doc['doc_id']} missing fields: {missing}"

    @pytest.mark.parametrize("tool_id", list(TOOLS))
    def test_tool_id_in_taxonomy(self, tool_id):
        doc = next(d for d in self.docs if d["tool_id"] == tool_id)
        assert doc["tool_id"] in TOOLS

    def test_text_is_nonempty_string(self):
        for doc in self.docs:
            assert isinstance(doc["text"], str) and len(doc["text"]) > 20

    def test_metadata_chambers_match_taxonomy(self):
        for doc in self.docs:
            tool = TOOLS[doc["tool_id"]]
            assert doc["metadata"]["chambers"] == tool.chamber_ids()

    def test_serialisable_to_json(self):
        for doc in self.docs:
            json.dumps(doc)  # must not raise


@pytest.mark.skipif(not CORPUS_FILE.exists(), reason="corpus not generated yet — run scripts/generate_data.py first")
class TestCorpusValidation:
    def test_no_taxonomy_violations(self):
        errors = validate_corpus()
        assert not errors, f"{len(errors)} violation(s):\n" + "\n".join(errors)

    def test_corpus_meets_minimum_size(self):
        count = sum(1 for _ in CORPUS_FILE.open())
        assert count >= 300, f"Corpus has only {count} docs — expected ≥ 300"

    def test_all_docs_have_required_envelope_fields(self):
        required = {"doc_id", "doc_type", "tool_id", "chamber", "alarm_codes", "subsystem", "date", "text", "metadata"}
        for line in CORPUS_FILE.open():
            doc = json.loads(line)
            missing = required - doc.keys()
            assert not missing, f"{doc.get('doc_id')} missing: {missing}"

    def test_doc_ids_are_unique(self):
        ids = [json.loads(line)["doc_id"] for line in CORPUS_FILE.open()]
        dupes = [i for i in ids if ids.count(i) > 1]
        assert not dupes, f"Duplicate doc_ids: {set(dupes)}"
