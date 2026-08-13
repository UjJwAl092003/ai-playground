"""
Tests for the Coding Exercise JSON importer.

These tests cover:

1. Valid coding lesson JSON → creates CodingLesson + all exercises.
2. Invalid / missing lesson fields (module, topic, lesson_slug, slug format).
3. Invalid / missing exercise fields.
4. Duplicate lesson slug → conflict detected, no duplicate.
5. Duplicate exercise numbers within the file.
6. Existing exercises → skipped, never overwritten.
7. Transaction rollback (all-or-nothing).
8. Markdown / code-block preservation.
9. Auto-numbering (fresh sequential numbers per lesson).
10. Admin workflow (upload → preview → confirm → result).

Run with:
    venv\\Scripts\\python manage.py test core.tests_coding_exercise_importer
"""

import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import CodingExercise, CodingLesson
from core.services import coding_exercise_importer as importer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_valid_exercise(number=1, **overrides):
    """Return a valid exercise dict with sensible defaults."""
    data = {
        "exercise_number": number,
        "title": f"Exercise {number}",
        "difficulty": "beginner",
        "estimated_time": 5,
        "objective": "Learn a concept.",
        "ml_connection": "Used in ML.",
        "dataset_name": "Sample Dataset",
        "dataset_description": "A sample dataset.",
        "dataset_preview": [{"col": 1}],
        "problem_statement": f"Solve exercise {number}.",
        "starter_code": "import pandas as pd",
        "expected_solution": "df = pd.read_csv('x.csv')",
        "expected_output": "Rows: 100",
        "explanation": "This is how to solve it.",
        "common_mistakes": ["Forgetting to import"],
        "hints": ["Start with read_csv"],
        "concepts_covered": ["DataFrames"],
    }
    data.update(overrides)
    return data


def make_valid_lesson_file(slug="pandas-filtering-sorting-groupby-aggregation",
                           module="Pandas", topic="Filtering, Sorting & GroupBy",
                           exercises=None):
    """Return a JSON string representing a valid coding lesson file."""
    exercises = exercises if exercises is not None else [make_valid_exercise(1)]
    return json.dumps({
        "module": module,
        "topic": topic,
        "lesson_slug": slug,
        "coding_exercises": exercises,
    })


def create_admin_user():
    """Create and return a staff superuser with the add_question permission."""
    user = User.objects.create_user(
        username="admin", password="secret123", is_staff=True
    )
    user.is_superuser = True
    user.save()
    return user


def make_uploaded_file(content, filename="coding_lesson.json"):
    """Build an in-memory upload for the admin upload form."""
    return SimpleUploadedFile(filename, content.encode("utf-8"))


class BaseCodingLessonTest(TestCase):
    """Base test case with a fresh admin user."""

    def setUp(self):
        self.admin = create_admin_user()
        self.client.force_login(self.admin)


# ---------------------------------------------------------------------------
# 1. Valid coding lesson JSON
# ---------------------------------------------------------------------------

