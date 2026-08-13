# TODO — Coding Exercise Importer with Auto-Numbering

## Goal
Build the complete Coding Exercise feature from scratch, mirroring the MCQ
importer architecture, with auto-numbering scoped per lesson.

## Steps
- [x] Add `CodingLesson` and `CodingExercise` models to `core/models.py`
- [x] Generate + apply migration for the new models
- [x] Create `core/services/coding_exercise_importer.py` (validation, auto-numbering, atomic import)
- [x] Register models in `core/admin.py` + mount the 4-step importer URLs
- [x] Add the 4-step importer views to `core/admin_views.py`
- [x] Create 4 admin templates (upload, preview, result, change_list)
- [x] Write tests in `core/tests_coding_exercise_importer.py`
- [x] Run `manage.py check`, `makemigrations`, `migrate`
- [x] Run full test suite (no regressions) — 132 tests pass
- [x] Wire coding lessons into `subject_detail` view + template (subject → coding lesson → exercise flow)
- [x] Verify URLs resolve and Django system check passes after integration
</content>
