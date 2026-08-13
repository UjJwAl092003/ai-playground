# Project TODO — Interactive MCQ Learning Platform

## Completed Steps

- [x] **Step 1: Application shell** — Django project + `core` app + base template + home page
- [x] **Step 2: Subject & Question models** — `Subject`, `Question` (with explanation, python_code, practical_example)
- [x] **Step 3: MCQ learning flow** — Learn page shell, question data/check JSON endpoints, explanation rendering, Next Question
- [x] **Step 4: Authentication + Progress** — Registration, login/logout, dashboard, profile, `UserProgress` model, Continue Learning
- [x] **Step 5: Markdown rendering** — XSS-safe `markdown.js` renderer for question_text code blocks
- [x] **Step 6: Admin panel + content** — Subject/Question admin, JSON importer, search/filter, edit/delete

## Step 7: Review Mistakes Feature

- [x] `core/views.py` — Added `review_mistakes`, `review_learn`, `review_questions_api` (+ subject-filtered variants)
- [x] `core/urls.py` — Added `/review/`, `/review/subject/<slug>/`, `/review/learn/`, `/review/subject/<slug>/learn/`, review API endpoints
- [x] `templates/core/review_mistakes.html` — Mistake list page grouped by subject, with Review All buttons
- [x] `templates/core/learn.html` — Review-mode banner, review mode JS config (`reviewMode: true`, `mistakes`)
- [x] `templates/core/dashboard.html` — "Review Mistakes" panel with mistake count
- [x] `static/js/learn.js` — Review mode navigation (load first mistake, next mistake, try again, review complete state)
- [x] `static/css/style.css` — Review mistakes page + review mode banner styles
- [x] `core/tests_review.py` — 23 tests covering guest access, empty state, filtering, removal, isolation, regressions
- [x] Ran `manage.py check` — no issues
- [x] Ran `manage.py test core.tests_review` — **23/23 OK**
- [x] Ran `manage.py test core` — **53/53 OK** (no regressions)

## Review Mode — Project Support (DONE)

- [x] `static/js/learn.js` — Review navigation now builds the correct API URL per mistake (subject OR project) using `content_type` + `slug` from the mistake list
- [x] `templates/core/learn.html` — Passes `reviewProjectSlug` config for project-filtered review
- [x] `core/views.py` — `review_learn` / `review_questions_api` pass `review_project_slug` to the template; project mistakes are grouped under `project` content type
- [x] Full suite — **71/71 OK**

## Test Commands

```powershell
venv\Scripts\python manage.py check
venv\Scripts\python manage.py test core -v 2
venv\Scripts\python manage.py runserver
```

