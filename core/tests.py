"""
Tests for the JSON question importer.

These tests cover:

1. Valid JSON import (multiple questions).
2. Invalid JSON (not parseable).
3. Missing subject.
4. Missing required field.
5. Invalid correct_answer.
6. Duplicate question_number inside the JSON file.
7. Question already existing in the database (conflict protection).
8. Empty question text.
9. Transaction rollback (all-or-nothing).
10. Successful import of multiple questions.
11. Admin access control (staff-only, permission required).
12. The full admin workflow (upload → preview → confirm → result).

Run with:
    venv\\Scripts\\python manage.py test core
"""

import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import Question, Subject
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


def make_valid_file(payload, subject="Pandas"):
    """Return a JSON string representing a valid import file."""
    return json.dumps({"subject": subject, "questions": payload})


def create_admin_user():
    """Create and return a staff superuser with the add_question permission."""
    user = User.objects.create_user(
        username="admin", password="secret123", is_staff=True
    )
    user.is_superuser = True
    user.save()
    return user


def make_uploaded_file(content, filename="questions.json"):
    """Build an in-memory upload for the admin upload form."""
    return SimpleUploadedFile(filename, content.encode("utf-8"))


class BaseImporterTest(TestCase):
    """Base test case that creates a Pandas subject and an admin user."""

    def setUp(self):
        # The seed migration already creates the initial 8 subjects (including
        # Pandas), so use get_or_create to avoid a unique-constraint clash.
        self.subject, _ = Subject.objects.get_or_create(
            name="Pandas", slug="pandas"
        )
        self.admin = create_admin_user()
        self.client.force_login(self.admin)


# ---------------------------------------------------------------------------
# 1. Valid JSON import (multiple questions)
# ---------------------------------------------------------------------------

class ValidImportTests(BaseImporterTest):

    def test_valid_import_creates_questions(self):
        preview = importer.validate_import_data(
            make_valid_file([make_valid_question(1), make_valid_question(2)])
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.questions), 2)
        self.assertEqual(preview.subject, self.subject)

        count = importer.import_questions(self.subject, preview.questions)
        self.assertEqual(count, 2)
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 2)

    def test_valid_import_stores_all_fields(self):
        question = make_valid_question(
            1,
            question_text="What does pd.read_csv() do?",
            option_a="Option A text",
            option_b="Option B text",
            option_c="Option C text",
            option_d="Option D text",
            correct_answer="A",
            explanation="A detailed explanation.",
            python_code="import pandas as pd\ndf = pd.read_csv('x.csv')",
            practical_example="Real world usage.",
        )
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertFalse(preview.has_errors)
        importer.import_questions(self.subject, preview.questions)

        q = Question.objects.get(subject=self.subject, question_number=1)
        self.assertEqual(q.question_text, "What does pd.read_csv() do?")
        self.assertEqual(q.option_a, "Option A text")
        self.assertEqual(q.option_b, "Option B text")
        self.assertEqual(q.option_c, "Option C text")
        self.assertEqual(q.option_d, "Option D text")
        self.assertEqual(q.correct_answer, "A")
        self.assertEqual(q.explanation, "A detailed explanation.")
        self.assertEqual(
            q.python_code, "import pandas as pd\ndf = pd.read_csv('x.csv')"
        )
        self.assertEqual(q.practical_example, "Real world usage.")


# ---------------------------------------------------------------------------
# 2. Invalid JSON
# ---------------------------------------------------------------------------

class InvalidJsonTests(BaseImporterTest):

    def test_invalid_json_reports_error(self):
        preview = importer.validate_import_data("this is not { json")
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("Invalid JSON" in e for e in preview.errors))

    def test_json_root_must_be_object(self):
        preview = importer.validate_import_data("[1, 2, 3]")
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("root" in e.lower() for e in preview.errors))


# ---------------------------------------------------------------------------
# 3. Missing subject
# ---------------------------------------------------------------------------

class MissingSubjectTests(BaseImporterTest):

    def test_missing_subject_key(self):
        preview = importer.validate_import_data(json.dumps({"questions": []}))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("subject" in e.lower() for e in preview.errors))

    def test_nonexistent_subject_reports_error(self):
        preview = importer.validate_import_data(
            json.dumps({"subject": "Quantum", "questions": [make_valid_question(1)]})
        )
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("not found" in e.lower() for e in preview.errors))

    def test_subject_not_created_when_missing(self):
        importer.validate_import_data(
            json.dumps({"subject": "Quantum", "questions": [make_valid_question(1)]})
        )
        self.assertFalse(Subject.objects.filter(name="Quantum").exists())


