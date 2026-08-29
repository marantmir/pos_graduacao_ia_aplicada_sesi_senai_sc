"""Tests for Video Analysis Streaming - video processor and WebSocket routes."""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import numpy as np
import json

from backend.app.video_analysis.video_processor import (
    FrameData,
    VideoMetadata,
    VideoStreamProcessor,
    RealTimeGraphBuilder,
)
from backend.app.routes.video_analysis import router, active_processors


class TestFrameData:
    def test_create_frame_data(self):
        """Create frame data instance."""
        positions = {0: (100.0, 200.0, 0), 1: (150.0, 250.0, 1)}
        frame = FrameData(
            frame_idx=10,
            timestamp=0.33,
            player_positions=positions,
            detections_count=2,
        )
        assert frame.frame_idx == 10
        assert frame.timestamp == 0.33
        assert len(frame.player_positions) == 2

    def test_frame_data_ball_position(self):
        """Frame data with ball position."""
        frame = FrameData(
            frame_idx=10,
            timestamp=0.33,
            player_positions={},
            ball_position=(300.0, 200.0),
        )
        assert frame.ball_position == (300.0, 200.0)


class TestVideoMetadata:
    def test_create_metadata(self):
        """Create video metadata."""
        meta = VideoMetadata(
            filepath="/path/to/video.mp4",
            total_frames=300,
            fps=30.0,
            width=1920,
            height=1080,
            duration_seconds=10.0,
        )
        assert meta.filepath == "/path/to/video.mp4"
        assert meta.total_frames == 300
        assert meta.fps == 30.0
        assert meta.duration_seconds == 10.0


class TestVideoStreamProcessor:
    def test_create_processor(self):
        """Create video stream processor."""
        processor = VideoStreamProcessor(buffer_size=30)
        assert processor.buffer_size == 30
        assert len(processor.frame_buffer) == 0

    def test_simulate_player_detection(self):
        """Simulate player detection."""
        processor = VideoStreamProcessor()

        # Create a mock frame
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        positions = processor._simulate_player_detection(frame, frame_idx=0)

        # Should have 22 players (11 per team)
        assert len(positions) == 22

        # Each position should be (x, y, team_id)
        for player_id, (x, y, team_id) in positions.items():
            assert isinstance(x, float)
            assert isinstance(y, float)
            assert team_id in [0, 1]
            assert 0 <= x < 1920
            assert 0 <= y < 1080

    def test_simulate_player_detection_varies_over_frames(self):
        """Player positions vary over frames."""
        processor = VideoStreamProcessor()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        pos1 = processor._simulate_player_detection(frame, frame_idx=0)
        pos2 = processor._simulate_player_detection(frame, frame_idx=10)

        # Positions should be different
        for player_id in pos1:
            x1, y1, _ = pos1[player_id]
            x2, y2, _ = pos2[player_id]
            # Some players should have moved
            assert (x1, y1) != (x2, y2) or player_id != 0


class TestRealTimeGraphBuilder:
    def test_create_builder(self):
        """Create real-time graph builder."""
        builder = RealTimeGraphBuilder(frame_window=30)
        assert builder.frame_window == 30
        assert len(builder.frame_history) == 0
        assert len(builder.player_tracks) == 0

    def test_update_with_frame_data(self):
        """Update builder with frame data."""
        builder = RealTimeGraphBuilder()

        frame = FrameData(
            frame_idx=0,
            timestamp=0.0,
            player_positions={0: (100.0, 200.0, 0), 1: (150.0, 250.0, 1)},
        )

        builder.update(frame)

        assert len(builder.frame_history) == 1
        assert len(builder.player_tracks) == 2

    def test_frame_history_window(self):
        """Frame history respects window size."""
        builder = RealTimeGraphBuilder(frame_window=3)

        for i in range(10):
            frame = FrameData(
                frame_idx=i,
                timestamp=i * 0.033,
                player_positions={0: (100.0 + i, 200.0, 0)},
            )
            builder.update(frame)

        # Should only keep last 3 frames
        assert len(builder.frame_history) == 3
        assert builder.frame_history[0].frame_idx == 7

    def test_get_current_graph_data(self):
        """Get current graph data."""
        builder = RealTimeGraphBuilder()

        for i in range(5):
            frame = FrameData(
                frame_idx=i,
                timestamp=i * 0.033,
                player_positions={
                    0: (100.0 + i, 200.0, 0),
                    1: (150.0 + i, 250.0, 1),
                },
            )
            builder.update(frame)

        graph_data = builder.get_current_graph_data()

        assert "frame_idx" in graph_data
        assert "timestamp" in graph_data
        assert "teams" in graph_data
        assert "total_players" in graph_data
        assert graph_data["total_players"] == 2

    def test_calculate_proximities(self):
        """Calculate player proximities."""
        builder = RealTimeGraphBuilder()

        # Two players close together
        frame = FrameData(
            frame_idx=0,
            timestamp=0.0,
            player_positions={
                0: (100.0, 100.0, 0),
                1: (105.0, 100.0, 0),  # 5 units away
                2: (200.0, 200.0, 1),  # Far away
            },
        )
        builder.update(frame)

        proximities = builder.calculate_proximities()

        # Should have at least one proximity (0 and 1)
        assert len(proximities) >= 1

        # Check structure
        for prox in proximities:
            assert "source" in prox
            assert "target" in prox
            assert "distance" in prox
            assert "same_team" in prox

    def test_distance_calculation(self):
        """Verify distance calculation is correct."""
        builder = RealTimeGraphBuilder()

        frame = FrameData(
            frame_idx=0,
            timestamp=0.0,
            player_positions={
                0: (100.0, 100.0, 0),
                1: (103.0, 104.0, 0),  # distance = 5
            },
        )
        builder.update(frame)

        proximities = builder.calculate_proximities()
        assert len(proximities) == 1

        prox = proximities[0]
        assert prox["distance"] == pytest.approx(5.0, rel=0.01)


