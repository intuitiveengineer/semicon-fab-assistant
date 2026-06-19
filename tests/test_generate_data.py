"""Tests for scripts/generate_data.py — one suite per generator function."""

import json

import pytest

from scripts.generate_data import generate_tool_summaries
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
