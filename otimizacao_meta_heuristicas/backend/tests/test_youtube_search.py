import json

from app import youtube_search


def _page_with_initial_data(payload: dict) -> str:
    return f"<html><script>var ytInitialData = {json.dumps(payload)};</script></html>"


SAMPLE_DATA = {
    "contents": {
        "results": [
            {
                "videoRenderer": {
                    "videoId": "abc123",
                    "title": {"runs": [{"text": "Flamengo x Palmeiras - Jogo completo"}]},
                    "ownerText": {"runs": [{"text": "Canal Futebol"}]},
                    "lengthText": {"simpleText": "1:52:30"},
                    "publishedTimeText": {"simpleText": "há 2 dias"},
                    "viewCountText": {"simpleText": "120 mil visualizações"},
                }
            },
            {
                "videoRenderer": {
                    "videoId": "def456",
                    "title": {"runs": [{"text": "Análise tática do Flamengo"}]},
                    "ownerText": {"runs": [{"text": "Scout BR"}]},
                    "lengthText": {"simpleText": "14:02"},
                }
            },
            # Duplicata do primeiro id: deve ser ignorada.
            {"videoRenderer": {"videoId": "abc123", "title": {"runs": [{"text": "Repetido"}]}}},
            # Sem titulo: descartado.
            {"videoRenderer": {"videoId": "ghi789"}},
        ]
    }
}


def test_search_youtube_videos_parses_real_video_metadata(monkeypatch):
    monkeypatch.setattr(youtube_search, "fetch_page", lambda url: _page_with_initial_data(SAMPLE_DATA))

    videos = youtube_search.search_youtube_videos("Flamengo jogo completo", limit=8)

    assert len(videos) == 2
    first = videos[0]
    assert first["id"] == "abc123"
    assert first["url"] == "https://www.youtube.com/watch?v=abc123"
    assert first["channel"] == "Canal Futebol"
    assert first["duration"] == "1:52:30"
    assert first["views"].startswith("120 mil")
    assert videos[1]["title"] == "Análise tática do Flamengo"


def test_search_youtube_videos_respects_limit(monkeypatch):
    monkeypatch.setattr(youtube_search, "fetch_page", lambda url: _page_with_initial_data(SAMPLE_DATA))

    videos = youtube_search.search_youtube_videos("Flamengo", limit=1)

    assert len(videos) == 1


def test_extract_yt_initial_data_raises_when_missing():
    import pytest

    with pytest.raises(ValueError):
        youtube_search._extract_yt_initial_data("<html>sem dados</html>")
