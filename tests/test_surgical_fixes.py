"""Regression tests for the surgical dead-code and HTTPS fixes."""

from unittest.mock import MagicMock, Mock, patch

from agents.agent_universal import process_universal
from agents.strategist_agent import ReconWorker
from core.brain import SecurAgentXAgent
from tools.perf import FastHTTP
from tools.python_recon import PythonRecon
from tools.smart_recon import SmartReconEngine


def test_recon_worker_returns_actionable_error_when_dns_finds_nothing():
    worker = ReconWorker()
    with patch("subprocess.run", return_value=Mock(returncode=1, stdout="")):
        result = worker.run("example.com")

    assert result.success is False
    assert result.error == "No recon tool available"


def test_universal_agent_invokes_supplied_context_overflow_check():
    overflow_check = Mock()
    client = Mock()
    client.chat.return_value = Mock(content="Hello")

    with (
        patch("agents.agent_universal.analyze_intent", return_value="casual"),
        patch("agents.agent_universal.get_context_for_ai", return_value=""),
        patch("agents.agent_universal._get_memory_profile_context", return_value=""),
        patch("agents.agent_universal._get_now_context", return_value="now"),
        patch("agents.agent_universal.get_universal_executor"),
        patch("agents.agent_universal.registry") as registry,
        patch("agents.agent_universal.remember"),
    ):
        registry.list_available_tools.return_value = {}
        result = process_universal(
            user_input="hello",
            client=client,
            conversation_history=[],
            base_prompt="test",
            governance=Mock(),
            check_context_overflow=overflow_check,
        )

    overflow_check.assert_called_once_with()
    assert result == "Hello"


def test_process_query_routes_smart_scan_flag_to_active_pipeline():
    agent = SecurAgentXAgent()
    callback = Mock()

    with patch.object(agent, "run_smart_scan", return_value="smart result") as smart_scan:
        result = agent.process_query(
            "scan example.com",
            target="example.com",
            use_smart_scan=True,
            callback=callback,
        )

    assert result == "smart result"
    smart_scan.assert_called_once_with("example.com")
    callback.assert_any_call("Using smart scan pipeline.")


def test_process_query_routes_new_pipeline_flag_to_hybrid_processor():
    agent = SecurAgentXAgent()
    callback = Mock()

    with patch.object(agent, "process_hybrid", return_value="hybrid result") as hybrid:
        result = agent.process_query(
            "scan example.com",
            target="example.com",
            use_new_pipeline=True,
            callback=callback,
        )

    assert result == "hybrid result"
    hybrid.assert_called_once_with("scan example.com", target="example.com", callback=callback)
    callback.assert_any_call("Using hybrid processing pipeline.")


def test_python_recon_normalizes_all_http_inputs_to_https():
    recon = PythonRecon()
    try:
        assert recon._normalize_url("example.com") == "https://example.com"
        assert recon._normalize_url("http://example.com/path") == "https://example.com/path"
        assert recon._normalize_url("https://example.com") == "https://example.com"
    finally:
        recon.close()


def test_smart_recon_probes_only_https():
    engine = SmartReconEngine("example.com")

    with patch("tools.smart_recon.requests.get", side_effect=Exception("offline")) as get:
        result = engine.probe_http("example.com")

    assert result is None
    assert get.call_args.args[0] == "https://example.com/"


def test_fast_http_upgrades_http_before_sending_request():
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Server": "test"}
    response.text = "ok"
    response.url = "https://example.com"
    session = Mock()
    session.get.return_value = response
    client = FastHTTP(use_cache=False)

    with patch.object(client, "_get_session", return_value=session):
        result = client.get("http://example.com")

    session.get.assert_called_once()
    assert session.get.call_args.args[0] == "https://example.com"
    assert result is not None
    assert result["url"] == "https://example.com"


def test_brain_fingerprint_upgrades_http_target_to_https():
    agent = SecurAgentXAgent()
    response = Mock(text="<html></html>", headers={})

    with (
        patch("requests.get", return_value=response) as request_get,
        patch("agents.agent_planner.TargetFingerprinter") as fingerprinter,
    ):
        fingerprinter.return_value.fingerprint.return_value = {"server": "test"}
        result = agent._fingerprint_target_for_planning("http://example.com")

    assert result == {"server": "test"}
    request_get.assert_called_once()
    assert request_get.call_args.args[0] == "https://example.com"
