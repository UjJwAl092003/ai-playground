"""
Tests for the Complete-Project JSON importer.

These tests cover:

1. Valid complete project JSON → creates Project + all questions.
2. Invalid / missing project fields (title, slug, slug format).
3. Invalid / missing question fields.
4. Duplicate project slug → conflict detected, no duplicate, explicit decision.
5. Duplicate question numbers within the file.
6. Existing questions → skipped, never overwritten.
7. Transaction rollback (all-or-nothing).
8. Markdown / code-block preservation.
9. Existing Subject importer regression (unchanged behavior).

Run with:
    venv\\Scripts\\python manage.py test core.tests_project_importer
"""

import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Question, Subject
from core.services import question_importer as importer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_valid_question(number=1, **overrides):
    """Return a valid question dict with sensible defaults."""
    data = {
        "question_number": number,
        "question_text": f"What is {number} + 0?",
        "option_a": "0",
        "option_b": str(number),
        "option_c": "None",
        "option_d": "Error",
        "correct_answer": "B",
        "explanation": "This is a test explanation.",
        "python_code": "print('hello')",
        "practical_example": "A practical example.",
    }
    data.update(overrides)
    return data


def make_valid_project_file(slug="titanic-survivor-prediction", title="Titanic Survivor Prediction", questions=None):
    """Return a JSON string representing a valid complete-project file."""
    questions = questions if questions is not None else [make_valid_question(1)]
    return json.dumps({
        "title": title,
        "slug": slug,
        "short_description": "A short description.",
        "description": "## Description\n\nA long Markdown description.",
        "overview": "## Overview\n\nStep-by-step overview.",
        "complete_code": "```python\nimport pandas as pd\ndf = pd.read_csv('train.csv')\n```",
        "output": "Accuracy: 0.82",
        "explanation": "## How it works\n\nWe train a model.",
        "learning_outcomes": "- Feature engineering\n- Model evaluation",
        "dataset_info": "Source: Kaggle Titanic dataset.",
        "questions": questions,
    })


def create_admin_user():
    """Create and return a staff superuser with the add_question permission."""
    user = User.objects.create_user(
        username="admin", password="secret123", is_staff=True
    )
    user.is_superuser = True
    user.save()
    return user


def make_uploaded_file(content, filename="project.json"):
    """Build an in-memory upload for the admin upload form."""
    return SimpleUploadedFile(filename, content.encode("utf-8"))


class BaseProjectImporterTest(TestCase):
    """Base test case with a fresh admin user."""

    def setUp(self):
        self.admin = create_admin_user()
        self.client.force_login(self.admin)


# ---------------------------------------------------------------------------
# 1. Valid complete project JSON
# ---------------------------------------------------------------------------

class ValidProjectImportTests(BaseProjectImporterTest):

    def test_valid_import_creates_project_and_questions(self):
        content = make_valid_project_file(
            questions=[make_valid_question(1), make_valid_question(2)]
        )
        preview = importer.validate_complete_project_import_data(content)
        self.assertFalse(preview.has_errors)
        self.assertFalse(preview.project_exists)
        self.assertEqual(len(preview.questions), 2)

        count = importer.import_complete_project(preview)
        self.assertEqual(count, 2)

        project = Project.objects.get(slug="titanic-survivor-prediction")
        self.assertEqual(project.title, "Titanic Survivor Prediction")
        self.assertEqual(project.short_description, "A short description.")
        self.assertEqual(Question.objects.filter(project=project).count(), 2)

    def test_valid_import_stores_all_project_fields(self):
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file()
        )
        self.assertFalse(preview.has_errors)
        importer.import_complete_project(preview)

        project = Project.objects.get(slug="titanic-survivor-prediction")
        self.assertEqual(project.description, "## Description\n\nA long Markdown description.")
        self.assertEqual(project.overview, "## Overview\n\nStep-by-step overview.")
        self.assertEqual(
            project.complete_code,
            "```python\nimport pandas as pd\ndf = pd.read_csv('train.csv')\n```",
        )
        self.assertEqual(project.output, "Accuracy: 0.82")
        self.assertEqual(project.explanation, "## How it works\n\nWe train a model.")
        self.assertEqual(project.learning_outcomes, "- Feature engineering\n- Model evaluation")
        self.assertEqual(project.dataset_info, "Source: Kaggle Titanic dataset.")

    def test_valid_import_stores_all_question_fields(self):
        content = make_valid_project_file(
            questions=[make_valid_question(
                1,
                question_text="What does pd.read_csv() do?",
                option_a="A", option_b="B", option_c="C", option_d="D",
                correct_answer="A",
                explanation="A detailed explanation.",
                python_code="import pandas as pd\ndf = pd.read_csv('x.csv')",
                practical_example="Real world usage.",
            )]
        )
        preview = importer.validate_complete_project_import_data(content)
        self.assertFalse(preview.has_errors)
        importer.import_complete_project(preview)

        project = Project.objects.get(slug="titanic-survivor-prediction")
        q = Question.objects.get(project=project, question_number=1)
        self.assertEqual(q.question_text, "What does pd.read_csv() do?")
        self.assertEqual(q.option_a, "A")
        self.assertEqual(q.option_b, "B")
        self.assertEqual(q.option_c, "C")
        self.assertEqual(q.option_d, "D")
        self.assertEqual(q.correct_answer, "A")
        self.assertEqual(q.explanation, "A detailed explanation.")
        self.assertEqual(
            q.python_code, "import pandas as pd\ndf = pd.read_csv('x.csv')"
        )
        self.assertEqual(q.practical_example, "Real world usage.")


