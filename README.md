# Tashih

> A web-based proofreading workbench for text extracted from PDF files.
> The AI marks potential errors; the human proofreader (*musahhih*) always has the final word.

[🇹🇷 Türkçe](README.tr.md)

---

## Overview

Many documents still circulate as PDFs — books, theses, official records, articles — and their
text needs to be proofread before republication, archiving, or data entry. **Tashih** turns
this into a guided, side-by-side workflow:

1. **Extract** — the original PDF page and its extracted text are shown next to each other.
2. **Suggest** — an AI model reviews the text and proposes corrections (spelling, typos,
   OCR artifacts, punctuation, consistency).
3. **Review** — the proofreader accepts, rejects, or edits each suggestion.
4. **Export** — the corrected text is exported (and optionally written back into a
   clean PDF/DOCX) together with a change log.

The human stays in control: AI suggestions are *never* applied automatically.

## Key Features

- 📄 **PDF upload & text extraction** — preserves page/paragraph structure where possible.
- 🔍 **Side-by-side view** — original PDF page image vs. editable extracted text.
- 🎈 **Margin correction bubbles** — every suggestion is located on the original PDF page (via the text layer, **no OCR**) and shown as a color-coded bubble in the page margin: red = deletion, green = insertion, dark purple = replacement.
- 🖊️ **Musahhih (author) marks** — the proofreader clicks a word on the page image and marks it
  directly: **Delete · Replace · Insert · Space · Join**. The change is applied to the text at once
  and shown as a bubble on the page.
- 🤖 **AI-assisted suggestions** — spelling, grammar, punctuation, and OCR-noise detection.
- ✅ **Accept / reject / edit workflow** — every change is explicit and auditable.
- 📝 **Inline editing** — the proofreader can freely edit the text beyond AI suggestions.
- 🧾 **Change log** — full diff (original → corrected) with who changed what and when.
- 📑 **Batch processing** — queue multiple PDFs and track progress per document.
- 💾 **Autosave & resume** — interrupted sessions can be continued where they left off.
- 📤 **Correction JSON export** — one file with `corrections` (author marks) and `aiSuggestions`
  (AI proposals), ready for the *Musahhih* desktop app.
- 🌐 **Bilingual UI** — Turkish and English interfaces.

## How It Works

```
┌────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  PDF upload│ ──▶ │  Text        │ ──▶ │  AI analysis  │ ──▶ │  Proofreader │
│            │     │  extraction  │     │  (suggestions)│     │  review UI   │
└────────────┘     └──────────────┘     └───────────────┘     └──────┬───────┘
                                                                     │
                   ┌──────────────┐     ┌───────────────┐           │
                   │  Export      │ ◀── │  Change log   │ ◀─────────┘
                   │  (TXT/MD/DOCX│     │  & final text │
                   └──────────────┘     └───────────────┘
```

## Tech Stack (planned)

| Layer      | Technology |
|------------|------------|
| Backend    | Python 3.11+, FastAPI, SQLAlchemy, SQLite/PostgreSQL |
| PDF parsing| PyMuPDF (fitz) / pdfplumber |
| AI layer   | OpenAI-compatible LLM API (pluggable provider) |
| Frontend   | React + Vite, TypeScript |
| Deploy     | Docker / Docker Compose |

> The stack is a proposal and may be adjusted during implementation.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- An API key for an LLM provider (OpenAI, Anthropic, or a local model)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/osmanselvi/tashih.git
cd tashih

# 2. Backend
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your API key

# 3. Frontend
cd ../web
npm install

# 4. Run (in two terminals)
cd ../server && uvicorn app.main:app --reload     # http://localhost:8000
cd ../web && npm run dev                           # http://localhost:5173
```

### Docker (alternative)

```bash
docker compose up --build
# App: http://localhost:3000  |  API: http://localhost:8000
```

### Apache2 (local deployment)

On a machine with Apache2 installed, Apache serves the built frontend and
proxies `/api` to uvicorn:

```bash
# 1. Build the frontend
cd web && npm install && npm run build && cd ..

