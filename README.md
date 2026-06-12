# ChassisUI

ChassisUI is an authenticated AI chat web app built with FastAPI, PostgreSQL, static frontend pages, JWT auth, and streamed model responses.

## What It Does

- Provides signup, login, and authenticated chat pages.
- Stores users, conversations, messages, and model metadata in PostgreSQL.
- Streams assistant responses from a local model endpoint.
- Supports reconnect/resume behavior for interrupted streams.
- Includes a shared-stream manager so the same model response can feed the frontend, background persistence, and resume clients without duplicate model calls.
- Includes model-management pages for user-owned models and weighted endpoints.

## Project Shape

The backend lives mostly in `main.py`, `routes.py`, `auth.py`, `database.py`, `schemas.py`, and `model_endpoint.py`. The frontend is in `static/`. Test and diagnostic scripts cover streaming, resume behavior, analytics, and model setup.

## Development

Create a `.env` from `.env.example`, configure PostgreSQL/JWT settings, then run the FastAPI app with Uvicorn.

```bash
uvicorn main:app --reload
```

## Recovery Notes

Hardcoded local database/JWT defaults from the recovered snapshot were replaced with environment-variable lookups. The implementation is a prototype: stream state is in process memory, CORS is permissive, and `routes.py` carries a lot of application logic.