# ---------------------------------------------------------------------------
# 2. Invalid / missing project fields
# ---------------------------------------------------------------------------

class InvalidProjectFieldTests(BaseProjectImporterTest):

    def test_missing_title(self):
        data = json.loads(make_valid_project_file())
        del data["title"]
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("title" in e for e in preview.errors))

    def test_missing_slug(self):
        data = json.loads(make_valid_project_file())
        del data["slug"]
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("slug" in e for e in preview.errors))

    def test_invalid_slug_format(self):
        data = json.loads(make_valid_project_file())
        data["slug"] = "Invalid Slug With Spaces!"
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("not a valid slug" in e for e in preview.errors))

    def test_non_string_description(self):
        data = json.loads(make_valid_project_file())
        data["description"] = 12345
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("description" in e for e in preview.errors))

    def test_invalid_json_root(self):
        preview = importer.validate_complete_project_import_data("[1, 2, 3]")
        self.assertTrue(preview.has_errors)

    def test_parse_error(self):
        preview = importer.validate_complete_project_import_data("not json")
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("Invalid JSON" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 3. Invalid / missing question fields
# ---------------------------------------------------------------------------

class InvalidQuestionFieldTests(BaseProjectImporterTest):

    def test_missing_question_explanation(self):
        question = make_valid_question(1)
        del question["explanation"]
        content = make_valid_project_file(questions=[question])
        preview = importer.validate_complete_project_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("explanation" in e for e in preview.errors))

    def test_missing_question_number(self):
        question = make_valid_question()
        del question["question_number"]
        content = make_valid_project_file(questions=[question])
        preview = importer.validate_complete_project_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("question_number" in e for e in preview.errors))

    def test_invalid_correct_answer(self):
        question = make_valid_question(1, correct_answer="E")
        content = make_valid_project_file(questions=[question])
        preview = importer.validate_complete_project_import_data(content)
        self.assertTrue(preview.has_errors)

    def test_empty_question_text(self):
        question = make_valid_question(1, question_text="   ")
        content = make_valid_project_file(questions=[question])
        preview = importer.validate_complete_project_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("must not be empty" in e for e in preview.errors))

    def test_missing_questions_list(self):
        data = json.loads(make_valid_project_file())
        del data["questions"]
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("questions" in e for e in preview.errors))

    def test_empty_questions_list(self):
        data = json.loads(make_valid_project_file())
        data["questions"] = []
        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("empty" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 4. Duplicate project slug
# ---------------------------------------------------------------------------

class DuplicateProjectSlugTests(BaseProjectImporterTest):

    def test_existing_slug_detected_as_conflict(self):
        # Pre-create a project with the same slug.
        Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file()
        )
        self.assertFalse(preview.has_errors)
        self.assertTrue(preview.project_exists)
        self.assertEqual(preview.project.title, "Existing Project")

    def test_no_duplicate_project_created(self):
        Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file()
        )
        importer.import_complete_project(preview)
        # Only one project with this slug exists, and it's the original.
        self.assertEqual(
            Project.objects.filter(slug="titanic-survivor-prediction").count(), 1
        )
        self.assertEqual(
            Project.objects.get(slug="titanic-survivor-prediction").title,
            "Existing Project",
        )

    def test_existing_project_fields_not_overwritten(self):
        existing = Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction",
            description="Original description",
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file()
        )
        importer.import_complete_project(preview)

        refreshed = Project.objects.get(id=existing.id)
        self.assertEqual(refreshed.title, "Existing Project")
        self.assertEqual(refreshed.description, "Original description")

    def test_existing_project_gets_new_questions(self):
        existing = Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file(
                questions=[make_valid_question(1), make_valid_question(2)]
            )
        )
        self.assertFalse(preview.has_errors)
        self.assertTrue(preview.project_exists)
        self.assertEqual(len(preview.questions), 2)

        importer.import_complete_project(preview)
        self.assertEqual(Question.objects.filter(project=existing).count(), 2)


