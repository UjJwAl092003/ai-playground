# Projects Feature — TODO

## Step 1: Models
- [x] Add `Project` model (title, slug, short_description, description, overview, complete_code, output, explanation, learning_outcomes, dataset_info, thumbnail, order, is_active, is_free, access_type, created_at, updated_at)
- [x] Make `Question.subject` nullable
- [x] Add `Question.project` nullable FK
- [x] Add CheckConstraint: exactly one of subject/project must be set
- [x] Add partial unique constraints: (subject, question_number) and (project, question_number)
- [x] Update `UserProgress.__str__` to handle project questions
- [x] Create migration (0004) and apply it
- [x] Install Pillow + add to requirements.txt

## Step 2: Admin
- [x] Register `Project` in admin with full fieldsets
- [x] Add Project JSON importer admin views (upload → preview → confirm → result)
- [x] Update `QuestionAdmin` to show subject OR project clearly
- [x] Update admin changelist template to add Project JSON import button

## Step 3: JSON Importer (project support)
- [x] Extend `question_importer.py` with project import functions
- [x] Add project importer admin views in `admin_views.py`
- [x] Create project import admin templates

## Step 4: Views & URLs
- [ ] Add `project_list`, `project_detail`, `project_learn`, `project_question_data`, `project_check_answer` views
- [ ] Extend review views to group by subject OR project
- [ ] Extend dashboard with project progress
- [ ] Add project URL routes

## Step 5: Templates
- [ ] Create `templates/core/projects.html`
- [ ] Create `templates/core/project_detail.html`
- [ ] Create `templates/core/project_complete.html`
- [ ] Update `templates/core/home.html` (separate Projects section)
- [ ] Update `templates/core/learn.html` (contentType config)
- [ ] Update `templates/core/dashboard.html` (project progress)
- [ ] Update `templates/core/review_mistakes.html` (project groups)

## Step 6: Frontend JS
- [ ] Update `static/js/learn.js` to build URLs based on contentType
- [ ] Add completion-page link after finishing all project MCQs

## Step 7: Styles
- [ ] Add project card, detail, completion styles to `static/css/style.css`

## Step 8: Tests
- [ ] Create `core/tests_projects.py` (comprehensive project tests)
- [ ] Run full test suite (existing + new)
- [ ] Verify no regression

</content>

