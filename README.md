# HN Graph

A tiny, zero-dependency app that snapshots the [Hacker News](https://news.ycombinator.com) front page every few minutes and plots how each story climbs (and falls) over the last 24 hours — like a CTF scoreboard, but for HN.

- **Hover** a line to see the story, its points, rank and comments.
- **Click** a line to open the story's discussion on Hacker News.
- Switch between **Points** and **Rank** views, and 6h / 12h / 24h ranges.

## Stack

- Python 3 standard library only (`http.server`, `sqlite3`, `urllib`) — no `pip install`.
- SQLite for storage.
- A single HTML page with [Apache ECharts](https://echarts.apache.org/).
- Data from the official [HN Firebase API](https://github.com/HackerNews/API).

## Run locally

```bash
python3 app.py
# open http://localhost:8000
```

The first snapshot is taken at startup, then every `POLL_INTERVAL` seconds.

## Deploy on a VPS (Docker)

```bash
git clone https://github.com/<you>/hn-graph.git
cd hn-graph
docker compose up -d --build
```

That's it — the app runs on port `8000` and the SQLite database lives in `./data/`.

To update:

```bash
git pull && docker compose up -d --build
```

### Optional: HTTPS with Caddy

```
hn.example.com {
    reverse_proxy localhost:8000
}
```

## Configuration

Set via environment variables (or a `.env` file next to `docker-compose.yml`):

| Variable         | Default      | Description                             |
| ---------------- | ------------ | --------------------------------------- |
| `POLL_INTERVAL`  | `300`        | Seconds between snapshots               |
| `TOP_N`          | `30`         | Number of front-page stories tracked    |
| `RETENTION_DAYS` | `7`          | Snapshots older than this are deleted   |
| `HOST_PORT`      | `8000`       | Host port (docker compose only)         |
| `DB_PATH`        | `data/hn.db` | SQLite file path                        |
| `PORT`           | `8000`       | HTTP port inside the app                |

## API

`GET /api/data?hours=24` returns every story seen on the front page in that window, with its time series of `[timestamp, score, rank, comments]`.

## License

MIT
