"""
Service for importing MCQs from a JSON file.

All of the validation and import logic for the JSON importer lives in this
module, deliberately separated from ``core/admin.py`` so that:

- It is easy to unit-test (no HTTP involved).
- It can be reused later (e.g. a management command or a future API).

There are two parallel import families (fully backward-compatible):

1. Subject import — JSON root shape: ``{"subject": "...", "questions": [...]}``
2. Project import — JSON root shape: ``{"project": "...", "questions": [...]}``

Each question must belong to a Subject OR a Project (never both, never
neither), enforced by a database constraint. The functions below keep the two
families separate and never modify existing subject-based behavior.

Security note:
The ``python_code`` and ``practical_example`` fields in the JSON are treated
as **data only**. They are stored as plain text and **never executed**.
Nothing in this module ever calls ``eval`` / ``exec``.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.db import models, transaction

from core.models import Project, Question, Subject

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Root-level keys that must be present in the JSON file.
REQUIRED_ROOT_KEYS = ("subject", "questions")

#: Every question object must contain all of these keys.
REQUIRED_QUESTION_FIELDS = (
    "question_number",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_answer",
    "explanation",
)

#: The only allowed values for ``correct_answer``.
VALID_ANSWERS = ("A", "B", "C", "D")

#: Fields that must be present AND non-empty.
NON_EMPTY_TEXT_FIELDS = (
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "explanation",
)

#: Fields that may be empty, but if present must be strings.
OPTIONAL_STRING_FIELDS = ("python_code", "practical_example")

#: Maximum accepted upload size in bytes (2 MB).
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# Simple data containers
# ---------------------------------------------------------------------------

@dataclass
class QuestionData:
    """A fully validated question ready to be stored in the database."""

    question_number: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    explanation: str
    python_code: str = ""
    practical_example: str = ""


@dataclass
class ImportPreview:
    """The result of validating a JSON import file."""

    subject_name: str = ""
    subject: Optional[Subject] = None
    questions: List[QuestionData] = field(default_factory=list)   # importable
    conflicts: List[QuestionData] = field(default_factory=list)   # already exist
    duplicate_numbers: List[int] = field(default_factory=list)    # dup in file
    errors: List[str] = field(default_factory=list)               # blocking errors

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


# ---------------------------------------------------------------------------
# Serialization helpers (used to store a preview in the session)
# ---------------------------------------------------------------------------

def question_to_dict(question: QuestionData) -> Dict[str, Any]:
    """Convert a validated question to a plain dict (session-safe)."""
    return {
        "question_number": question.question_number,
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
        "python_code": question.python_code,
        "practical_example": question.practical_example,
    }


def dict_to_question(data: Dict[str, Any]) -> QuestionData:
    """Convert a plain dict back into a validated QuestionData object."""
    return QuestionData(**data)


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
        return None, "The JSON root must be an object with 'subject' and 'questions'."
    return data, None


def extract_root(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[list], List[str]]:
    """Extract and validate the root structure.

    Returns ``(subject_name, questions_list, errors)``.
    """
    errors: List[str] = []
    subject_name = data.get("subject")
    questions = data.get("questions")

    if not isinstance(subject_name, str) or not subject_name.strip():
        errors.append("The root 'subject' must be a non-empty string.")
        subject_name = None

    if questions is None:
        errors.append("The root 'questions' key is missing.")
        questions = None
    elif not isinstance(questions, list):
        errors.append("The root 'questions' must be a list.")
        questions = None
    elif len(questions) == 0:
        errors.append("The 'questions' list is empty; nothing to import.")

    return subject_name, questions, errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _clean_text(value: Any) -> str:
    """Return a stripped string, or '' for any non-string value."""
    if isinstance(value, str):
        return value.strip()
    return ""


def find_subject(name: str) -> Tuple[Optional[Subject], Optional[str]]:
    """Look up a subject by name (case-insensitive).

    Never creates a duplicate subject. Returns ``(subject, error)``.
    """
    subject = Subject.objects.filter(name__iexact=name.strip()).first()
    if subject is None:
        available = ", ".join(
            Subject.objects.values_list("name", flat=True).order_by("name")
        )
        error = (
            f"Subject '{name.strip()}' was not found in the database. "
            f"Available subjects: {available or '(none yet)'}."
        )
        return None, error
    return subject, None


def validate_questions(
    questions: List[Any],
    auto_number: bool = False,
) -> Tuple[List[QuestionData], List[int], List[str]]:
    """Validate every question object in the JSON list.

    Returns ``(valid_questions, duplicate_numbers, errors)``.

    - ``valid_questions``: fully valid, importable questions.
    - ``duplicate_numbers``: question numbers that appear more than once.
    - ``errors``: a human-readable error for every invalid question.

    When ``auto_number`` is True, the ``question_number`` values in the JSON
    are IGNORED (fresh sequential numbers are assigned later). In that mode:
    - ``question_number`` is not required and is not validated.
    - Duplicate numbers in the file are NOT treated as errors.
    - A placeholder number (0) is used; ``assign_sequential_numbers``
      overwrites it with the real assigned number.
    """
    valid_questions: List[QuestionData] = []
    duplicate_numbers: List[int] = []
    errors: List[str] = []
    seen_numbers: Dict[int, int] = {}  # question_number -> position in file

    for index, raw in enumerate(questions):
        position = index + 1  # 1-based position in the file

        # A malformed item must always be reported, never silently skipped.
        if not isinstance(raw, dict):
            errors.append(
                f"Question {position}: expected an object with question fields, "
                f"got {type(raw).__name__}."
            )
            continue

        # --- question_number -------------------------------------------------
        if auto_number:
            # Auto-numbering mode: numbers in the JSON are IGNORED. Fresh
            # sequential numbers are assigned later (max_existing + 1 ...).
            # Duplicate numbers in the file are therefore NOT an error here.
            q_number = 0  # placeholder; overwritten by assign_sequential_numbers
        else:
            q_number = raw.get("question_number")
            if q_number is None:
                errors.append(
                    f"Question {position}: missing required field 'question_number'."
                )
                continue
            if isinstance(q_number, bool) or not isinstance(q_number, int):
                errors.append(
                    f"Question {position}: 'question_number' must be a positive "
                    f"integer, got {q_number!r}."
                )
                continue
            if q_number < 1:
                errors.append(
                    f"Question {position}: 'question_number' must be at least 1, "
                    f"got {q_number}."
                )
                continue

            # Duplicate number within the same file.
            if q_number in seen_numbers:
                duplicate_numbers.append(q_number)
                errors.append(
                    f"Question {position}: question_number {q_number} appears more "
                    f"than once in the JSON file (first seen at position "
                    f"{seen_numbers[q_number]})."
                )
                continue
            seen_numbers[q_number] = position

        # --- required fields present -----------------------------------------
        missing = [f for f in REQUIRED_QUESTION_FIELDS if f not in raw]
        if missing:
            errors.append(
                f"Question {q_number}: missing required field(s): "
                f"{', '.join(missing)}."
            )
            continue

        # --- required text fields non-empty -----------------------------------
        cleaned: Dict[str, str] = {}
        empty_fields = []
        for field_name in NON_EMPTY_TEXT_FIELDS:
            value = _clean_text(raw.get(field_name))
            cleaned[field_name] = value
            if not value:
                empty_fields.append(field_name)
        if empty_fields:
            errors.append(
                f"Question {q_number}: the following field(s) must not be empty: "
                f"{', '.join(empty_fields)}."
            )
            continue

        # --- optional string fields -------------------------------------------
        optional_ok = True
        for field_name in OPTIONAL_STRING_FIELDS:
            value = raw.get(field_name, "")
            if not isinstance(value, str):
                errors.append(
                    f"Question {q_number}: '{field_name}' must be a string "
                    f"(or omitted)."
                )
                optional_ok = False
                break
            cleaned[field_name] = value.strip()
        if not optional_ok:
            continue

        # --- correct_answer ----------------------------------------------------
        answer = _clean_text(raw.get("correct_answer")).upper()
        if answer not in VALID_ANSWERS:
            errors.append(
                f"Question {q_number}: correct_answer must be one of A, B, C, "
                f"or D. Got {raw.get('correct_answer')!r}."
            )
            continue

        valid_questions.append(
            QuestionData(
                question_number=q_number,
                question_text=cleaned["question_text"],
                option_a=cleaned["option_a"],
                option_b=cleaned["option_b"],
                option_c=cleaned["option_c"],
                option_d=cleaned["option_d"],
                correct_answer=answer,
                explanation=cleaned["explanation"],
                python_code=cleaned.get("python_code", ""),
                practical_example=cleaned.get("practical_example", ""),
            )
        )

    return valid_questions, duplicate_numbers, errors


def detect_conflicts(
    subject: Subject, questions: List[QuestionData]
) -> Tuple[List[QuestionData], List[QuestionData]]:
    """Split questions into importable ones and ones that already exist.

    Existing questions are **never** overwritten; they are returned as
    ``conflicts`` so the caller can skip them.
    """
    existing_numbers = set(
        Question.objects.filter(subject=subject).values_list(
            "question_number", flat=True
        )
    )
    importable: List[QuestionData] = []
    conflicts: List[QuestionData] = []
    for question in questions:
        if question.question_number in existing_numbers:
            conflicts.append(question)
        else:
            importable.append(question)
    return importable, conflicts


def get_max_question_number(
    subject: Optional[Subject] = None,
    project: Optional[Project] = None,
) -> int:
    """Return the highest existing question_number for a Subject or Project.

    Returns 0 when there are no questions yet. Exactly one of ``subject``
    or ``project`` should be provided (matching the Question model's
    "belongs to exactly one parent" constraint).
    """
    qs = Question.objects.all()
    if subject is not None:
        qs = qs.filter(subject=subject)
    elif project is not None:
        qs = qs.filter(project=project)
    else:
        return 0
    return qs.aggregate(max_number=models.Max("question_number"))[
        "max_number"
    ] or 0


def assign_sequential_numbers(
    questions: List[QuestionData], start: int
) -> List[QuestionData]:
    """Return a new list of questions numbered ``start, start+1, ...``.

    The order of the input list is preserved. The ``question_number`` value
    on each returned ``QuestionData`` is overwritten with the assigned
    sequential number.
    """
    result: List[QuestionData] = []
    for offset, question in enumerate(questions):
        result.append(
            QuestionData(
                question_number=start + offset,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                python_code=question.python_code,
                practical_example=question.practical_example,
            )
        )
    return result


def apply_auto_numbering(
    questions: List[QuestionData],
    subject: Optional[Subject] = None,
    project: Optional[Project] = None,
) -> Tuple[List[QuestionData], int, int]:
    """Assign sequential numbers to a batch of questions.

    Computes ``start = get_max_question_number(...) + 1`` and renumbers the
    batch from ``start``.

    Returns ``(renumbered_questions, start, end)``. Returns ``(questions,
    0, 0)`` unchanged if the list is empty.
    """
    if not questions:
        return questions, 0, 0
    start = get_max_question_number(subject=subject, project=project) + 1
    renumbered = assign_sequential_numbers(questions, start)
    end = start + len(renumbered) - 1
    return renumbered, start, end


def validate_import_data(content: str, auto_number: bool = False) -> ImportPreview:
    """Run the complete validation pipeline on raw JSON file content.

    When ``auto_number`` is True, question numbers in the JSON are ignored
    and duplicate numbers are not treated as errors (fresh sequential
    numbers are assigned later).
    """
    preview = ImportPreview()

    data, error = parse_json(content)
    if error:
        preview.errors.append(error)
        return preview

    subject_name, questions_list, root_errors = extract_root(data)
    preview.errors.extend(root_errors)
    if subject_name is None:
        return preview
    preview.subject_name = subject_name.strip()

    # The subject must already exist — we never create duplicate subjects.
    subject, subject_error = find_subject(subject_name)
    if subject_error:
        preview.errors.append(subject_error)
        return preview
    preview.subject = subject

    if questions_list is None:
        return preview

    valid, duplicates, question_errors = validate_questions(
        questions_list, auto_number=auto_number
    )
    preview.duplicate_numbers = duplicates
    preview.errors.extend(question_errors)
    if question_errors:
        return preview

    # Separate questions that already exist in the database.
    preview.questions, preview.conflicts = detect_conflicts(subject, valid)
    return preview


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_questions(subject: Subject, questions: List[QuestionData]) -> int:
    """Create Question records inside a single database transaction.

    The import is **all-or-nothing**: if creating any question fails, the
    entire transaction is rolled back and no partial data is written.

    Returns the number of questions created.
    """
    with transaction.atomic():
        for question in questions:
            Question.objects.create(
                subject=subject,
                question_number=question.question_number,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                python_code=question.python_code,
                practical_example=question.practical_example,
            )
    return len(questions)


# ===========================================================================
#  PROJECT IMPORT FAMILY
# ===========================================================================
#
# These functions are the exact parallel of the Subject import family above,
# but they assign questions to a Project instead of a Subject. The question
# validation logic (validate_questions) is shared.

#: Root-level key that must be present in a Project import JSON file.
PROJECT_ROOT_KEY = "project"


@dataclass
class ProjectImportPreview:
    """The result of validating a Project JSON import file."""

    project_name: str = ""
    project_id: Optional[int] = None
    project: Optional[Project] = None
    questions: List[QuestionData] = field(default_factory=list)
    conflicts: List[QuestionData] = field(default_factory=list)
    duplicate_numbers: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def find_project(name: str) -> Tuple[Optional[Project], Optional[str]]:
    """Look up a project by title (case-insensitive).

    Never creates a duplicate project. Returns ``(project, error)``.
    """
    project = Project.objects.filter(title__iexact=name.strip()).first()
    if project is None:
        available = ", ".join(
            Project.objects.values_list("title", flat=True).order_by("title")
        )
        error = (
            f"Project '{name.strip()}' was not found in the database. "
            f"Available projects: {available or '(none yet)'}."
        )
        return None, error
    return project, None


def detect_project_conflicts(
    project: Project, questions: List[QuestionData]
) -> Tuple[List[QuestionData], List[QuestionData]]:
    """Split questions into importable ones and ones that already exist.

    Existing questions are **never** overwritten; they are returned as
    ``conflicts`` so the caller can skip them.
    """
    existing_numbers = set(
        Question.objects.filter(project=project).values_list(
            "question_number", flat=True
        )
    )
    importable: List[QuestionData] = []
    conflicts: List[QuestionData] = []
    for question in questions:
        if question.question_number in existing_numbers:
            conflicts.append(question)
        else:
            importable.append(question)
    return importable, conflicts


def validate_project_import_data(
    content: str, auto_number: bool = False
) -> ProjectImportPreview:
    """Run the complete validation pipeline on a Project JSON file.

    The JSON root is ``{"project": "...", "questions": [...]}``.
    """
    preview = ProjectImportPreview()

    data, error = parse_json(content)
    if error:
        preview.errors.append(error)
        return preview

    if not isinstance(data, dict):
        preview.errors.append(
            "The JSON root must be an object with 'project' and 'questions'."
        )
        return preview

    project_name = data.get(PROJECT_ROOT_KEY)
    questions_list = data.get("questions")

    if not isinstance(project_name, str) or not project_name.strip():
        preview.errors.append(
            "The root 'project' must be a non-empty string."
        )
        return preview
    preview.project_name = project_name.strip()

    if questions_list is None:
        preview.errors.append("The root 'questions' key is missing.")
        return preview
    if not isinstance(questions_list, list):
        preview.errors.append("The root 'questions' must be a list.")
        return preview
    if len(questions_list) == 0:
        preview.errors.append("The 'questions' list is empty; nothing to import.")
        return preview

    # The project must already exist — we never create duplicate projects.
    project, project_error = find_project(project_name)
    if project_error:
        preview.errors.append(project_error)
        return preview
    preview.project = project
    preview.project_id = project.id

    valid, duplicates, question_errors = validate_questions(
        questions_list, auto_number=auto_number
    )
    preview.duplicate_numbers = duplicates
    preview.errors.extend(question_errors)
    if question_errors:
        return preview

    # Separate questions that already exist in the database.
    preview.questions, preview.conflicts = detect_project_conflicts(
        project, valid
    )
    return preview


def import_project_questions(
    project: Project, questions: List[QuestionData]
) -> int:
    """Create Question records for a Project inside one transaction.

    All-or-nothing, exactly like the subject importer.
    """
    with transaction.atomic():
        for question in questions:
            Question.objects.create(
                project=project,
                question_number=question.question_number,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                python_code=question.python_code,
                practical_example=question.practical_example,
            )
    return len(questions)


# ===========================================================================
#  COMPLETE-PROJECT IMPORT FAMILY
# ===========================================================================
#
# This family treats the JSON file as the SINGLE SOURCE OF TRUTH for a
# complete Project (project-level fields + its questions). Unlike the older
# "Project import" family above (which required the Project to already exist),
# this family CREATES the Project automatically if it does not exist.
#
# Behavior (approved):
# - The JSON root contains project-level fields and a "questions" list.
# - The Project is created automatically if it does not exist.
# - If a Project with the same SLUG already exists, we do NOT create a
#   duplicate and do NOT overwrite it. We surface a clear conflict and only
#   allow adding new questions (keeping existing project info unchanged).
# - Existing questions are never overwritten.
# - Project + questions are imported atomically (single transaction).
# - Markdown / fenced ```python code blocks are preserved verbatim.
# - The existing Subject importer is untouched.

#: Project-level fields accepted from the JSON root (map to Project model).
PROJECT_MARKDOWN_FIELDS = (
    "description",
    "overview",
    "complete_code",
    "output",
    "explanation",
    "learning_outcomes",
    "dataset_info",
)

#: All project-level fields we read from the JSON root.
PROJECT_TEXT_FIELDS = (
    "title",
    "slug",
    "short_description",
    *PROJECT_MARKDOWN_FIELDS,
)

#: A simple slug regex matching Django's SlugField format.
_SLUG_RE = r"^[-a-zA-Z0-9_]+$"


@dataclass
class CompleteProjectPreview:
    """The result of validating a complete-project JSON file."""

    project_data: Dict[str, str] = field(default_factory=dict)
    project: Optional[Project] = None
    project_exists: bool = False
    questions: List[QuestionData] = field(default_factory=list)
    conflicts: List[QuestionData] = field(default_factory=list)
    duplicate_numbers: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def validate_project_fields(data: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """Validate the project-level fields from the JSON root.

    Returns ``(project_data, errors)``.

    - ``title`` and ``slug`` must be non-empty strings.
    - ``slug`` must match Django's slug format.
    - All other fields must be strings if present (may be empty).
    - Markdown / multiline content is preserved (only outer whitespace is
      stripped; internal newlines and fenced code blocks are kept).
    """
    errors: List[str] = []
    project_data: Dict[str, str] = {}

    # --- title (required) -------------------------------------------------
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("The root 'title' must be a non-empty string.")
    else:
        project_data["title"] = title.strip()

    # --- slug (required, must match slug format) --------------------------
    slug = data.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        errors.append("The root 'slug' must be a non-empty string.")
    else:
        slug = slug.strip()
        import re
        if not re.match(_SLUG_RE, slug):
            errors.append(
                f"The root 'slug' '{slug}' is not a valid slug. Use lowercase "
                f"letters, numbers, hyphens, and underscores only."
            )
        else:
            project_data["slug"] = slug

    # --- short_description (optional string) ------------------------------
    short_description = data.get("short_description", "")
    if not isinstance(short_description, str):
        errors.append("The root 'short_description' must be a string (or omitted).")
    else:
        project_data["short_description"] = short_description.strip()

    # --- Markdown content fields (optional strings, preserved verbatim) ---
    for field_name in PROJECT_MARKDOWN_FIELDS:
        value = data.get(field_name, "")
        if not isinstance(value, str):
            errors.append(
                f"The root '{field_name}' must be a string (or omitted)."
            )
        else:
            # Preserve internal Markdown/newlines; only strip outer whitespace.
            project_data[field_name] = value.strip()

    return project_data, errors


def find_project_by_slug(slug: str) -> Optional[Project]:
    """Look up an existing project by slug (case-insensitive)."""
    return Project.objects.filter(slug__iexact=slug.strip()).first()


def validate_complete_project_import_data(
    content: str, auto_number: bool = False
) -> CompleteProjectPreview:
    """Run the complete validation pipeline on a complete-project JSON file.

    When ``auto_number`` is True, question numbers in the JSON are ignored
    and duplicate numbers are not treated as errors (fresh sequential
    numbers are assigned later).

    The JSON root is::

        {
          "title": "...",
          "slug": "...",
          "short_description": "...",
          "description": "...",
          "overview": "...",
          "complete_code": "...",
          "output": "...",
          "explanation": "...",
          "learning_outcomes": "...",
          "dataset_info": "...",
          "questions": [ { ... } ]
        }

    Everything is validated BEFORE anything is written to the database.
    """
    preview = CompleteProjectPreview()

    data, error = parse_json(content)
    if error:
        preview.errors.append(error)
        return preview

    if not isinstance(data, dict):
        preview.errors.append(
            "The JSON root must be an object with project fields and 'questions'."
        )
        return preview

    # --- Validate project-level fields ------------------------------------
    project_data, project_errors = validate_project_fields(data)
    preview.project_data = project_data
    preview.errors.extend(project_errors)
    # If title or slug failed validation, we cannot proceed.
    if "title" not in project_data or "slug" not in project_data:
        return preview

    # --- Validate the questions list ---------------------------------------
    questions_list = data.get("questions")
    if questions_list is None:
        preview.errors.append("The root 'questions' key is missing.")
        return preview
    if not isinstance(questions_list, list):
        preview.errors.append("The root 'questions' must be a list.")
        return preview
    if len(questions_list) == 0:
        preview.errors.append("The 'questions' list is empty; nothing to import.")
        return preview

    valid, duplicates, question_errors = validate_questions(
        questions_list, auto_number=auto_number
    )
    preview.duplicate_numbers = duplicates
    preview.errors.extend(question_errors)
    if question_errors:
        return preview

    # --- Detect an existing project by slug -------------------------------
    existing = find_project_by_slug(project_data["slug"])
    if existing is not None:
        preview.project = existing
        preview.project_exists = True
        # Only add NEW questions; existing questions are never overwritten.
        preview.questions, preview.conflicts = detect_project_conflicts(
            existing, valid
        )
    else:
        preview.questions = valid

    return preview


def import_complete_project(preview: CompleteProjectPreview) -> int:
    """Create (or attach to) a Project and its questions atomically.

    Behavior:
    - If the project does NOT exist, it is created from ``preview.project_data``.
    - If the project DOES exist, it is NOT modified (no overwrite). Only new
      questions are added.
    - Existing questions are never overwritten.
    - Everything happens inside a single transaction; on any failure the whole
      import is rolled back.

    Returns the number of questions created.
    """
    with transaction.atomic():
        if preview.project_exists and preview.project is not None:
            project = preview.project
        else:
            project = Project.objects.create(
                title=preview.project_data["title"],
                slug=preview.project_data["slug"],
                short_description=preview.project_data.get("short_description", ""),
                description=preview.project_data.get("description", ""),
                overview=preview.project_data.get("overview", ""),
                complete_code=preview.project_data.get("complete_code", ""),
                output=preview.project_data.get("output", ""),
                explanation=preview.project_data.get("explanation", ""),
                learning_outcomes=preview.project_data.get("learning_outcomes", ""),
                dataset_info=preview.project_data.get("dataset_info", ""),
            )

        for question in preview.questions:
            Question.objects.create(
                project=project,
                question_number=question.question_number,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                python_code=question.python_code,
                practical_example=question.practical_example,
            )

    return len(preview.questions)

