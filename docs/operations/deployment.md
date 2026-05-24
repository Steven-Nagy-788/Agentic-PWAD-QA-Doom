# CI/CD Pipeline

```mermaid
flowchart LR
  A([Push / PR]) --> B{CI Pipeline}
  B --> C[Backend tests<br/>Python 3.11 / pytest]
  B --> D[MCP Doom tests<br/>Python 3.11 / ViZDoom]
  B --> E[Frontend checks<br/>Bun 1.3 / test + lint + build]

  subgraph C [Backend — ubuntu-latest]
    direction TB
    C1[setup-python 3.11<br/>pip cache]
    C2[apt: ffmpeg, libcairo2,<br/>libpango, libharfbuzz,<br/>libgdk-pixbuf]
    C3[venv + pip install<br/>-r requirements.txt]
    C4[pytest -q]
    C1 --> C2 --> C3 --> C4
  end

  subgraph D [MCP Doom — ubuntu-latest]
    direction TB
    D1[setup-python 3.11<br/>pip cache]
    D2[apt: libgl1, libsdl2-2.0-0]
    D3[venv + pip install<br/>-e ".[dev]"]
    D4[pytest -q]
    D1 --> D2 --> D3 --> D4
  end

  subgraph E [Frontend — ubuntu-latest]
    direction TB
    E1[setup-bun 1.3]
    E2[bun install<br/>--frozen-lockfile]
    E3[bun run test]
    E4[bun run lint]
    E5[bun run build]
    E1 --> E2 --> E3 --> E4 --> E5
  end
```

## Trigger

| Event | Branches |
|---|---|
| `push` | `**` (all branches) |
| `pull_request` | all |

## Jobs

### 1. Backend tests

| Step | Action |
|---|---|
| Checkout | `actions/checkout@v4` |
| Python | `actions/setup-python@v5` — Python 3.11, pip cache keyed on `Backend/requirements.txt` |
| System deps | `apt-get install ffmpeg libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0` |
| Python deps | `.venv/bin/pip install -r requirements.txt` |
| Run tests | `.venv/bin/python -m pytest -q` |

Working directory: `Backend`

### 2. MCP Doom tests

| Step | Action |
|---|---|
| Checkout | `actions/checkout@v4` |
| Python | `actions/setup-python@v5` — Python 3.11, pip cache keyed on `mcp-doom/pyproject.toml` |
| System deps | `apt-get install libgl1 libsdl2-2.0-0` (ViZDoom runtime) |
| Python deps | `.venv/bin/pip install -e ".[dev]"` |
| Run tests | `.venv/bin/python -m pytest -q` |

Working directory: `mcp-doom`

### 3. Frontend checks

| Step | Action |
|---|---|
| Checkout | `actions/checkout@v4` |
| Bun | `oven-sh/setup-bun@v2` — Bun 1.3 |
| Install | `bun install --frozen-lockfile` |
| Test | `bun run test` |
| Lint | `bun run lint` |
| Build | `bun run build` |

Working directory: `frontend`
