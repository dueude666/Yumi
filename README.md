# Yumi

Yumi is a local-first campus study assistant built on a standard PyTorch stack.
It is designed for offline deployment and local data residency.

## Current Features
- Course and material management (local text ingestion + chunking)
- Material file upload (`txt/md/pdf/image`) with OCR for image notes
- Classroom audio intelligent assistant:
  - offline lecture transcription + summary
  - custom terminology normalization
  - simple speaker diarization (Speaker A/B)
  - Anki flashcard CSV export
  - batch processing with progress visualization
- Note summarization (summary + keywords)
- Local QA with source excerpts
- Final-week schedule generation
- Fixed-event conflict avoidance (classes, meetings, commute)
- Plan analytics (hours by day/course + load stability)
- ICS export for calendar apps

## Tech Stack
- `PyTorch` + lightweight local NLP adapter (replaceable with larger local models)
- `FastAPI` for backend service
- `Streamlit` for local UI
- `SQLite` for local storage

## Quick Start
1. Install dependencies
```bash
pip install -r requirements.txt
```

2. Initialize DB
```bash
python scripts/init_db.py
```

3. Run API
```bash
python scripts/run_api.py
```

4. Run UI (new terminal)
```bash
python scripts/run_ui.py
```

Default URLs:
- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:8501`

## Mobile Use (Phone)
1. Ensure phone and computer are on the same Wi-Fi.
2. Start UI:
```bash
python scripts/run_ui.py
```
3. The script prints LAN address like `http://192.168.x.x:8501`.
4. Open that address on your phone browser.

Optional environment variables:
- `YUMI_UI_HOST` (default `0.0.0.0`)
- `YUMI_UI_PORT` (default `8501`)
- `YUMI_API_HOST` (default `127.0.0.1`)
- `YUMI_API_PORT` (default `8000`)
- `YUMI_DEV_RELOAD` (`1` to enable API hot reload)

## Scheduling Logic
Course priority score:

`priority = 0.35*urgency + 0.30*(1-mastery) + 0.20*difficulty + 0.15*credit_weight`

Planner rules:
- Deep block: default `90` minutes
- Review block: default `30` minutes
- Buffer time: default `20%`
- Mandatory reviews at `D-7`, `D-3`, `D-1`
- Fixed weekly events remove occupied intervals before planning

## Core API Endpoints
- `POST /courses`
- `GET /courses`
- `POST /courses/{course_id}/materials`
- `POST /courses/{course_id}/materials/upload`
- `POST /audio/process-upload`
- `GET /audio/transcripts?course_id=&limit=`
- `GET /audio/{transcript_id}/anki.csv`
- `POST /glossary/terms`
- `GET /glossary/terms`
- `POST /notes/summarize`
- `POST /qa/ask`
- `POST /planner/exams`
- `GET /planner/exams`
- `PUT /planner/availability`
- `GET /planner/availability`
- `POST /planner/fixed-events`
- `PUT /planner/fixed-events`
- `GET /planner/fixed-events`
- `POST /planner/final-week-plan`
- `GET /planner/events?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /planner/analysis?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /planner/export/ics?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&include_fixed=true`

## Database Tables
- `courses`
- `notes`
- `document_chunks`
- `exams`
- `availability_slots`
- `fixed_events`
- `study_events`

## Next Extensions
- Higher-accuracy domain ASR model packs
- FAISS embedding retrieval
- Personal knowledge graph per course

## Audio Assistant Positioning
- Problem solved:
  - students/teachers spend too much time turning lecture recordings into structured notes
  - manual transcription is slow and key points are hard to extract
- Core promise:
  - data stays on device from audio input to note output
  - no network requests during inference (except first-time model download if not cached)
- Typical scenarios:
  - lecture recording review
  - seminar archive
  - group discussion minutes
  - language listening recap
- Target users:
  - undergraduates (heavy coursework in engineering/medical majors)
  - postgraduates
  - teachers
  - self-learners

## OCR Runtime Note
Image OCR uses `pytesseract`, which requires local Tesseract OCR binary installation.
On Windows, install Tesseract and ensure `tesseract.exe` is in `PATH`.
