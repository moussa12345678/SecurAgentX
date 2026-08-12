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