class ValidCodingLessonImportTests(BaseCodingLessonTest):

    def test_valid_import_creates_lesson_and_exercises(self):
        content = make_valid_lesson_file(
            exercises=[make_valid_exercise(1), make_valid_exercise(2)]
        )
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertFalse(preview.has_errors)
        self.assertFalse(preview.lesson_exists)
        self.assertEqual(len(preview.exercises), 2)

        count = importer.import_coding_lesson(preview)
        self.assertEqual(count, 2)

        lesson = CodingLesson.objects.get(lesson_slug="pandas-filtering-sorting-groupby-aggregation")
        self.assertEqual(lesson.module, "Pandas")
        self.assertEqual(lesson.topic, "Filtering, Sorting & GroupBy")
        self.assertEqual(CodingExercise.objects.filter(lesson=lesson).count(), 2)

    def test_valid_import_stores_all_lesson_fields(self):
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file()
        )
        self.assertFalse(preview.has_errors)
        importer.import_coding_lesson(preview)

        lesson = CodingLesson.objects.get(lesson_slug="pandas-filtering-sorting-groupby-aggregation")
        self.assertEqual(lesson.module, "Pandas")
        self.assertEqual(lesson.topic, "Filtering, Sorting & GroupBy")

    def test_valid_import_stores_all_exercise_fields(self):
        content = make_valid_lesson_file(
            exercises=[make_valid_exercise(
                1,
                title="Filtering rows",
                difficulty="intermediate",
                estimated_time=10,
                objective="Learn .loc",
                ml_connection="Feature selection",
                dataset_name="Titanic",
                dataset_description="Passenger data",
                dataset_preview=[{"a": 1}, {"b": 2}],
                problem_statement="Filter survivors.",
                starter_code="import pandas as pd",
                expected_solution="df[df['survived'] == 1]",
                expected_output="100 rows",
                explanation="Detailed explanation.",
                common_mistakes=["Using .iloc"],
                hints=["Use boolean mask"],
                concepts_covered=["Boolean indexing"],
            )]
        )
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertFalse(preview.has_errors)
        importer.import_coding_lesson(preview)

        lesson = CodingLesson.objects.get(lesson_slug="pandas-filtering-sorting-groupby-aggregation")
        e = CodingExercise.objects.get(lesson=lesson, exercise_number=1)
        self.assertEqual(e.title, "Filtering rows")
        self.assertEqual(e.difficulty, "intermediate")
        self.assertEqual(e.estimated_time, 10)
        self.assertEqual(e.objective, "Learn .loc")
        self.assertEqual(e.ml_connection, "Feature selection")
        self.assertEqual(e.dataset_name, "Titanic")
        self.assertEqual(e.dataset_description, "Passenger data")
        self.assertEqual(e.dataset_preview, [{"a": 1}, {"b": 2}])
        self.assertEqual(e.problem_statement, "Filter survivors.")
        self.assertEqual(e.starter_code, "import pandas as pd")
        self.assertEqual(e.expected_solution, "df[df['survived'] == 1]")
        self.assertEqual(e.expected_output, "100 rows")
        self.assertEqual(e.explanation, "Detailed explanation.")
        self.assertEqual(e.common_mistakes, ["Using .iloc"])
        self.assertEqual(e.hints, ["Use boolean mask"])
        self.assertEqual(e.concepts_covered, ["Boolean indexing"])


# ---------------------------------------------------------------------------
# 2. Invalid / missing lesson fields
# ---------------------------------------------------------------------------

class InvalidLessonFieldTests(BaseCodingLessonTest):

    def test_missing_module(self):
        data = json.loads(make_valid_lesson_file())
        del data["module"]
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("module" in e for e in preview.errors))

    def test_missing_topic(self):
        data = json.loads(make_valid_lesson_file())
        del data["topic"]
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("topic" in e for e in preview.errors))

    def test_missing_lesson_slug(self):
        data = json.loads(make_valid_lesson_file())
        del data["lesson_slug"]
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("lesson_slug" in e for e in preview.errors))

    def test_invalid_lesson_slug_format(self):
        data = json.loads(make_valid_lesson_file())
        data["lesson_slug"] = "Invalid Slug With Spaces!"
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("not a valid slug" in e for e in preview.errors))

    def test_invalid_json_root(self):
        preview = importer.validate_coding_lesson_import_data("[1, 2, 3]")
        self.assertTrue(preview.has_errors)

    def test_parse_error(self):
        preview = importer.validate_coding_lesson_import_data("not json")
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("Invalid JSON" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 3. Invalid / missing exercise fields
# ---------------------------------------------------------------------------

class InvalidExerciseFieldTests(BaseCodingLessonTest):

    def test_missing_explanation(self):
        exercise = make_valid_exercise(1)
        del exercise["explanation"]
        content = make_valid_lesson_file(exercises=[exercise])
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("explanation" in e for e in preview.errors))

    def test_missing_exercise_number(self):
        exercise = make_valid_exercise()
        del exercise["exercise_number"]
        content = make_valid_lesson_file(exercises=[exercise])
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("exercise_number" in e for e in preview.errors))

    def test_missing_title(self):
        exercise = make_valid_exercise(1)
        del exercise["title"]
        content = make_valid_lesson_file(exercises=[exercise])
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("title" in e for e in preview.errors))

    def test_empty_problem_statement(self):
        exercise = make_valid_exercise(1, problem_statement="   ")
        content = make_valid_lesson_file(exercises=[exercise])
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("must not be empty" in e for e in preview.errors))

    def test_missing_coding_exercises_list(self):
        data = json.loads(make_valid_lesson_file())
        del data["coding_exercises"]
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("coding_exercises" in e for e in preview.errors))

    def test_empty_coding_exercises_list(self):
        data = json.loads(make_valid_lesson_file())
        data["coding_exercises"] = []
        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertTrue(preview.has_errors)
        self.assertTrue(any("empty" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 4. Duplicate lesson slug
# ---------------------------------------------------------------------------

class DuplicateLessonSlugTests(BaseCodingLessonTest):

    def test_existing_slug_detected_as_conflict(self):
        CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file()
        )
        self.assertFalse(preview.has_errors)
        self.assertTrue(preview.lesson_exists)
        self.assertEqual(preview.lesson.topic, "Existing Topic")

    def test_no_duplicate_lesson_created(self):
        CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file()
        )
        importer.import_coding_lesson(preview)
        self.assertEqual(
            CodingLesson.objects.filter(
                lesson_slug="pandas-filtering-sorting-groupby-aggregation"
            ).count(),
            1,
        )
        self.assertEqual(
            CodingLesson.objects.get(
                lesson_slug="pandas-filtering-sorting-groupby-aggregation"
            ).topic,
            "Existing Topic",
        )

    def test_existing_lesson_fields_not_overwritten(self):
        existing = CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file()
        )
        importer.import_coding_lesson(preview)

        refreshed = CodingLesson.objects.get(id=existing.id)
        self.assertEqual(refreshed.topic, "Existing Topic")
        self.assertEqual(refreshed.module, "Pandas")

    def test_existing_lesson_gets_new_exercises(self):
        existing = CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file(
                exercises=[make_valid_exercise(1), make_valid_exercise(2)]
            )
        )
        self.assertFalse(preview.has_errors)
        self.assertTrue(preview.lesson_exists)
        self.assertEqual(len(preview.exercises), 2)

        importer.import_coding_lesson(preview)
        self.assertEqual(CodingExercise.objects.filter(lesson=existing).count(), 2)


