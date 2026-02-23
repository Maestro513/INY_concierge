# InsuranceNYou Backend

FastAPI backend for SOB PDF question-answering powered by Claude.

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Configure

Copy `.env.example` to `.env` and add your Anthropic API key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Add SOB PDFs

Drop SOB PDFs into the `pdfs/` folder, named by plan ID:
```
pdfs/H0028-007.pdf
pdfs/H5521-042.pdf
```

## Process PDFs

Extract and chunk the PDFs (run once, or after adding new PDFs):
```bash
python -m app.pdf_processor
```

This creates JSON files in `extracted/` with the chunked text.

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

API docs at: http://localhost:8000/docs

## Endpoints

- `GET /health` — health check
- `POST /ask` — ask a question about a member's plan

### Example /ask request:
```json
{
  "question": "What's my specialist copay?",
  "plan_id": "H0028-007"
}
```
