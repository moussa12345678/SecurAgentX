from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"


def test_venom_does_not_persist_session_secrets_or_put_tts_key_in_url():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "apiKey:S.apiKey" not in source
    assert "tts:S.tts" not in source
    assert "text:synthesize?key=" not in source
    assert "X-Goog-Api-Key':S.tts.googleKey" in source


def test_venom_escapes_provider_test_output_and_discloses_free_voice_destination():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "this.esc(txt.slice(0,40))" in source
    assert "this.esc(e.message)" in source
    assert "Free voice mode sends spoken text to StreamElements" in source
    assert "connection timed out" in source
    assert "},15000);" in source


def test_venom_routes_registered_actions_to_the_local_control_plane():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "const VenomControl={" in source
    assert "'/api/venom/execute'" in source
    assert "'Authorization':'Bearer '+window.VENOM_CONTROL_TOKEN" in source
    assert "Term.run('venom '+action" in source
    assert "this.runControlAction('page_metadata',target)" in source
    assert "this.runControlAction('http_headers'" in source
    assert "this.runControlAction('audit_log')" in source
    assert "'venom audit','run venom tests','test venom'" in source
    assert "Venom control action was not executed" in source


def test_venom_validates_scope_before_changing_active_target():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "if(t.startsWith('use target '))return this.activateApprovedTarget" in source
    assert "VenomControl.execute('scope_validate',target)" in source
    assert "S.scope.targets=[approved]" in source
    assert "Scope was not changed" in source


def test_venom_controls_memory_and_skill_search_through_dashboard_state():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "if(t.startsWith('remember '))return this.remember" in source
    assert "if(t==='clear memory')" in source
    assert "if(t.startsWith('find skill '))return this.findSkills" in source
    assert "S.memory=S.memory.slice(-50)" in source
    assert "Term.run('venom find skill '+needle" in source
    assert "venom audit, run venom tests" in source