# ---------------------------------------------------------------------------
# 5. Duplicate exercise numbers within the file
# ---------------------------------------------------------------------------

class DuplicateExerciseNumberTests(BaseCodingLessonTest):

    def test_duplicate_numbers_reported(self):
        content = make_valid_lesson_file(
            exercises=[make_valid_exercise(1), make_valid_exercise(1)]
        )
        preview = importer.validate_coding_lesson_import_data(content)
        self.assertTrue(preview.has_errors)
        self.assertEqual(preview.duplicate_numbers, [1])
        self.assertTrue(any("appears more than once" in e for e in preview.errors))


# ---------------------------------------------------------------------------
# 6. Existing exercises (never overwritten)
# ---------------------------------------------------------------------------

class ExistingExerciseTests(BaseCodingLessonTest):

    def test_existing_exercise_is_conflict_not_duplicate(self):
        lesson = CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        CodingExercise.objects.create(
            lesson=lesson, exercise_number=1,
            title="Original", problem_statement="Original problem",
            explanation="Original explanation.",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file(
                exercises=[make_valid_exercise(1), make_valid_exercise(2)]
            )
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.exercises), 1)   # only Ex2
        self.assertEqual(len(preview.conflicts), 1)   # Ex1 conflicts
        self.assertEqual(preview.conflicts[0].exercise_number, 1)

    def test_existing_exercise_not_overwritten(self):
        lesson = CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        original = CodingExercise.objects.create(
            lesson=lesson, exercise_number=1,
            title="Original", problem_statement="Original problem",
            explanation="Original explanation.",
        )
        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file(exercises=[make_valid_exercise(1)])
        )
        importer.import_coding_lesson(preview)

        refreshed = CodingExercise.objects.get(id=original.id)
        self.assertEqual(refreshed.title, "Original")
        self.assertEqual(CodingExercise.objects.filter(lesson=lesson).count(), 1)


# ---------------------------------------------------------------------------
# 7. Transaction rollback (all-or-nothing)
# ---------------------------------------------------------------------------

class TransactionRollbackTests(BaseCodingLessonTest):

    def test_partial_failure_rolls_back_lesson_and_exercises(self):
        # Build a preview whose exercises include a duplicate number that
        # will violate the (lesson, exercise_number) unique constraint at
        # the database level. Because import_coding_lesson runs in a
        # transaction, the Lesson must NOT be created either.
        lesson_data = {
            "module": "Pandas",
            "topic": "Filtering, Sorting & GroupBy",
            "lesson_slug": "pandas-filtering-sorting-groupby-aggregation",
        }
        exercises = [
            importer.CodingExerciseData(
                exercise_number=n, title=f"Exercise {n}",
                problem_statement=f"Solve {n}",
                explanation=f"Explanation {n}",
            )
            for n in range(1, 37)
        ]
        # 37th item re-uses exercise_number 1 → IntegrityError.
        exercises.append(
            importer.CodingExerciseData(
                exercise_number=1, title="Exercise 37",
                problem_statement="Solve 37",
                explanation="Explanation 37",
            )
        )

        preview = importer.CodingLessonPreview(
            lesson_data=lesson_data,
            lesson_exists=False,
            exercises=exercises,
        )

        with self.assertRaises(IntegrityError):
            importer.import_coding_lesson(preview)

        # Nothing was created — the transaction rolled back.
        self.assertFalse(
            CodingLesson.objects.filter(
                lesson_slug="pandas-filtering-sorting-groupby-aggregation"
            ).exists()
        )
        self.assertEqual(CodingExercise.objects.all().count(), 0)


