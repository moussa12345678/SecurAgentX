from unittest.mock import AsyncMock, Mock, patch

import pytest

from agents.redteam.base import AgentMessage, MessageBus, MessageType, MissionContext
from agents.redteam.planner import PlannerAgent
from agents.redteam.recon import ReconAgent
from agents.redteam.scanner import ScannerAgent
from securagentx.agent.vuln_agent import _tool_web_recon


@pytest.mark.asyncio
async def test_scanner_executes_single_vulnerability_through_standard_queue():
    scanner = ScannerAgent(MessageBus())

    result = await scanner.execute_task(
        {
            "type": "scan_vuln_type",
            "target": "example.com",
            "vuln_type": "xss",
            "technique_id": "T1059",
        }
    )

    assert result["status"] == "completed"
    assert result["target"] == "example.com"
    assert result["scans_completed"] == 1
    assert scanner.completed_scans[0].task.vuln_type == "xss"
    assert scanner.completed_scans[0].task.technique_id == "T1059"


@pytest.mark.asyncio
async def test_scanner_rejects_single_vulnerability_task_without_vulnerability_type():
    scanner = ScannerAgent(MessageBus())

    result = await scanner.execute_task({"type": "scan_vuln_type", "target": "example.com"})

    assert result == {"error": "scan_vuln_type requires a non-empty vuln_type"}


@pytest.mark.asyncio
async def test_scanner_waf_bypass_returns_only_unblocked_variants_without_growth():
    scanner = ScannerAgent(MessageBus())
    scanner.blocked_payloads.add("a%20b")

    result = await scanner.execute_task(
        {"type": "waf_bypass", "payload": "a b", "waf_type": "unknown"}
    )

    assert result["waf_type"] == "unknown"
    assert result["bypasses"] == ["a%09b", "a b"]


@pytest.mark.asyncio
async def test_scanner_routes_bus_task_to_result_message():
    bus = MessageBus()
    ScannerAgent(bus)
    received = []

    async def capture(message):
        received.append(message)

    bus.subscribe("captain", capture)
    message = AgentMessage(
        from_agent="captain",
        to_agent="scanner",
        message_type=MessageType.TASK,
        payload={"type": "waf_bypass", "payload": "a b", "waf_type": "unknown"},
    )

    await bus.publish(message)

    assert len(received) == 1
    assert received[0].message_type == MessageType.RESULT
    assert received[0].correlation_id == message.correlation_id
    assert received[0].payload["bypasses"]


@pytest.mark.asyncio
async def test_recon_routes_threat_intel_to_implemented_lookup():
    recon = ReconAgent(MessageBus())

    with patch.object(
        recon, "_threat_intel_lookup", new=AsyncMock(return_value={"source": "lookup"})
    ) as lookup:
        result = await recon.execute_task({"type": "threat_intel"})

    assert result == {"source": "lookup"}
    lookup.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_recon_routes_dns_and_ssl_tasks_to_active_implementations():
    recon = ReconAgent(MessageBus())

    with (
        patch.object(recon, "_dns_recon", new=AsyncMock(return_value={"dns_records": {}})) as dns_recon,
        patch.object(recon, "_ssl_cert_analysis", new=AsyncMock(return_value={"ssl_info": {}})) as ssl_recon,
    ):
        dns_result = await recon.execute_task({"type": "dns_enum"})
        ssl_result = await recon.execute_task({"type": "ssl_analysis"})

    assert dns_result == {"dns_records": {}}
    assert ssl_result == {"ssl_info": {}}
    dns_recon.assert_awaited_once_with()
    ssl_recon.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_recon_routes_bus_task_to_result_message():
    bus = MessageBus()
    ReconAgent(bus)
    received = []

    async def capture(message):
        received.append(message)

    bus.subscribe("captain", capture)
    message = AgentMessage(
        from_agent="captain",
        to_agent="recon",
        message_type=MessageType.TASK,
        payload={"type": "threat_intel"},
    )

    await bus.publish(message)

    assert len(received) == 1
    assert received[0].message_type == MessageType.RESULT
    assert received[0].correlation_id == message.correlation_id


@pytest.mark.asyncio
async def test_planner_routes_bus_task_to_result_message():
    bus = MessageBus()
    PlannerAgent(bus)
    received = []

    async def capture(message):
        received.append(message)

    bus.subscribe("captain", capture)
    message = AgentMessage(
        from_agent="captain",
        to_agent="planner",
        message_type=MessageType.TASK,
        payload={"type": "unsupported_task"},
    )

    await bus.publish(message)

    assert len(received) == 1
    assert received[0].message_type == MessageType.RESULT
    assert received[0].payload == {"error": "Unknown task type: unsupported_task"}


def test_vuln_agent_web_recon_upgrades_http_to_https():
    response = Mock(status_code=200, headers={"Server": "test"}, text="ok")

    with patch("requests.get", return_value=response) as request_get:
        result = _tool_web_recon("http://example.com", "/status")

    assert result["success"] is True
    request_get.assert_called_once()
    assert request_get.call_args.args[0] == "https://example.com/status"


@pytest.mark.asyncio
async def test_planner_publishes_full_tree_and_compact_update_without_overwrite():
    bus = MessageBus()
    planner = PlannerAgent(bus)
    received = []

    async def capture(message):
        received.append(message)

    bus.subscribe("observer", capture)
    await planner.initialize(MissionContext(target="example.com", scope=["example.com"]))

    result = await planner.execute_task(
        {
            "type": "generate_attack_tree",
            "target": "example.com",
            "tech_stack": {"app": "php"},
            "technologies": {"example.com": {"framework": "php"}},
        }
    )

    assert result["status"] == "completed"
    payload_types = [message.payload["type"] for message in received]
    assert payload_types == ["attack_tree", "attack_tree_update"]
    assert received[0].payload["tree"]["steps"]
    assert received[1].payload["tree_steps"] == result["tree"]["steps_count"]
