# Engineer Chat Bot

Prototype internal AI assistant for the Engineering application.

## Current target

- Ollama + Llama 3.2 3B
- Standalone Python API
- PostgreSQL connector prepared for the existing Engineering database
- Demo/mock mode so the prototype can run before connecting to the office database
- Ready to package as a Windows `.exe`
- No GitHub Actions / CI

## Architecture

Engineering VB App (future)
        |
        | HTTP
        v
EngineerAI.exe
        |
        +--> PostgreSQL (office)
        |
        +--> Ollama -> llama3.2:3b

For the prototype, PostgreSQL can be unavailable and the application uses demo data.

## Requirements

- Windows
- Python 3.11+
- Ollama installed locally
- Llama 3.2 3B model

Install model:

```text
ollama pull llama3.2:3b
```

Install Python dependencies:

```text
pip install -r requirements.txt
```

Run:

```text
python main.py
```

API:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

## Demo mode

By default:

```DEMO_MODE=true```

This allows the prototype to work without the office database.

Example:

```text
POST /chat

{
  "question": "Berapa project aktif?"
}
```

The response identifies that the answer is coming from demo data.

## Office database

When the office PostgreSQL connection is available, configure:

```text
DEMO_MODE=false
DB_HOST=...
DB_PORT=5432
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
```

Do not commit real company credentials.

## EXE build

Run:

```text
build.bat
```

Output:

```text
dist/EngineerAI.exe
```

The EXE is the AI gateway. Ollama and its model remain separate during this prototype phase.
