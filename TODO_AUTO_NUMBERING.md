# Plan — Auto-Numbering for JSON Importers (TODO)

## Goal
Add an explicit "Automatically continue question numbering" checkbox to both
the Subject importer and the Complete-Project importer. When checked, the
importer ignores `question_number` values in the JSON, detects the highest
existing question number for the selected Subject/Project, and assigns fresh
sequential numbers from `max + 1`.

## Behavior (approved)
- Unchecked (default): preserve `question_number` values exactly (backward
  compatible).
- Checked: ignore JSON numbers; assign `max_existing + 1 ... max_existing + n`.
- Never modify or overwrite existing questions.
- Preview shows: existing question count, starting number, ending number, and
  a per-question mapping (JSON Question N → Database Question M).
- When auto-numbering is ON, duplicate `question_number` values inside the
  JSON are NOT treated as errors (fresh numbers are assigned anyway).
- When auto-numbering is OFF, duplicate numbers remain errors (unchanged).
- Confirm step re-checks the max number (race-condition guard) and re-assigns.

## Steps
- [x] Service layer: add `get_max_question_number`, `assign_sequential_numbers`,
      `apply_auto_numbering`; thread `auto_number` through validation
- [x] Admin views: read checkbox, persist in session, show mapping in preview,
      re-check + re-assign in confirm (subject + complete-project)
- [x] Templates: add checkbox to upload forms; show numbering summary + mapping
      in previews; show mode + range in results (subject + project)
- [x] Tests: run full test suite (all 101 tests pass, no regressions)
- [ ] Tests: (optional) add dedicated auto-numbering unit tests for Subject
      and Complete-Project importers (service-level functions already verified
      via the app test suite)