# 2. Enable proxy modules (once) and install the vhost
sudo a2enmod proxy proxy_http
sudo cp web/apache/tashih.conf /etc/apache2/sites-available/tashih.conf
sudo a2ensite tashih
sudo systemctl reload apache2   # or: sudo apache2ctl restart

# 3. Run the backend (e.g. as a service or in a terminal)
cd server && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The vhost uses `ServerName tashih.local`, so the app is reachable at
`http://tashih.local` — add `127.0.0.1 tashih.local` to `/etc/hosts` (or change
`ServerName` to your own domain). If the repository is not at
`/var/www/opencd`, adjust `DocumentRoot` in
`/etc/apache2/sites-available/tashih.conf`. The vhost serves `web/dist` as an
SPA (unknown paths fall back to `index.html`) and forwards `/api/*` to the
backend.

### Tests

Backend tests run in-process (no running server needed):

```bash
cd server
python -m pytest -q
```

## Usage

1. Open the web UI and **upload a PDF** (or pick one from the queue).
2. Review the **extracted text** next to the original page; fix extraction issues first if needed.
3. Click **"Analyze with AI"** to generate suggestions.
4. Walk through suggestions with **Accept / Skip / Edit** — or ignore them and edit manually.
5. When finished, **export** the corrected text (`.txt`, `.md`, `.docx`) and download the change log.

## Project Structure

```
tashih/
├── server/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # App entry point (also serves built frontend)
│   │   ├── config.py       # Settings from env
│   │   ├── db.py           # SQLAlchemy engine & session
│   │   ├── models.py       # DB models
│   │   ├── schemas.py      # Pydantic schemas (API contract)
│   │   ├── api/
│   │   │   ├── documents.py    # Upload, pages, image, export, analyze
│   │   │   ├── suggestions.py  # Accept / reject / undo
│   │   │   └── common.py       # Serialization helpers
│   │   └── services/
│   │       ├── extractor.py    # PDF → text + page PNGs
│   │       ├── analyzer.py     # AI / rule-based suggestions
│   │       └── exporter.py     # Results → txt / md / docx
│   ├── Dockerfile
│   ├── .env.example
│   └── requirements.txt
├── web/                    # React + Vite frontend
│   ├── Dockerfile, apache/tashih.conf
│   └── src/
│       ├── pages/          # DocumentList (queue), Review (workbench)
│       ├── components/     # SuggestionCard, ChangeLogPanel
│       └── api.ts, types.ts, i18n.ts, styles.css
├── README.md               # This file (English)
├── README.tr.md            # Turkish version
└── docker-compose.yml
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for the AI provider; if empty, rule-based analysis is used | — |
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |
| `LLM_MODEL`   | Model to use for suggestions | `gpt-4o-mini` |
| `DATABASE_URL`| Database connection string | `sqlite:///./data/tashih.db` |
| `DATA_DIR`    | Storage folder (uploads, page images, database) | `./data` |
| `MAX_UPLOAD_MB` | Maximum PDF upload size | `50` |
| `LANG` | Default UI language (`tr` / `en`) | `tr` |

## Roadmap

- [ ] PDF upload & page-accurate text extraction
- [ ] Side-by-side proofreading UI
- [ ] AI suggestion engine (spelling/OCR/punctuation)
- [ ] Accept/reject workflow + change log
- [ ] Export to TXT / MD / DOCX
- [ ] Multi-user accounts & assignment of documents to proofreaders
- [ ] Glossary / custom dictionary support
- [ ] Two-pass workflow (first pass: OCR cleanup, second pass: language edit)

## Contributing

Contributions are welcome. Open an issue first to discuss significant changes, then send a
pull request with a clear description of the problem and solution.

## License

MIT — see [LICENSE](LICENSE) for details.