# ---------------------------------------------------------------------------
# 4. Missing required field
# ---------------------------------------------------------------------------

class MissingFieldTests(BaseImporterTest):

    def test_missing_explanation(self):
        question = make_valid_question(1)
        del question["explanation"]
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("explanation" in e for e in preview.errors))

    def test_missing_option_d(self):
        question = make_valid_question(1)
        del question["option_d"]
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("option_d" in e for e in preview.errors))

    def test_missing_question_number(self):
        question = make_valid_question()
        del question["question_number"]
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("question_number" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 5. Invalid correct_answer
# ---------------------------------------------------------------------------

class InvalidAnswerTests(BaseImporterTest):

    def test_invalid_correct_answer(self):
        question = make_valid_question(1, correct_answer="E")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(
            any("A, B, C" in e or "correct_answer" in e for e in preview.errors)
        )

    def test_lowercase_answer_is_uppercased(self):
        question = make_valid_question(1, correct_answer="b")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.questions[0].correct_answer, "B")


# ---------------------------------------------------------------------------
# 6. Duplicate question_number inside JSON
# ---------------------------------------------------------------------------

class DuplicateInFileTests(BaseImporterTest):

    def test_duplicate_numbers_reported(self):
        file_content = make_valid_file(
            [make_valid_question(1), make_valid_question(1)]
        )
        preview = importer.validate_import_data(file_content)
        self.assertTrue(preview.has_errors)
        self.assertEqual(preview.duplicate_numbers, [1])
        self.assertTrue(any("appears more than once" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 7. Question already existing in the database (conflict protection)
# ---------------------------------------------------------------------------

class ExistingQuestionTests(BaseImporterTest):

    def test_existing_question_is_conflict_not_duplicate(self):
        Question.objects.create(
            subject=self.subject,
            question_number=1,
            question_text="Existing question",
            option_a="a", option_b="b", option_c="c", option_d="d",
            correct_answer="A",
            explanation="Existing explanation.",
        )
        preview = importer.validate_import_data(
            make_valid_file([make_valid_question(1), make_valid_question(2)])
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.questions), 1)   # only Q2 is importable
        self.assertEqual(len(preview.conflicts), 1)   # Q1 already exists
        self.assertEqual(preview.conflicts[0].question_number, 1)

    def test_existing_question_not_overwritten(self):
        original = Question.objects.create(
            subject=self.subject,
            question_number=1,
            question_text="Original text",
            option_a="a", option_b="b", option_c="c", option_d="d",
            correct_answer="A",
            explanation="Original explanation.",
        )
        preview = importer.validate_import_data(
            make_valid_file([make_valid_question(1)])
        )
        importer.import_questions(self.subject, preview.questions)  # Q1 is skipped

        refreshed = Question.objects.get(id=original.id)
        self.assertEqual(refreshed.question_text, "Original text")
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 1)


# ---------------------------------------------------------------------------
# 8. Empty question text
# ---------------------------------------------------------------------------

class EmptyTextTests(BaseImporterTest):

    def test_empty_question_text_rejected(self):
        question = make_valid_question(1, question_text="   ")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("must not be empty" in e for e in preview.errors))

    def test_empty_option_rejected(self):
        question = make_valid_question(1, option_b="   ")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("option_b" in e for e in preview.errors))

    def test_optional_python_code_can_be_empty(self):
        question = make_valid_question(1, python_code="")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.questions[0].python_code, "")

    def test_optional_practical_example_can_be_empty(self):
        question = make_valid_question(1, practical_example="")
        preview = importer.validate_import_data(make_valid_file([question]))
        self.assertFalse(preview.has_errors)
        self.assertEqual(preview.questions[0].practical_example, "")


# ---------------------------------------------------------------------------
# 9. Transaction rollback (all-or-nothing)
# ---------------------------------------------------------------------------

class TransactionRollbackTests(BaseImporterTest):

    def test_partial_failure_rolls_back_everything(self):
        # Build 37 importable QuestionData objects. The first 36 use distinct
        # numbers (1-36). The 37th reuses number 1, which will violate the
        # (subject, question_number) unique constraint at the DATABASE level.
        # If the transaction does not roll back, the first 36 would remain.
        questions = [
            importer.QuestionData(
                question_number=n,
                question_text=f"Q{n}",
                option_a="a", option_b="b", option_c="c", option_d="d",
                correct_answer="A",
                explanation=f"Explanation {n}",
            )
            for n in range(1, 37)
        ]
        # The 37th item re-uses question_number 1 → IntegrityError on insert.
        questions.append(
            importer.QuestionData(
                question_number=1,  # duplicate!
                question_text="Q37",
                option_a="a", option_b="b", option_c="c", option_d="d",
                correct_answer="A",
                explanation="Explanation 37",
            )
        )

        count_before = Question.objects.filter(subject=self.subject).count()

        with self.assertRaises(IntegrityError):
            importer.import_questions(self.subject, questions)

        count_after = Question.objects.filter(subject=self.subject).count()
        self.assertEqual(
            count_after, count_before, "Transaction should roll back everything"
        )


