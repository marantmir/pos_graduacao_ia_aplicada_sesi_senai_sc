import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app import crud_store as crud_store_module
from app import data_store as data_store_module
from app import database as database_module


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Point the sqlite history/profile store at a throwaway file per test."""
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "football_intelligence_test.db")
    database_module.init_db()
    yield


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Copy the JSON data collections to a throwaway dir so CRUD tests (and any
    test that writes) never mutate the real seed files under backend/data."""
    source = data_store_module.DATA_DIR
    temp_dir = tmp_path / "data"
    shutil.copytree(source, temp_dir)
    monkeypatch.setattr(data_store_module, "DATA_DIR", temp_dir)
    monkeypatch.setattr(crud_store_module, "DATA_DIR", temp_dir)
    data_store_module.load_json.cache_clear()
    yield
    data_store_module.load_json.cache_clear()


@pytest.fixture(autouse=True)
def no_network_llm(monkeypatch):
    """Never hit OpenAI/DuckDuckGo from tests; keep the deterministic fallback path."""
    from app import llm_assistant

    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "")


@pytest.fixture(autouse=True)
def isolated_llm_config(tmp_path, monkeypatch):
    """Point the LLM config file at a throwaway path so tests never write to
    the real backend/data/llm_config.json."""
    from app import llm_config as llm_config_module

    monkeypatch.setattr(llm_config_module, "CONFIG_PATH", tmp_path / "llm_config_test.json")
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Rate limiters are process-wide singletons; keep tests independent."""
    from app.rate_limit import video_upload_rate_limiter

    video_upload_rate_limiter.reset()
    yield
    video_upload_rate_limiter.reset()
