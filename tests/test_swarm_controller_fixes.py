from tools.swarm_controller import SwarmConfig, SwarmController, SwarmResult


def test_critical_swarm_result_aborts_without_display_callback():
    controller = SwarmController(SwarmConfig(max_concurrent=1, abort_on_critical=True))
    target = controller.load_targets_from_list(["https://example.com"])[0]

    def critical_result(*_args, **_kwargs):
        return SwarmResult(
            target_id=target.target_id,
            target_url=target.target_url,
            success=True,
            findings=[{"severity": "critical", "title": "synthetic regression finding"}],
            mission_summary={},
            duration_seconds=0.0,
        )

    controller._run_single_target = critical_result

    results = controller.run([target], display_callback=None)

    assert len(results) == 1
    assert results[0].findings[0]["severity"] == "critical"
    assert controller.abort_event.is_set()
