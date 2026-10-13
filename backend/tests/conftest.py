import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

_data = TemporaryDirectory(prefix="interactive-video-tests-")
os.environ["DATA_DIR"] = _data.name
os.environ["VIDEO_PROVIDER"] = "mock"
os.environ["NODE_COUNT"] = "2"
os.environ["GEMINI_API_KEY"] = ""
os.environ["FAL_KEY"] = ""


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
