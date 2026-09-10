# Task 2: Safe Resume Extraction and Structured Context

## Scope

Implemented an isolated, static resume parser only. It has no route, database write, or persistence-lifecycle integration. It accepts raw upload bytes plus a trusted media type, produces redacted normalized text and deterministic `BACKGROUND_ONLY` candidate context, and never stores original binaries.

## Files

- `backend/requirements.txt`: bounded `pypdf` and `python-docx` dependencies.
- `backend/app/services/resume_schemas.py`: typed source segment, background item, candidate background, and parsed-context contracts.
- `backend/app/services/resume_parser.py`: bounded signature-checked TXT/PDF/DOCX extraction, redaction, hashing, and deterministic section bucketing.
- `backend/tests/test_resume_parser.py`: parser contract coverage.

## TDD evidence

RED:

1. Added parser contract tests before either parser production module existed.
2. `python -m pytest backend/tests/test_resume_parser.py -q` initially stopped because `python-docx` was unavailable to the Python 3.14 pytest interpreter.
3. After adding/installing the bounded dependencies, the same command failed with the expected `ModuleNotFoundError: backend.app.services.resume_parser`.

GREEN:

1. Implemented the smallest parser/schema surface for the tests.
2. `python -m pytest backend/tests/test_resume_parser.py -q` completed with `7 passed`.
3. `python -m pytest backend/tests/test_resume_models.py backend/tests/test_assessment_contracts.py -q` completed with `6 passed` (three pre-existing framework deprecation warnings).

## Safety behavior

- Rejects empty and >5 MiB uploads before extraction.
- Cross-checks extension against trusted MIME type and validates PDF/DOCX/TXT magic signatures.
- Rejects encrypted PDFs and gives stable corrupt/empty/signature error codes.
- Removes control characters; redacts email/phone values and drops address-like lines before source segments and structured context are created.
- Calculates SHA-256 from upload bytes; no binary is returned or persisted by this isolated parser.
- Treats all remaining text, including command-like text, as opaque document data.

## Verification

- `git diff --check -- backend/requirements.txt backend/app/services/resume_schemas.py backend/app/services/resume_parser.py backend/tests/test_resume_parser.py` exited 0.
- A staged `git diff --cached --check` is run immediately before the local commit.

## Known concerns

The focused regression suite emits existing FastAPI/Starlette deprecation warnings. The parser deliberately does not OCR scanned/image-only PDFs; their extracted text is empty and results in `RESUME_EMPTY`.