# ---------------------------------------------------------------------------
# 10. Successful import of multiple questions
# ---------------------------------------------------------------------------

class MultiImportTests(BaseImporterTest):

    def test_import_50_questions(self):
        questions = [make_valid_question(i) for i in range(1, 51)]
        preview = importer.validate_import_data(make_valid_file(questions))
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.questions), 50)

        count = importer.import_questions(self.subject, preview.questions)
        self.assertEqual(count, 50)
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 50)


# ---------------------------------------------------------------------------
# 11. Admin access control
# ---------------------------------------------------------------------------

class AdminAccessTests(BaseImporterTest):

    def test_import_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("admin:core_question_import_json"))
        # Redirect to the admin login page.
        self.assertEqual(response.status_code, 302)

    def test_non_staff_user_is_rejected(self):
        user = User.objects.create_user(username="bob", password="secret123")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:core_question_import_json"))
        self.assertEqual(response.status_code, 302)  # redirected to admin login

    def test_staff_without_permission_is_rejected(self):
        user = User.objects.create_user(
            username="staff", password="secret123", is_staff=True
        )
        # Do NOT give the user the core.add_question permission.
        self.client.force_login(user)
        response = self.client.get(reverse("admin:core_question_import_json"))
        # admin_view wraps the view; a PermissionDenied is raised by our
        # permission check and surfaces as a 403.
        self.assertEqual(response.status_code, 403)

    def test_admin_user_can_access_import_page(self):
        response = self.client.get(reverse("admin:core_question_import_json"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# 12. Full admin workflow (upload → preview → confirm → result)
# ---------------------------------------------------------------------------

class FullAdminWorkflowTests(BaseImporterTest):

    def test_full_upload_preview_confirm_result(self):
        content = make_valid_file(
            [make_valid_question(1), make_valid_question(2)]
        )
        # Step 1: upload
        response = self.client.post(
            reverse("admin:core_question_import_json"),
            {"json_file": make_uploaded_file(content)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("preview", response.url)

        # Step 2: preview
        response = self.client.get(
            reverse("admin:core_question_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pandas")
        self.assertContains(response, "2")

        # Step 3: confirm
        response = self.client.post(
            reverse("admin:core_question_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("result", response.url)

        # Questions were created
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 2)

        # Step 4: result page
        response = self.client.get(
            reverse("admin:core_question_import_json_result")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successfully imported")

    def test_confirm_without_upload_redirects_to_upload(self):
        response = self.client.get(
            reverse("admin:core_question_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("import-json", response.url)

    def test_upload_rejects_non_json_file(self):
        content = "definitely not json"
        response = self.client.post(
            reverse("admin:core_question_import_json"),
            {"json_file": make_uploaded_file(content, "file.txt")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a JSON file")

    def test_upload_rejects_invalid_json_content(self):
        content = "this is not json at all"
        response = self.client.post(
            reverse("admin:core_question_import_json"),
            {"json_file": make_uploaded_file(content, "file.json")},
        )
        self.assertEqual(response.status_code, 302)
        # Redirects to preview which shows the errors.
        self.assertIn("preview", response.url)
        preview_response = self.client.get(
            reverse("admin:core_question_import_json_preview")
        )
        self.assertContains(preview_response, "Invalid JSON")

    def test_duplicate_protection_in_full_workflow(self):
        # First import Q1 and Q2.
        content = make_valid_file(
            [make_valid_question(1), make_valid_question(2)]
        )
        preview = importer.validate_import_data(content)
        importer.import_questions(self.subject, preview.questions)
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 2)

        # Now upload a file with Q2 and Q3.
        content2 = make_valid_file(
            [make_valid_question(2), make_valid_question(3)]
        )
        preview2 = importer.validate_import_data(content2)
        self.assertFalse(preview2.has_errors)
        self.assertEqual(len(preview2.questions), 1)   # only Q3
        self.assertEqual(len(preview2.conflicts), 1)   # Q2 conflicts

        importer.import_questions(self.subject, preview2.questions)
        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 3)