# ---------------------------------------------------------------------------
# 5. Duplicate question numbers within the file
# ---------------------------------------------------------------------------

class DuplicateQuestionNumberTests(BaseProjectImporterTest):

    def test_duplicate_numbers_reported(self):
        content = make_valid_project_file(
            questions=[make_valid_question(1), make_valid_question(1)]
        )
        preview = importer.validate_complete_project_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertEqual(preview.duplicate_numbers, [1])
        self.assertTrue(any("appears more than once" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 6. Existing questions (never overwritten)
# ---------------------------------------------------------------------------

class ExistingQuestionTests(BaseProjectImporterTest):

    def test_existing_question_is_conflict_not_duplicate(self):
        project = Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        Question.objects.create(
            project=project, question_number=1,
            question_text="Original", option_a="a", option_b="b",
            option_c="c", option_d="d", correct_answer="A",
            explanation="Original explanation.",
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file(
                questions=[make_valid_question(1), make_valid_question(2)]
            )
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.questions), 1)   # only Q2
        self.assertEqual(len(preview.conflicts), 1)   # Q1 conflicts
        self.assertEqual(preview.conflicts[0].question_number, 1)

    def test_existing_question_not_overwritten(self):
        project = Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        original = Question.objects.create(
            project=project, question_number=1,
            question_text="Original", option_a="a", option_b="b",
            option_c="c", option_d="d", correct_answer="A",
            explanation="Original explanation.",
        )
        preview = importer.validate_complete_project_import_data(
            make_valid_project_file(questions=[make_valid_question(1)])
        )
        importer.import_complete_project(preview)

        refreshed = Question.objects.get(id=original.id)
        self.assertEqual(refreshed.question_text, "Original")
        self.assertEqual(Question.objects.filter(project=project).count(), 1)


# ---------------------------------------------------------------------------
# 7. Transaction rollback (all-or-nothing)
# ---------------------------------------------------------------------------

class TransactionRollbackTests(BaseProjectImporterTest):

    def test_partial_failure_rolls_back_project_and_questions(self):
        # Build a preview whose questions include a duplicate number that
        # will violate the (project, question_number) unique constraint at
        # the database level. Because import_complete_project runs in a
        # transaction, the Project must NOT be created either.
        project_data = {
            "title": "Titanic Survivor Prediction",
            "slug": "titanic-survivor-prediction",
            "short_description": "A short description.",
            "description": "",
            "overview": "",
            "complete_code": "",
            "output": "",
            "explanation": "",
            "learning_outcomes": "",
            "dataset_info": "",
        }
        questions = [
            importer.QuestionData(
                question_number=n, question_text=f"Q{n}",
                option_a="a", option_b="b", option_c="c", option_d="d",
                correct_answer="A", explanation=f"Explanation {n}",
            )
            for n in range(1, 37)
        ]
        # 37th item re-uses question_number 1 → IntegrityError.
        questions.append(
            importer.QuestionData(
                question_number=1, question_text="Q37",
                option_a="a", option_b="b", option_c="c", option_d="d",
                correct_answer="A", explanation="Explanation 37",
            )
        )

        preview = importer.CompleteProjectPreview(
            project_data=project_data,
            project_exists=False,
            questions=questions,
        )

        with self.assertRaises(IntegrityError):
            importer.import_complete_project(preview)

        # Nothing was created — the transaction rolled back.
        self.assertFalse(
            Project.objects.filter(slug="titanic-survivor-prediction").exists()
        )
        self.assertEqual(Question.objects.all().count(), 0)


# ---------------------------------------------------------------------------
# 8. Markdown / code-block preservation
# ---------------------------------------------------------------------------

class MarkdownPreservationTests(BaseProjectImporterTest):

    def test_markdown_and_code_blocks_preserved(self):
        description = (
            "# Titanic Project\n\n"
            "This is a **Markdown** description.\n\n"
            "## Steps\n\n"
            "1. Load data\n"
            "2. Clean data\n"
        )
        complete_code = (
            "```python\n"
            "import pandas as pd\n"
            "import numpy as np\n"
            "\n"
            "df = pd.read_csv('train.csv')\n"
            "print(df.head())\n"
            "```\n"
        )
        output = (
            "```\n"
            "   PassengerId  Survived  Pclass\n"
            "0            1         0       3\n"
            "1            2         1       1\n"
            "```\n"
        )
        question_python = (
            "```python\n"
            "def load_data():\n"
            "    return pd.read_csv('train.csv')\n"
            "```\n"
        )

        content = make_valid_project_file(
            questions=[make_valid_question(
                1,
                python_code=question_python,
                practical_example="## Example\n\nLoad the data and inspect it.",
            )]
        )
        data = json.loads(content)
        data["description"] = description
        data["complete_code"] = complete_code
        data["output"] = output

        preview = importer.validate_complete_project_import_data(json.dumps(data))
        self.assertFalse(preview.has_errors)
        importer.import_complete_project(preview)

        project = Project.objects.get(slug="titanic-survivor-prediction")
        # The importer strips outer whitespace but preserves internal
        # Markdown/newlines and fenced code blocks exactly.
        self.assertEqual(project.description, description.strip())
        self.assertEqual(project.complete_code, complete_code.strip())
        self.assertEqual(project.output, output.strip())

        q = Question.objects.get(project=project, question_number=1)
        self.assertEqual(q.python_code, question_python.strip())
        self.assertEqual(
            q.practical_example, "## Example\n\nLoad the data and inspect it.".strip()
        )


# ---------------------------------------------------------------------------
# 9. Existing Subject importer regression (unchanged behavior)
# ---------------------------------------------------------------------------

class SubjectImporterRegressionTests(BaseProjectImporterTest):

    def test_subject_importer_still_works(self):
        # The seed migration creates initial subjects; use get_or_create.
        subject, _ = Subject.objects.get_or_create(name="Pandas", slug="pandas")
        content = json.dumps({
            "subject": "Pandas",
            "questions": [make_valid_question(1)],
        })
        preview = importer.validate_import_data(content)
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.subject, subject)

        count = importer.import_questions(subject, preview.questions)
        self.assertEqual(count, 1)
        self.assertEqual(Question.objects.filter(subject=subject).count(), 1)

    def test_subject_importer_rejects_missing_project(self):
        # The subject importer must still NOT accept a project-style root.
        subject, _ = Subject.objects.get_or_create(name="Pandas", slug="pandas")
        content = json.dumps({
            "project": "Titanic Survivor Prediction",
            "questions": [make_valid_question(1)],
        })
        preview = importer.validate_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("subject" in e.lower() for e in preview.errors))