class TestVideoAnalysisRoutes:
    def test_upload_video_endpoint(self):
        """Test video upload endpoint."""
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake video content")
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                response = client.post(
                    "/api/videos/upload",
                    files={"file": f},
                )

            assert response.status_code == 200
            data = response.json()
            assert "video_id" in data
            assert "filename" in data
            assert "size_bytes" in data
            assert data["status"] == "uploaded"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_get_status_endpoint(self):
        """Test status endpoint."""
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # First upload a video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake video content")
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                upload_response = client.post(
                    "/api/videos/upload",
                    files={"file": f},
                )

            video_id = upload_response.json()["video_id"]

            # Get status
            status_response = client.get(f"/api/videos/status/{video_id}")
            assert status_response.status_code == 200

            data = status_response.json()
            assert data["video_id"] == video_id
            assert data["status"] == "ready"
            assert "metadata" in data
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            # Clean up
            if video_id in active_processors:
                del active_processors[video_id]

    def test_clean_endpoint(self):
        """Test video cleanup endpoint."""
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # Create a temporary video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake video content")
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                upload_response = client.post(
                    "/api/videos/upload",
                    files={"file": f},
                )

            video_id = upload_response.json()["video_id"]

            # Clean
            clean_response = client.delete(f"/api/videos/clean/{video_id}")
            assert clean_response.status_code == 200

            data = clean_response.json()
            assert data["status"] == "cleaned"
            assert data["video_id"] == video_id

            # Video should no longer exist
            assert video_id not in active_processors
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass

    def test_status_nonexistent_video(self):
        """Test status for non-existent video."""
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        response = client.get("/api/videos/status/nonexistent")
        assert response.status_code == 404


class TestRealTimeGraphBuilderIntegration:
    def test_progressive_frames(self):
        """Test processing multiple frames progressively."""
        builder = RealTimeGraphBuilder(frame_window=10)

        # Simulate 20 frames
        for frame_idx in range(20):
            positions = {}
            for player_id in range(22):
                # Create some movement
                team_id = 0 if player_id < 11 else 1
                x = 100.0 + (frame_idx * 5) + (player_id % 11) * 20
                y = 200.0 + (player_id // 11) * 100
                positions[player_id] = (x, y, team_id)

            frame = FrameData(
                frame_idx=frame_idx,
                timestamp=frame_idx / 30.0,
                player_positions=positions,
            )
            builder.update(frame)

        # Check final state
        graph_data = builder.get_current_graph_data()
        assert graph_data["total_players"] == 22
        assert graph_data["frame_idx"] == 19

        # Check proximities are calculated
        proximities = builder.calculate_proximities()
        assert len(proximities) > 0

    def test_team_separation_in_graph_data(self):
        """Teams should be separated in graph data."""
        builder = RealTimeGraphBuilder()

        frame = FrameData(
            frame_idx=0,
            timestamp=0.0,
            player_positions={
                0: (100.0, 100.0, 0),
                1: (110.0, 100.0, 0),
                2: (200.0, 100.0, 1),
                3: (210.0, 100.0, 1),
            },
        )
        builder.update(frame)

        graph_data = builder.get_current_graph_data()
        teams = graph_data.get("teams", {})

        # Should have both teams
        assert "0" in teams or 0 in teams
        assert "1" in teams or 1 in teams


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
