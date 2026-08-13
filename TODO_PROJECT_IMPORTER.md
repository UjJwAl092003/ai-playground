# Plan — Complete-Project JSON Importer (TODO)

## Goal
Make the JSON file the single source of truth for a complete Project. The
importer creates the Project automatically (if it doesn't exist) and imports
its questions. No manual Project creation required first.

## Behavior (approved)
- JSON root contains project-level fields + `questions[]`.
- Reuse existing Project/Question model fields (no model redesign).
- Validate the ENTIRE JSON before anything is written.
- Import Project + questions atomically (single transaction).
- If a Project with the same **slug** already exists:
  - Do NOT create a duplicate.
  - Show a clear conflict.
  - Allow ONLY "Add new questions while keeping existing project info unchanged".
  - Never overwrite existing project fields or existing questions.
- Preserve Markdown formatting and fenced ```python code blocks.
- Subject importer keeps working exactly as before.

## Steps
- [x] Service layer: add complete-project import family to `core/services/question_importer.py`
- [x] Admin views: repurpose project import views in `core/admin_views.py`
- [x] Templates: update project import/preview/result in `templates/admin/core/project/`
- [x] Tests: add `core/tests_project_importer.py`
- [x] Run full test suite (all tests pass, no regressions)