# ---------------------------------------------------------------------------
# 8. Markdown / code-block preservation
# ---------------------------------------------------------------------------

class MarkdownPreservationTests(BaseCodingLessonTest):

    def test_markdown_and_code_blocks_preserved(self):
        problem = (
            "# Filtering\n\n"
            "Write a function to **filter** survivors.\n\n"
            "```python\n"
            "def filter_survivors(df):\n"
            "    return df[df['survived'] == 1]\n"
            "```\n"
        )
        starter = (
            "```python\n"
            "import pandas as pd\n"
            "df = pd.read_csv('train.csv')\n"
            "```\n"
        )
        expected_solution = (
            "```python\n"
            "def filter_survivors(df):\n"
            "    return df[df['survived'] == 1]\n"
            "```\n"
        )

        content = make_valid_lesson_file(
            exercises=[make_valid_exercise(1, problem_statement=problem)]
        )
        data = json.loads(content)
        exercise = data["coding_exercises"][0]
        exercise["starter_code"] = starter
        exercise["expected_solution"] = expected_solution

        preview = importer.validate_coding_lesson_import_data(json.dumps(data))
        self.assertFalse(preview.has_errors)
        importer.import_coding_lesson(preview)

        lesson = CodingLesson.objects.get(lesson_slug="pandas-filtering-sorting-groupby-aggregation")
        e = CodingExercise.objects.get(lesson=lesson, exercise_number=1)
        self.assertEqual(e.problem_statement, problem.strip())
        self.assertEqual(e.starter_code, starter.strip())
        self.assertEqual(e.expected_solution, expected_solution.strip())


# ---------------------------------------------------------------------------
# 9. Auto-numbering (fresh sequential numbers per lesson)
# ---------------------------------------------------------------------------

