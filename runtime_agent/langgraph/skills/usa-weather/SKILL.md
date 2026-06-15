---
name: usa-weather
description: >
  US weather news skill powered by NOAA feeds.
  Use when the user asks about US weather updates, NOAA announcements,
  or energy-demand impacts related to US weather events.

  Triggers include:
  - US weather news: "NOAA", "미국 날씨", "미국 기상", "weather news", "에너지 날씨"
  - General: weather-related energy demand analysis for US weather events
---

# usa-weather

## US Weather News (NOAA)

Run `scripts/fetch_noaa_news.py` via `execute_code`:

```python
import subprocess, sys
result = subprocess.run(
    [sys.executable,
     'skills/usa-weather/scripts/fetch_noaa_news.py',
     '--days', '7', '--max', '10', '--format', 'text'],
    capture_output=True, text=True
)
print(result.stdout)
```

**Key options**:
| Flag | Default | Description |
|------|---------|-------------|
| `--days` | 7 | Look-back window in days |
| `--max` | 10 | Max articles to return |
| `--pages` | 2 | NOAA pages to scan |
| `--format` | text | `text` or `json` |

**Output includes**: article title, date, URL, energy impact summary, relevance score (0–100).
