import pytest

from securagentx.memory import VectorMemoryBackend


@pytest.mark.parametrize("remote_location", ["http://127.0.0.1:8000", "https://memory.example", "//remote/share"])
def test_vector_memory_rejects_remote_uri_locations(remote_location):
    with pytest.raises(ValueError, match="local filesystem path"):
        VectorMemoryBackend(remote_location)
