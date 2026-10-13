from pathlib import Path

import pytest

from app.config import Settings
from app.models import JobRequestOptions
from app.services.llm_client import GeminiStoryPlanner
from app.storage import JobStore


def test_health_and_input_validation(client):
    assert client.get("/api/health").json()["default_video_provider"] == "mock"
    assert client.post("/api/jobs", data={"input_mode": "text"}).status_code == 400
    assert client.post("/api/jobs", data={"input_mode": "text", "input_text": "A robot", "clip_length_seconds": "10"}).status_code == 422
    assert client.get("/api/jobs?limit=-1").status_code == 422


def test_real_providers_need_explicit_credentials(client):
    for provider in ["veo_lite", "fal"]:
        result = client.post("/api/jobs", data={"input_mode": "text", "input_text": "A robot", "video_provider": provider})
        assert result.status_code == 400
        assert "KEY" in result.json()["detail"]


def test_mock_mode_does_not_call_gemini_even_with_a_key(tmp_path, monkeypatch):
    planner = GeminiStoryPlanner(Settings(_env_file=None, data_dir=tmp_path, video_provider="mock", gemini_api_key="test-only-never-used"))
    from google import genai

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Mock mode must not call external AI services")

    monkeypatch.setattr(genai, "Client", fail_if_called)
    graph = planner.plan_story_graph(None, JobRequestOptions(input_mode="text", input_text="A robot", video_provider="mock"))
    assert graph.root_id == "clip1"
    assert len(graph.nodes) >= 2


def test_job_store_rejects_traversal(tmp_path):
    store = JobStore(Settings(_env_file=None, data_dir=tmp_path))
    with pytest.raises(ValueError):
        store.job_dir("../private")
    job = store.create_job(original_filename=None, options=JobRequestOptions(input_mode="text", input_text="Robot"))
    with pytest.raises(ValueError):
        store.write_json(job.job_id, "../../outside.json", {})
    assert not (tmp_path / "outside.json").exists()


def test_asset_endpoint_rejects_paths_to_sibling_jobs(client):
    from app.main import store

    first = store.create_job(original_filename=None, options=JobRequestOptions(input_mode="text", input_text="Robot"))
    sibling = store.jobs_dir / f"{first.job_id}_private"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("fixture-only")
    result = client.get(f"/api/jobs/{first.job_id}/file/%2E%2E%2F{first.job_id}_private%2Fsecret.txt")
    assert result.status_code == 404


def test_normalized_plan_has_unique_nodes_and_a_valid_root(tmp_path):
    planner = GeminiStoryPlanner(Settings(_env_file=None, data_dir=tmp_path, node_count=3))
    graph = planner._normalize_plan({"root_id": "absent", "nodes": [{"id": "clip2"}, {"id": "clip2"}], "edges": []}, JobRequestOptions(input_mode="text", input_text="Robot"))
    ids = [node.id for node in graph.nodes]
    assert len(ids) == len(set(ids)) == 3
    assert graph.root_id in ids
    assert all(edge.source in ids and edge.target in ids for edge in graph.edges)


def test_mock_job_generates_playable_video_and_saved_graph(client):
    result = client.post("/api/jobs", data={"input_mode": "text", "input_text": "A robot learns to dance", "video_provider": "mock", "clip_length_seconds": "15"})
    assert result.status_code == 200, result.text
    job_id = result.json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed", job.get("error")
    assert job["progress"] == 1
    graph = client.get(f"/api/jobs/{job_id}/graph").json()
    assert len(graph["nodes"]) == 2
    clip = graph["nodes"][0]["filename"]
    video = client.get(f"/media/{job_id}/{clip}")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert len(video.content) > 1024
    assert b"ftyp" in video.content[:32]
    assert client.post(f"/api/jobs/{job_id}/retry").json()["status"] == "completed"
