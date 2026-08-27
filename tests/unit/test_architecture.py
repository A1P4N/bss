"""Architecture boundary tests."""

import pathlib


def test_replay_no_loader_import():
    text = pathlib.Path("src/bss/replay/replay_data_source.py").read_text()
    assert "historical_loader.application.download_service" not in text
    assert "HistoricalSource" not in text
    # ensure not importing analysis
    assert "from bss.analysis" not in text


def test_replay_no_http():
    text = pathlib.Path("src/bss/replay/replay_data_source.py").read_text()
    assert "httpx" not in text.lower()
    assert "requests" not in text.lower()


def test_event_model_no_replay():
    text = pathlib.Path("src/bss/event_model/envelope.py").read_text()
    assert "replay" not in text.lower()
    assert "from bss.replay" not in text
    assert "from bss.analysis" not in text


def test_event_model_no_networking():
    text = pathlib.Path("src/bss/event_model/envelope.py").read_text()
    assert "httpx" not in text.lower()


def test_loader_no_replay():
    # historical_loader domain/application/infrastructure should not import replay
    # CLI is allowed to import replay as thin adapter (AGENTS §26)
    import pathlib as p

    for path in p.Path("src/bss/historical_loader").rglob("*.py"):
        if "cli" in path.parts:
            continue
        txt = path.read_text()
        assert "from bss.replay" not in txt
        assert "import replay" not in txt
