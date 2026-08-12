import asyncio

from agents.redteam.base import AgentRole, MessageBus
from agents.redteam.captain import CaptainAgent


def test_register_agent_preserves_agent_role_enum():
    captain = CaptainAgent(MessageBus())

    captain.register_agent("recon", AgentRole.RECON)

    assert captain.registry.agents["recon"].role is AgentRole.RECON


def test_decide_exploit_chain_ignores_non_list_findings():
    captain = CaptainAgent(MessageBus())

    decision = asyncio.run(captain._decide_exploit_chain({"findings": "not-a-list"}))

    assert decision == {"decision": "individual", "reason": "insufficient_chain_potential"}


def test_decide_exploit_chain_filters_non_mapping_findings():
    captain = CaptainAgent(MessageBus())

    decision = asyncio.run(
        captain._decide_exploit_chain(
            {"findings": [{"type": "sqli"}, "invalid", {"type": "file_upload"}]}
        )
    )

    assert decision["decision"] == "chain"
    assert decision["chain"] == "sqli_to_rce"