class AutoNumberingTests(BaseCodingLessonTest):

    def test_auto_numbering_ignores_file_numbers(self):
        # Two exercises with confusing/duplicate numbers in the file.
        content = make_valid_lesson_file(
            exercises=[
                make_valid_exercise(99),
                make_valid_exercise(55),
            ]
        )
        preview = importer.validate_coding_lesson_import_data(
            content, auto_number=True
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.exercises), 2)

        # Placeholder numbers are 0 until assigned.
        self.assertEqual(preview.exercises[0].exercise_number, 0)

        # Create the lesson first (as import would), then assign sequential
        # numbers starting at 1 (no existing exercises).
        lesson = CodingLesson.objects.create(
            module="Pandas",
            topic="Filtering, Sorting & GroupBy",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        renumbered, start, end = importer.apply_auto_numbering(
            preview.exercises, lesson=lesson
        )
        self.assertEqual(start, 1)
        self.assertEqual(end, 2)
        self.assertEqual(renumbered[0].exercise_number, 1)
        self.assertEqual(renumbered[1].exercise_number, 2)

    def test_auto_numbering_continues_from_existing_max(self):
        lesson = CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        CodingExercise.objects.create(
            lesson=lesson, exercise_number=1,
            title="Existing", problem_statement="Existing",
            explanation="Existing explanation.",
        )

        preview = importer.validate_coding_lesson_import_data(
            make_valid_lesson_file(
                exercises=[
                    make_valid_exercise(50),
                    make_valid_exercise(60),
                ]
            ),
            auto_number=True,
        )
        self.assertFalse(preview.has_errors)
        self.assertTrue(preview.lesson_exists)

        renumbered, start, end = importer.apply_auto_numbering(
            preview.exercises, lesson=lesson
        )
        self.assertEqual(start, 2)
        self.assertEqual(end, 3)
        self.assertEqual(renumbered[0].exercise_number, 2)
        self.assertEqual(renumbered[1].exercise_number, 3)

    def test_auto_numbering_ignores_duplicates_in_file(self):
        # With auto-numbering ON, duplicate numbers are NOT errors.
        content = make_valid_lesson_file(
            exercises=[
                make_valid_exercise(1),
                make_valid_exercise(1),
            ]
        )
        preview = importer.validate_coding_lesson_import_data(
            content, auto_number=True
        )
        self.assertFalse(preview.has_errors)
        self.assertEqual(len(preview.exercises), 2)
        self.assertEqual(preview.duplicate_numbers, [])


# ---------------------------------------------------------------------------
# 10. Admin workflow
# ---------------------------------------------------------------------------

class CodingLessonAdminWorkflowTests(BaseCodingLessonTest):

    def test_full_upload_preview_confirm_result(self):
        content = make_valid_lesson_file(
            exercises=[make_valid_exercise(1), make_valid_exercise(2)]
        )
        # Step 1: upload
        response = self.client.post(
            reverse("admin:core_codinglesson_import_json"),
            {"json_file": make_uploaded_file(content)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("preview", response.url)

        # Step 2: preview
        response = self.client.get(
            reverse("admin:core_codinglesson_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtering, Sorting")
        self.assertContains(response, "Will be created")

        # Step 3: confirm
        response = self.client.post(
            reverse("admin:core_codinglesson_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("result", response.url)

        # Lesson + exercises created.
        lesson = CodingLesson.objects.get(lesson_slug="pandas-filtering-sorting-groupby-aggregation")
        self.assertEqual(CodingExercise.objects.filter(lesson=lesson).count(), 2)

        # Step 4: result page
        response = self.client.get(
            reverse("admin:core_codinglesson_import_json_result")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created")

    def test_existing_lesson_shows_conflict_in_preview(self):
        CodingLesson.objects.create(
            module="Pandas",
            topic="Existing Topic",
            lesson_slug="pandas-filtering-sorting-groupby-aggregation",
        )
        content = make_valid_lesson_file(exercises=[make_valid_exercise(1)])
        self.client.post(
            reverse("admin:core_codinglesson_import_json"),
            {"json_file": make_uploaded_file(content)},
        )
        response = self.client.get(
            reverse("admin:core_codinglesson_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already exists in database")

    def test_confirm_without_upload_redirects_to_upload(self):
        response = self.client.get(
            reverse("admin:core_codinglesson_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("import-json", response.url)

    def test_upload_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("admin:core_codinglesson_import_json"))
        self.assertEqual(response.status_code, 302)

    def test_auto_numbering_new_lesson_assigns_sequential(self):
        """New lesson + auto_number=True must assign 1,2,3... (no UNIQUE error)."""
        content = make_valid_lesson_file(
            slug="auto-new-lesson",
            exercises=[
                make_valid_exercise(99),
                make_valid_exercise(55),
                make_valid_exercise(7),
            ],
        )
        # Step 1: upload with auto_number checked.
        response = self.client.post(
            reverse("admin:core_codinglesson_import_json"),
            {"json_file": make_uploaded_file(content), "auto_number": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("preview", response.url)

        # Step 2: preview.
        response = self.client.get(
            reverse("admin:core_codinglesson_import_json_preview")
        )
        self.assertEqual(response.status_code, 200)

        # Step 3: confirm. This previously raised an IntegrityError because
        # the placeholder numbers (0,0,0) were never replaced for a new lesson.
        response = self.client.post(
            reverse("admin:core_codinglesson_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("result", response.url)

        # The lesson was created with sequential exercise numbers 1,2,3.
        lesson = CodingLesson.objects.get(lesson_slug="auto-new-lesson")
        numbers = sorted(
            CodingExercise.objects.filter(lesson=lesson).values_list(
                "exercise_number", flat=True
            )
        )
        self.assertEqual(numbers, [1, 2, 3])

    def test_auto_numbering_existing_lesson_continues_from_max(self):
        """Existing lesson + auto_number=True must continue from max+1."""
        lesson = CodingLesson.objects.create(
            module="Pandas",
            topic="Auto Existing",
            lesson_slug="auto-existing-lesson",
        )
        CodingExercise.objects.create(
            lesson=lesson, exercise_number=11,
            title="Existing", problem_statement="Existing",
            explanation="Existing explanation.",
        )
        content = make_valid_lesson_file(
            slug="auto-existing-lesson",
            exercises=[
                make_valid_exercise(1),
                make_valid_exercise(2),
                make_valid_exercise(3),
            ],
        )
        self.client.post(
            reverse("admin:core_codinglesson_import_json"),
            {"json_file": make_uploaded_file(content), "auto_number": "on"},
        )
        self.client.get(
            reverse("admin:core_codinglesson_import_json_preview")
        )
        response = self.client.post(
            reverse("admin:core_codinglesson_import_json_confirm")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("result", response.url)

        numbers = sorted(
            CodingExercise.objects.filter(lesson=lesson).values_list(
                "exercise_number", flat=True
            )
        )
        # Existing 11 + new 12,13,14.
        self.assertEqual(numbers, [11, 12, 13, 14])
