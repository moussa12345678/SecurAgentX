import asyncio
import json

from agents.hybrid_agent import _extract_json
from tools.data_facility import DataFacility
from tools.exploitation import exploit_bola


class _Response:
    status = 200

    async def text(self):
        return json.dumps({"id": 2, "email": "other@example.test"})


class _RequestContext:
    async def __aenter__(self):
        return _Response()

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _Session:
    def get(self, *_args, **_kwargs):
        return _RequestContext()


def test_data_facility_builds_named_sections_when_services_unavailable():
    context = DataFacility().get_full_context("example.com", ["python"])

    assert context["target"] == "example.com"
    assert set(context["data_sections"]) == {
        "past_knowledge",
        "tool_recommendations",
        "vuln_knowledge",
        "payload_suggestions",
        "target_summary",
    }


def test_hybrid_json_extractor_handles_embedded_object_without_exception_variable_leakage():
    assert _extract_json("decision: {\"action\": \"finish\"} trailing") == {"action": "finish"}


def test_bola_proof_accepts_structured_auth_mapping_and_mapping_responses():
    proof = asyncio.run(
        exploit_bola(
            _Session(),
            "https://example.test/users/{id}",
            {"user_id": 1, "headers": {}, "cookies": {"session_id": "test-session"}},
        )
    )

    assert proof.data_extracted["extracted_users"]
    assert "session_id=test-session" in proof.curl_command
