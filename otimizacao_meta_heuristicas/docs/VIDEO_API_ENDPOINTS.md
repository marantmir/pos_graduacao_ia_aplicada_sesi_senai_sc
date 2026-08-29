# Video Analysis API Endpoints

Complete reference for video analysis streaming endpoints with examples.

## Overview

The Video Analysis API supports three main operations:
1. **Upload videos** (file or URL)
2. **Stream analysis** (real-time WebSocket)
3. **Manage videos** (status, cleanup)

## HTTP Endpoints

### POST /api/videos/upload
Upload a video file for analysis.

**Parameters:**
- `file` (multipart/form-data): Video file (MP4, AVI, MOV)
- `team_names` (optional): JSON string with team names
  ```json
  {"0": "Flamengo", "1": "Botafogo"}
  ```

**Example:**
```bash
curl -X POST \
  -F "file=@match.mp4" \
  -F "team_names={\"0\": \"Manchester United\", \"1\": \"Liverpool\"}" \
  http://localhost:8000/api/videos/upload
```

**Response:**
```json
{
  "video_id": "match",
  "filename": "match.mp4",
  "size_bytes": 52428800,
  "duration_seconds": 120.0,
  "fps": 30.0,
  "resolution": "1920x1080",
  "total_frames": 3600,
  "status": "uploaded"
}
```

### POST /api/videos/upload-url
Upload a video from URL for analysis.

**Parameters:**
- `video_url` (query): Full URL to video file
- `filename` (optional): Custom filename
- `team_names` (optional): JSON string with team names

**Example:**
```bash
curl -X POST "http://localhost:8000/api/videos/upload-url?video_url=https://example.com/video.mp4&team_names=%7B%220%22%3A%20%22Team%20A%22%2C%20%221%22%3A%20%22Team%20B%22%7D"
```

**Python Example:**
```python
import requests

params = {
    'video_url': 'https://example.com/video.mp4',
    'filename': 'video.mp4',
    'team_names': '{"0": "Team A", "1": "Team B"}'
}

response = requests.post(
    'http://localhost:8000/api/videos/upload-url',
    params=params
)

data = response.json()
print(f"Video ID: {data['video_id']}")
print(f"Source: {data['source']}")  # 'url'
```

**Response:**
```json
{
  "video_id": "video",
  "filename": "video.mp4",
  "size_bytes": 52428800,
  "duration_seconds": 120.0,
  "fps": 30.0,
  "resolution": "1920x1080",
  "total_frames": 3600,
  "status": "uploaded",
  "source": "url"
}
```

### GET /api/videos/status/{video_id}
Get video processing status and metadata.

**Example:**
```bash
curl http://localhost:8000/api/videos/status/match
```

**Response:**
```json
{
  "video_id": "match",
  "status": "ready",
  "metadata": {
    "duration_seconds": 120.0,
    "fps": 30.0,
    "total_frames": 3600,
    "resolution": "1920x1080"
  }
}
```

### GET /api/videos/stream/{video_id}
Download/stream the video file.

**Example:**
```bash
curl -o output.mp4 http://localhost:8000/api/videos/stream/match
```

### DELETE /api/videos/clean/{video_id}
Clean up video and free resources.

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/videos/clean/match
```

**Response:**
```json
{
  "status": "cleaned",
  "video_id": "match"
}
```

## WebSocket Endpoint

### WebSocket /api/videos/ws/stream/{video_id}
Real-time streaming of frame analysis data.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/videos/ws/stream/match');
```

### Message Types

#### 1. Metadata (Initial)
Sent immediately upon connection with video information.

```json
{
  "type": "metadata",
  "duration_seconds": 120.0,
  "fps": 30.0,
  "total_frames": 3600,
  "resolution": "1920x1080",
  "team_names": {
    "0": "Team A",
    "1": "Team B"
  },
  "source": "file"
}
```

#### 2. Frame Data (Continuous)
Sent for each processed frame with player positions and analysis.

```json
{
  "type": "frame_data",
  "frame_idx": 120,
  "timestamp": 4.0,
  "teams": {
    "0": [
      {
        "player_id": 0,
        "x": 52.5,
        "y": 34.0,
        "distance_traveled": 45.2,
        "trajectory": [
          [52.0, 34.1],
          [52.2, 34.05],
          [52.5, 34.0]
        ]
      }
    ],
    "1": [
      {
        "player_id": 11,
        "x": 60.0,
        "y": 30.0,
        "distance_traveled": 38.5,
        "trajectory": [
          [59.8, 30.2],
          [59.9, 30.1],
          [60.0, 30.0]
        ]
      }
    ]
  },
  "total_players": 22,
  "proximities": [
    {
      "source": 0,
      "target": 5,
      "distance": 45.2,
      "same_team": true
    },
    {
      "source": 0,
      "target": 11,
      "distance": 8.5,
      "same_team": false
    }
  ]
}
```

