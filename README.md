# AI-Powered Onboarding Help Desk

**AI-first onboarding assistance delivered as a secure full-stack product.**

This project combines a production-ready FastAPI backend, a React (Vite) interface,
and a retrieval-augmented generation (RAG) pipeline to turn internal documentation
into reliable, contextual answers for employees.

**Start here:** follow the [Quick run](#quick-run) guide to launch the complete stack.

## Why it matters

New employees often lose time searching through scattered documentation or waiting
for answers to recurring questions. This platform turns approved onboarding content
into an accessible knowledge assistant: document ingestion → semantic indexing →
grounded answer generation → source-aware delivery → quality evaluation.

## What the product delivers

**AI value**

1. **Grounded onboarding answers** generated from the organization's own documents.
2. **Semantic retrieval and reranking** to surface the most relevant context.
3. **Quality and fallback diagnostics** to evaluate answers and identify knowledge gaps.

**Product value**

1. **Conversational workspace** with authentication, history, feedback, and suggested questions.
2. **Administration portal** for documents, users, contacts, conversations, and evaluations.
3. **REST API** for secure integrations and enterprise workflows.

## RAG approach (high level)

This solution prioritizes grounded, observable answers over unsupported generation:

- **Document ingestion** extracts and segments approved PDF and DOCX content.
- **Vector retrieval** uses Ollama embeddings and Qdrant to find relevant passages.
- **Semantic reranking** improves context selection before answer generation.
- **Conversation memory** preserves useful context across an exchange.
- **Evaluation and observability** track relevance, latency, fallbacks, and user feedback.

Uploaded business documents and generated vector data are stored outside Git and are
not included in this public repository.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, Pydantic
- **Frontend:** React 19, Vite, React Router, Vitest
- **AI / RAG:** LlamaIndex, Ollama, Qdrant
- **Data:** PostgreSQL 16
- **Infrastructure:** Docker Compose, Nginx

## Repo structure

```text
Assistant_Help_Desk/
├── backend/              # FastAPI API, RAG services, migrations, scripts, and tests
│   ├── alembic/          # Database migrations
│   ├── app/              # API, models, schemas, and application services
│   ├── scripts/          # Setup, ingestion, evaluation, and admin utilities
│   └── tests/            # Backend test suite
├── frontend/             # React (Vite) user and administration interfaces
├── .env.example          # Environment configuration template
└── docker-compose.yml    # Complete local application stack
```

## Quick run

### Prerequisites

- Docker Engine with Docker Compose v2
- Ollama installed locally or available on a private network
- Around 16 GB of system RAM recommended for the default `llama3` model

### 1. Prepare Ollama

```bash
ollama pull llama3
ollama pull nomic-embed-text
ollama serve
```

Ollama must be reachable from Docker. The default configuration uses
`http://host.docker.internal:11434`.

### 2. Configure the application

```bash
cp .env.example .env
```

Replace every `replace-with-...` value in `.env`. In particular, use strong values
for `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, and `INITIAL_ADMIN_PASSWORD`. Never commit
the local `.env` file.

### 3. Start the stack

```bash
docker compose up -d --build
docker compose ps
```

The web interface is available at `http://localhost:8080`, and the API health check
at `http://localhost:8001/health`.

### 4. Create the first administrator

```bash
set -a
. ./.env
set +a
docker compose exec \
  -e INITIAL_ADMIN_EMAIL \
  -e INITIAL_ADMIN_PASSWORD \
  -e INITIAL_ADMIN_NAME \
  api-staging python scripts/create_initial_admin.py
```

Sign in through the web interface, open **Administration → Documents**, and upload
the PDF or DOCX files that should power the assistant.

## Development and tests

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

Backend (Python 3.11 recommended):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Security notes

- Keep PostgreSQL, Qdrant, Ollama, and the backend API off the public Internet.
- Place the frontend behind HTTPS in production.
- Store production credentials in a dedicated secrets manager.
- Back up PostgreSQL, Qdrant snapshots, and uploaded documents together.
- Reindex the documents whenever the embedding model changes.

## Supported document formats

- PDF (`.pdf`)
- Microsoft Word (`.docx`)