# ---------------------------------------------------------------------------
# 10. Admin workflow for the complete-project importer
# ---------------------------------------------------------------------------

class CompleteProjectAdminWorkflowTests(BaseProjectImporterTest):

    def test_full_upload_preview_confirm_result(self):
        content = make_valid_project_file(
            questions=[make_valid_question(1), make_valid_question(2)]
        )
        # Step 1: upload
        response = self.client.post(
            reverse("admin:core_project_import_json"),
            {"json_file": make_uploaded_file(content)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("preview", response.url)

        # Step 2: preview
        response = self.client.get(
            reverse("admin:core_project_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Titanic Survivor Prediction")
        self.assertContains(response, "Will be created")

        # Step 3: confirm
        response = self.client.post(
            reverse("admin:core_project_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("result", response.url)

        # Project + questions created.
        project = Project.objects.get(slug="titanic-survivor-prediction")
        self.assertEqual(Question.objects.filter(project=project).count(), 2)

        # Step 4: result page
        response = self.client.get(
            reverse("admin:core_project_import_json_result")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created")

    def test_existing_project_shows_conflict_in_preview(self):
        Project.objects.create(
            title="Existing Project", slug="titanic-survivor-prediction"
        )
        content = make_valid_project_file(
            questions=[make_valid_question(1)]
        )
        self.client.post(
            reverse("admin:core_project_import_json"),
            {"json_file": make_uploaded_file(content)},
        )
        response = self.client.get(
            reverse("admin:core_project_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already exists in database")

    def test_confirm_without_upload_redirects_to_upload(self):
        response = self.client.get(
            reverse("admin:core_project_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("import-json", response.url)

    def test_upload_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("admin:core_project_import_json"))
        self.assertEqual(response.status_code, 302)
