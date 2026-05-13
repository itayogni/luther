# Luther — WhatsApp Personal Assistant

A monorepo containing a WhatsApp personal assistant with a Python FastAPI backend and Node.js WhatsApp gateway.

## Structure

- `core/` — Python FastAPI backend (the brain)
- `gateway/` — Node.js WhatsApp gateway using Baileys

## Setup

### Python Backend

```bash
cd core
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
```

### Node.js Gateway

```bash
cd gateway
npm install
```

## Development

Start the Python backend:
```bash
cd core
.venv\Scripts\activate
uvicorn luther.main:app --reload
```

Start the Node.js gateway:
```bash
cd gateway
npm run dev
```