**Field Descriptions:**
- `frame_idx`: Frame number (0-indexed)
- `timestamp`: Time in seconds
- `teams`: Player data grouped by team (0 or 1)
  - `player_id`: Unique player identifier
  - `x`, `y`: Position on field (meters, 0-105 × 0-68)
  - `distance_traveled`: Total distance since start (meters)
  - `trajectory`: Last N positions for trail visualization
- `total_players`: Total active players in frame
- `proximities`: List of player pairs within range
  - `source`, `target`: Player IDs
  - `distance`: Distance between players (meters)
  - `same_team`: Whether players are on same team

#### 3. Completion
Sent when video processing is complete.

```json
{
  "type": "complete",
  "total_frames": 3600,
  "message": "Vídeo processado com sucesso"
}
```

#### 4. Error
Sent if an error occurs during processing.

```json
{
  "type": "error",
  "message": "Error description"
}
```

## JavaScript Example

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/api/videos/ws/stream/match');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'metadata') {
    console.log('Video duration:', message.duration_seconds);
    console.log('Teams:', message.team_names);
  } 
  else if (message.type === 'frame_data') {
    console.log(`Frame ${message.frame_idx}: ${message.total_players} players`);
    console.log('Proximities:', message.proximities.length);
    
    // Process frame data
    message.teams['0'].forEach(player => {
      console.log(`Team A Player ${player.player_id}: (${player.x}, ${player.y})`);
    });
  } 
  else if (message.type === 'complete') {
    console.log('Processing complete');
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected');
};
```

## Python Example

```python
import asyncio
import websockets
import json

async def analyze_video():
    uri = "ws://localhost:8000/api/videos/ws/stream/match"
    
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            
            if data['type'] == 'metadata':
                print(f"Duration: {data['duration_seconds']}s")
                print(f"Teams: {data['team_names']}")
            
            elif data['type'] == 'frame_data':
                print(f"Frame {data['frame_idx']}: {data['total_players']} players")
                
                for team_id, players in data['teams'].items():
                    print(f"  Team {team_id}: {len(players)} players")
                    for player in players[:2]:  # First 2 players
                        print(f"    Player {player['player_id']}: ({player['x']:.1f}, {player['y']:.1f})")
            
            elif data['type'] == 'complete':
                print("Complete!")
                break
            
            elif data['type'] == 'error':
                print(f"Error: {data['message']}")
                break

asyncio.run(analyze_video())
```

## Error Handling

### Common Errors

**404 - Video Not Found**
```json
{"detail": "Vídeo não encontrado"}
```

**500 - Server Error**
```json
{"detail": "Error message"}
```

### Best Practices

1. **Always close WebSocket properly**
   ```javascript
   ws.close(1000, 'Normal closure');
   ```

2. **Handle reconnection**
   ```javascript
   function connectWithRetry(videoId, retries = 3) {
     for (let i = 0; i < retries; i++) {
       try {
         return new WebSocket(`ws://.../${videoId}`);
       } catch (e) {
         if (i === retries - 1) throw e;
         await sleep(1000 * Math.pow(2, i));
       }
     }
   }
   ```

3. **Validate input**
   ```python
   if not video_url.startswith(('http://', 'https://')):
       raise ValueError("Invalid URL")
   ```

## Rate Limiting

No rate limiting currently enforced, but recommended:
- Max 10 concurrent uploads
- Max 50 concurrent streams
- Max 100 videos per hour

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| File upload | Depends on size | Streaming recommended |
| URL download | 5-60s | Depends on bandwidth |
| Frame processing | ~10-50ms | Per frame |
| WebSocket latency | <100ms | Network dependent |

## Monitoring

Monitor these metrics:
- Video processing queue size
- Active WebSocket connections
- Error rate per endpoint
- Average frame processing time

## Future Enhancements

- [ ] Batch video upload
- [ ] Video quality selection
- [ ] Pause/resume processing
- [ ] Progress callbacks
- [ ] Rate limiting
- [ ] Authentication/API keys
- [ ] Video caching
- [ ] Statistics export

---

**Last Updated:** 2026-07-16
**API Version:** 1.0
