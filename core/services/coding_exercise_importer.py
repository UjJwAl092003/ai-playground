"""
Service for importing Coding Exercises from a JSON file.

This module is the exact parallel of the MCQ importer
(``core/services/question_importer.py``), but for Coding Exercises. It is
deliberately separated from ``core/admin.py`` so that:

- It is easy to unit-test (no HTTP involved).
- It can be reused later (e.g. a management command or a future API).

The uploaded JSON is the **single source of truth** and follows this shape::

    {
      "module": "Pandas",
      "topic": "Filtering, Sorting & GroupBy Aggregation",
      "lesson_slug": "pandas-filtering-sorting-groupby-aggregation",
      "coding_exercises": [
        {
          "exercise_number": 1,
          "title": "...",
          "difficulty": "...",
          "estimated_time": 5,
          "objective": "...",
          "ml_connection": "...",
          "dataset": {"name": "...", "description": "...", "preview": []},
          "problem_statement": "...",
          "starter_code": "...",
          "expected_solution": "...",
          "expected_output": "...",
          "explanation": "...",
          "common_mistakes": [],
          "hints": [],
          "concepts_covered": []
        }
      ]
    }

Behavior (mirrors the MCQ importer exactly):

- **Auto-numbering**: when ``auto_number`` is True, the ``exercise_number``
  values in the JSON are IGNORED and fresh sequential numbers are assigned
  starting from the highest existing exercise number within the lesson + 1.
- **Default**: when ``auto_number`` is False, the ``exercise_number`` values
  are preserved exactly (backward compatible).
- **Duplicate handling**: when auto-numbering is OFF, duplicate numbers in the
  file are validation errors. When ON, duplicates are ignored (they will all
  be reassigned).
- **Atomic import**: the whole import runs inside a single transaction; on any
  failure everything is rolled back. No partial imports.
- **Markdown preservation**: Markdown fields are preserved verbatim (only outer
  whitespace is stripped; internal newlines and fenced ```python blocks are
  kept).

Security note:
The ``starter_code`` / ``expected_solution`` fields in the JSON are treated as
**data only**. They are stored as plain text and **never executed**. Nothing in
this module ever calls ``eval`` / ``exec``.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.db import models, transaction

from core.models import CodingExercise, CodingLesson

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Root-level keys that must be present in the JSON file.
REQUIRED_ROOT_KEYS = ("module", "topic", "lesson_slug", "coding_exercises")

#: Every exercise object must contain all of these keys.
REQUIRED_EXERCISE_FIELDS = (
    "exercise_number",
    "title",
    "problem_statement",
    "explanation",
)

#: Fields that must be present AND non-empty.
NON_EMPTY_TEXT_FIELDS = (
    "title",
    "problem_statement",
    "explanation",
)

#: Text fields that may contain multiline Markdown and must be preserved
#: verbatim (only outer whitespace is stripped).
MARKDOWN_FIELDS = (
    "objective",
    "ml_connection",
    "dataset_description",
    "problem_statement",
    "starter_code",
    "expected_solution",
    "expected_output",
    "explanation",
)

#: Fields that may be empty, but if present must be strings.
OPTIONAL_STRING_FIELDS = (
    "difficulty",
    "dataset_name",
    "objective",
    "ml_connection",
    "dataset_description",
    "starter_code",
    "expected_solution",
    "expected_output",
)

#: List fields (stored as JSON); must be lists if present.
OPTIONAL_LIST_FIELDS = (
    "dataset_preview",
    "common_mistakes",
    "hints",
    "concepts_covered",
)

#: Maximum accepted upload size in bytes (2 MB).
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

#: A simple slug regex matching Django's SlugField format.
_SLUG_RE = r"^[-a-zA-Z0-9_]+$"


# ---------------------------------------------------------------------------
# Simple data containers
# ---------------------------------------------------------------------------

@dataclass
class CodingExerciseData:
    """A fully validated coding exercise ready to be stored in the database."""

    exercise_number: int
    title: str
    difficulty: str = ""
    estimated_time: int = 5
    objective: str = ""
    ml_connection: str = ""
    dataset_name: str = ""
    dataset_description: str = ""
    dataset_preview: List[Any] = field(default_factory=list)
    problem_statement: str = ""
    starter_code: str = ""
    expected_solution: str = ""
    expected_output: str = ""
    explanation: str = ""
    common_mistakes: List[Any] = field(default_factory=list)
    hints: List[Any] = field(default_factory=list)
    concepts_covered: List[Any] = field(default_factory=list)


@dataclass
class CodingLessonPreview:
    """The result of validating a Coding Lesson import file."""

    lesson_data: Dict[str, str] = field(default_factory=dict)
    lesson: Optional[CodingLesson] = None
    lesson_exists: bool = False
    exercises: List[CodingExerciseData] = field(default_factory=list)
    conflicts: List[CodingExerciseData] = field(default_factory=list)
    duplicate_numbers: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


# ---------------------------------------------------------------------------
# Serialization helpers (used to store a preview in the session)
# ---------------------------------------------------------------------------

def exercise_to_dict(exercise: CodingExerciseData) -> Dict[str, Any]:
    """Convert a validated exercise to a plain dict (session-safe)."""
    return {
        "exercise_number": exercise.exercise_number,
        "title": exercise.title,
        "difficulty": exercise.difficulty,
        "estimated_time": exercise.estimated_time,
        "objective": exercise.objective,
        "ml_connection": exercise.ml_connection,
        "dataset_name": exercise.dataset_name,
        "dataset_description": exercise.dataset_description,
        "dataset_preview": exercise.dataset_preview,
        "problem_statement": exercise.problem_statement,
        "starter_code": exercise.starter_code,
        "expected_solution": exercise.expected_solution,
        "expected_output": exercise.expected_output,
        "explanation": exercise.explanation,
        "common_mistakes": exercise.common_mistakes,
        "hints": exercise.hints,
        "concepts_covered": exercise.concepts_covered,
    }


def dict_to_exercise(data: Dict[str, Any]) -> CodingExerciseData:
    """Convert a plain dict back into a validated CodingExerciseData object."""
    return CodingExerciseData(**data)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_json(content: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse raw file content as JSON.

    Returns ``(data, error)``. If parsing succeeds ``error`` is ``None``.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, (
            "The JSON root must be an object with 'module', 'topic', "
            "'lesson_slug', and 'coding_exercises'."
        )
    return data, None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _clean_text(value: Any) -> str:
    """Return a stripped string, or '' for any non-string value."""
    if isinstance(value, str):
        return value.strip()
    return ""


def _clean_markdown(value: Any) -> str:
    """Return a markdown string with only outer whitespace stripped.

    Internal newlines and fenced code blocks are preserved verbatim.
    """
    if isinstance(value, str):
        return value.strip()
    return ""


def validate_lesson_fields(
    data: Dict[str, Any],
) -> Tuple[Dict[str, str], List[str]]:
    """Validate the lesson-level fields from the JSON root.

    Returns ``(lesson_data, errors)``.

    - ``module``, ``topic``, and ``lesson_slug`` must be non-empty strings.
    - ``lesson_slug`` must match Django's slug format.
    """
    errors: List[str] = []
    lesson_data: Dict[str, str] = {}

    # --- module (required) ------------------------------------------------
    module = data.get("module")
    if not isinstance(module, str) or not module.strip():
        errors.append("The root 'module' must be a non-empty string.")
    else:
        lesson_data["module"] = module.strip()

    # --- topic (required) -------------------------------------------------
    topic = data.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        errors.append("The root 'topic' must be a non-empty string.")
    else:
        lesson_data["topic"] = topic.strip()

    # --- lesson_slug (required, must match slug format) -------------------
    lesson_slug = data.get("lesson_slug")
    if not isinstance(lesson_slug, str) or not lesson_slug.strip():
        errors.append("The root 'lesson_slug' must be a non-empty string.")
    else:
        lesson_slug = lesson_slug.strip()
        import re
        if not re.match(_SLUG_RE, lesson_slug):
            errors.append(
                f"The root 'lesson_slug' '{lesson_slug}' is not a valid slug. "
                f"Use lowercase letters, numbers, hyphens, and underscores only."
            )
        else:
            lesson_data["lesson_slug"] = lesson_slug

    return lesson_data, errors


def validate_exercises(
    exercises: List[Any],
    auto_number: bool = False,
) -> Tuple[List[CodingExerciseData], List[int], List[str]]:
    """Validate every exercise object in the JSON list.

    Returns ``(valid_exercises, duplicate_numbers, errors)``.

    - ``valid_exercises``: fully valid, importable exercises.
    - ``duplicate_numbers``: exercise numbers that appear more than once.
    - ``errors``: a human-readable error for every invalid exercise.

    When ``auto_number`` is True, the ``exercise_number`` values in the JSON
    are IGNORED (fresh sequential numbers are assigned later). In that mode:
    - ``exercise_number`` is not required and is not validated.
    - Duplicate numbers in the file are NOT treated as errors.
    - A placeholder number (0) is used; ``assign_sequential_numbers``
      overwrites it with the real assigned number.
    """
    valid_exercises: List[CodingExerciseData] = []
    duplicate_numbers: List[int] = []
    errors: List[str] = []
    seen_numbers: Dict[int, int] = {}  # exercise_number -> position in file

    for index, raw in enumerate(exercises):
        position = index + 1  # 1-based position in the file

        # A malformed item must always be reported, never silently skipped.
        if not isinstance(raw, dict):
            errors.append(
                f"Exercise {position}: expected an object with exercise fields, "
                f"got {type(raw).__name__}."
            )
            continue

        # --- exercise_number ----------------------------------------------
        if auto_number:
            # Auto-numbering mode: numbers in the JSON are IGNORED. Fresh
            # sequential numbers are assigned later (max_existing + 1 ...).
            # Duplicate numbers in the file are therefore NOT an error here.
            ex_number = 0  # placeholder; overwritten by assign_sequential_numbers
        else:
            ex_number = raw.get("exercise_number")
            if ex_number is None:
                errors.append(
                    f"Exercise {position}: missing required field "
                    f"'exercise_number'."
                )
                continue
            if isinstance(ex_number, bool) or not isinstance(ex_number, int):
                errors.append(
                    f"Exercise {position}: 'exercise_number' must be a positive "
                    f"integer, got {ex_number!r}."
                )
                continue
            if ex_number < 1:
                errors.append(
                    f"Exercise {position}: 'exercise_number' must be at least "
                    f"1, got {ex_number}."
                )
                continue

            # Duplicate number within the same file.
            if ex_number in seen_numbers:
                duplicate_numbers.append(ex_number)
                errors.append(
                    f"Exercise {position}: exercise_number {ex_number} appears "
                    f"more than once in the JSON file (first seen at position "
                    f"{seen_numbers[ex_number]})."
                )
                continue
            seen_numbers[ex_number] = position

        # --- required fields present ---------------------------------------
        missing = [f for f in REQUIRED_EXERCISE_FIELDS if f not in raw]
        if missing:
            errors.append(
                f"Exercise {ex_number}: missing required field(s): "
                f"{', '.join(missing)}."
            )
            continue

        # --- required text fields non-empty --------------------------------
        cleaned: Dict[str, str] = {}
        empty_fields = []
        for field_name in NON_EMPTY_TEXT_FIELDS:
            value = _clean_text(raw.get(field_name))
            cleaned[field_name] = value
            if not value:
                empty_fields.append(field_name)
        if empty_fields:
            errors.append(
                f"Exercise {ex_number}: the following field(s) must not be "
                f"empty: {', '.join(empty_fields)}."
            )
            continue

        # --- optional string fields ----------------------------------------
        optional_ok = True
        for field_name in OPTIONAL_STRING_FIELDS:
            value = raw.get(field_name, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                errors.append(
                    f"Exercise {ex_number}: '{field_name}' must be a string "
                    f"(or omitted)."
                )
                optional_ok = False
                break
            # Preserve internal Markdown verbatim; only strip outer whitespace.
            cleaned[field_name] = _clean_markdown(value)
        if not optional_ok:
            continue

        # --- estimated_time (optional int) ---------------------------------
        estimated_time = raw.get("estimated_time", 5)
        if isinstance(estimated_time, bool) or not isinstance(estimated_time, int):
            errors.append(
                f"Exercise {ex_number}: 'estimated_time' must be a positive "
                f"integer (or omitted)."
            )
            continue
        if estimated_time < 1:
            estimated_time = 1

        # --- optional list fields (JSON) -----------------------------------
        lists_ok = True
        list_values: Dict[str, list] = {}
        for field_name in OPTIONAL_LIST_FIELDS:
            value = raw.get(field_name, [])
            if value is None:
                value = []
            if not isinstance(value, list):
                errors.append(
                    f"Exercise {ex_number}: '{field_name}' must be a list "
                    f"(or omitted)."
                )
                lists_ok = False
                break
            list_values[field_name] = value
        if not lists_ok:
            continue

        # --- dataset (optional object) -------------------------------------
        dataset_name = cleaned.get("dataset_name", "")
        dataset_description = cleaned.get("dataset_description", "")
        dataset_preview = list_values.get("dataset_preview", [])
        dataset = raw.get("dataset")
        if isinstance(dataset, dict):
            if isinstance(dataset.get("name"), str):
                dataset_name = dataset["name"].strip()
            if isinstance(dataset.get("description"), str):
                dataset_description = dataset["description"].strip()
            if isinstance(dataset.get("preview"), list):
                dataset_preview = dataset["preview"]

        valid_exercises.append(
            CodingExerciseData(
                exercise_number=ex_number,
                title=cleaned["title"],
                difficulty=cleaned.get("difficulty", ""),
                estimated_time=estimated_time,
                objective=cleaned.get("objective", ""),
                ml_connection=cleaned.get("ml_connection", ""),
                dataset_name=dataset_name,
                dataset_description=dataset_description,
                dataset_preview=dataset_preview,
                problem_statement=cleaned["problem_statement"],
                starter_code=cleaned.get("starter_code", ""),
                expected_solution=cleaned.get("expected_solution", ""),
                expected_output=cleaned.get("expected_output", ""),
                explanation=cleaned["explanation"],
                common_mistakes=list_values.get("common_mistakes", []),
                hints=list_values.get("hints", []),
                concepts_covered=list_values.get("concepts_covered", []),
            )
        )

    return valid_exercises, duplicate_numbers, errors


def find_lesson_by_slug(slug: str) -> Optional[CodingLesson]:
    """Look up an existing lesson by slug (case-insensitive)."""
    return CodingLesson.objects.filter(lesson_slug__iexact=slug.strip()).first()


def detect_conflicts(
    lesson: CodingLesson, exercises: List[CodingExerciseData]
) -> Tuple[List[CodingExerciseData], List[CodingExerciseData]]:
    """Split exercises into importable ones and ones that already exist.

    Existing exercises are **never** overwritten; they are returned as
    ``conflicts`` so the caller can skip them.
    """
    existing_numbers = set(
        CodingExercise.objects.filter(lesson=lesson).values_list(
            "exercise_number", flat=True
        )
    )
    importable: List[CodingExerciseData] = []
    conflicts: List[CodingExerciseData] = []
    for exercise in exercises:
        if exercise.exercise_number in existing_numbers:
            conflicts.append(exercise)
        else:
            importable.append(exercise)
    return importable, conflicts


def get_max_exercise_number(lesson: CodingLesson) -> int:
    """Return the highest existing exercise_number for a lesson.

    Returns 0 when there are no exercises yet.
    """
    return (
        CodingExercise.objects.filter(lesson=lesson).aggregate(
            max_number=models.Max("exercise_number")
        )["max_number"]
        or 0
    )


def assign_sequential_numbers(
    exercises: List[CodingExerciseData], start: int
) -> List[CodingExerciseData]:
    """Return a new list of exercises numbered ``start, start+1, ...``.

    The order of the input list is preserved. The ``exercise_number`` value
    on each returned ``CodingExerciseData`` is overwritten with the assigned
    sequential number.
    """
    result: List[CodingExerciseData] = []
    for offset, exercise in enumerate(exercises):
        result.append(
            CodingExerciseData(
                exercise_number=start + offset,
                title=exercise.title,
                difficulty=exercise.difficulty,
                estimated_time=exercise.estimated_time,
                objective=exercise.objective,
                ml_connection=exercise.ml_connection,
                dataset_name=exercise.dataset_name,
                dataset_description=exercise.dataset_description,
                dataset_preview=exercise.dataset_preview,
                problem_statement=exercise.problem_statement,
                starter_code=exercise.starter_code,
                expected_solution=exercise.expected_solution,
                expected_output=exercise.expected_output,
                explanation=exercise.explanation,
                common_mistakes=exercise.common_mistakes,
                hints=exercise.hints,
                concepts_covered=exercise.concepts_covered,
            )
        )
    return result


def apply_auto_numbering(
    exercises: List[CodingExerciseData], lesson: CodingLesson
) -> Tuple[List[CodingExerciseData], int, int]:
    """Assign sequential numbers to a batch of exercises.

    Computes ``start = get_max_exercise_number(lesson) + 1`` and renumbers
    the batch from ``start``.

    Returns ``(renumbered_exercises, start, end)``. Returns ``(exercises,
    0, 0)`` unchanged if the list is empty.
    """
    if not exercises:
        return exercises, 0, 0
    start = get_max_exercise_number(lesson) + 1
    renumbered = assign_sequential_numbers(exercises, start)
    end = start + len(renumbered) - 1
    return renumbered, start, end


def validate_coding_lesson_import_data(
    content: str, auto_number: bool = False
) -> CodingLessonPreview:
    """Run the complete validation pipeline on raw JSON file content.

    When ``auto_number`` is True, exercise numbers in the JSON are ignored
    and duplicate numbers are not treated as errors (fresh sequential
    numbers are assigned later).

    The JSON root is::

        {
          "module": "...",
          "topic": "...",
          "lesson_slug": "...",
          "coding_exercises": [ { ... } ]
        }

    Everything is validated BEFORE anything is written to the database.
    """
    preview = CodingLessonPreview()

    data, error = parse_json(content)
    if error:
        preview.errors.append(error)
        return preview

    if not isinstance(data, dict):
        preview.errors.append(
            "The JSON root must be an object with 'module', 'topic', "
            "'lesson_slug', and 'coding_exercises'."
        )
        return preview

    # --- Validate lesson-level fields -------------------------------------
    lesson_data, lesson_errors = validate_lesson_fields(data)
    preview.lesson_data = lesson_data
    preview.errors.extend(lesson_errors)
    # If any of module/topic/lesson_slug failed, we cannot proceed.
    if "module" not in lesson_data or "topic" not in lesson_data or "lesson_slug" not in lesson_data:
        return preview

    # --- Validate the exercises list --------------------------------------
    exercises_list = data.get("coding_exercises")
    if exercises_list is None:
        preview.errors.append("The root 'coding_exercises' key is missing.")
        return preview
    if not isinstance(exercises_list, list):
        preview.errors.append("The root 'coding_exercises' must be a list.")
        return preview
    if len(exercises_list) == 0:
        preview.errors.append(
            "The 'coding_exercises' list is empty; nothing to import."
        )
        return preview

    valid, duplicates, exercise_errors = validate_exercises(
        exercises_list, auto_number=auto_number
    )
    preview.duplicate_numbers = duplicates
    preview.errors.extend(exercise_errors)
    if exercise_errors:
        return preview

    # --- Detect an existing lesson by slug --------------------------------
    existing = find_lesson_by_slug(lesson_data["lesson_slug"])
    if existing is not None:
        preview.lesson = existing
        preview.lesson_exists = True
        # Only add NEW exercises; existing exercises are never overwritten.
        preview.exercises, preview.conflicts = detect_conflicts(existing, valid)
    else:
        preview.exercises = valid

    return preview


def import_coding_lesson(preview: CodingLessonPreview) -> int:
    """Create (or attach to) a CodingLesson and its exercises atomically.

    Behavior:
    - If the lesson does NOT exist, it is created from ``preview.lesson_data``.
    - If the lesson DOES exist, it is NOT modified (no overwrite). Only new
      exercises are added.
    - Existing exercises are never overwritten.
    - Everything happens inside a single transaction; on any failure the whole
      import is rolled back.

    Returns the number of exercises created.
    """
    with transaction.atomic():
        if preview.lesson_exists and preview.lesson is not None:
            lesson = preview.lesson
        else:
            lesson = CodingLesson.objects.create(
                module=preview.lesson_data["module"],
                topic=preview.lesson_data["topic"],
                lesson_slug=preview.lesson_data["lesson_slug"],
            )

        for exercise in preview.exercises:
            CodingExercise.objects.create(
                lesson=lesson,
                exercise_number=exercise.exercise_number,
                title=exercise.title,
                difficulty=exercise.difficulty,
                estimated_time=exercise.estimated_time,
                objective=exercise.objective,
                ml_connection=exercise.ml_connection,
                dataset_name=exercise.dataset_name,
                dataset_description=exercise.dataset_description,
                dataset_preview=exercise.dataset_preview,
                problem_statement=exercise.problem_statement,
                starter_code=exercise.starter_code,
                expected_solution=exercise.expected_solution,
                expected_output=exercise.expected_output,
                explanation=exercise.explanation,
                common_mistakes=exercise.common_mistakes,
                hints=exercise.hints,
                concepts_covered=exercise.concepts_covered,
            )

    return len(preview.exercises)
