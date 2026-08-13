"""
Admin views for the JSON question importer.

These views are mounted inside the Django Admin (see ``core/admin.py`` and
``QuestionAdmin.get_urls()``). They implement the 3-step workflow:

    1. ``import-json``        → upload the .json file (GET form / POST upload)
    2. ``import-json-preview``→ validate + show preview, ask for confirmation
    3. ``import-json-confirm``→ import inside a DB transaction (POST only)
    4. ``import-json-result`` → success summary

Security:
- Every view is wrapped with ``admin_site.admin_view`` which enforces the
  normal admin login / staff checks.
- We additionally require the ``core.add_question`` permission.
- Only ``.json`` files up to 2 MB are accepted.
- Content is parsed as JSON text only. The ``python_code`` field is stored
  as plain text and is **never executed**.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models import CodingExercise, CodingLesson, Project, Question, Subject
from core.services import coding_exercise_importer as coding_importer
from core.services import question_importer as importer

#: Session keys used to carry data between the admin steps.
SESSION_PREVIEW_KEY = "question_import_preview"
SESSION_RESULT_KEY = "question_import_result"

#: Field names we reconstruct a QuestionData from when importing.
_QUESTION_FIELDS = (
    "question_number",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_answer",
    "explanation",
    "python_code",
    "practical_example",
)


def _has_import_permission(request) -> bool:
    """True if the user may add questions (and therefore import them)."""
    return request.user.is_active and request.user.has_perm("core.add_question")


def _ensure_import_permission(request):
    """Raise PermissionDenied if the user cannot import questions."""
    if not _has_import_permission(request):
        raise PermissionDenied("You do not have permission to import questions.")


def _render_admin(request, template, context):
    """Render a template using the standard admin base template."""
    context.setdefault("site_header", "Django administration")
    context.setdefault("site_title", "Django site admin")
    context.setdefault("title", "Import Questions from JSON")
    context.setdefault("has_permission", _has_import_permission(request))
    context.setdefault("is_popup", False)
    context.setdefault("is_nav_sidebar_enabled", True)
    # The templates use ``opts.app_label`` / ``opts.model_name`` for the
    # admin body CSS class, just like the built-in admin change views.
    context.setdefault("opts", {"app_label": "core", "model_name": "question"})
    return render(request, template, context)


# ---------------------------------------------------------------------------
# Step 1 — Upload
# ---------------------------------------------------------------------------

def import_json_upload(request):
    """Upload page. GET shows the form; POST parses + validates the file."""
    _ensure_import_permission(request)

    if request.method == "POST":
        return _handle_upload(request)

    return _render_admin(request, "admin/core/question/import_json.html", {})


def _handle_upload(request):
    """Validate the uploaded file and store the preview in the session."""
    file = request.FILES.get("json_file")
    if file is None:
        messages.error(request, "No file was selected. Please choose a .json file.")
        return _render_admin(
            request, "admin/core/question/import_json.html", {}
        )

    # --- File type + size checks -----------------------------------------
    if not file.name.lower().endswith(".json"):
        messages.error(
            request,
            f"'{file.name}' is not a JSON file. Please upload a file ending "
            f"in .json.",
        )
        return _render_admin(request, "admin/core/question/import_json.html", {})

    if file.size > importer.MAX_FILE_SIZE_BYTES:
        messages.error(
            request,
            f"File is too large ({file.size} bytes). Maximum allowed is "
            f"{importer.MAX_FILE_SIZE_BYTES} bytes.",
        )
        return _render_admin(request, "admin/core/question/import_json.html", {})

    # --- Read as text (UTF-8). Never executed, just parsed. ---------------
    try:
        content = file.read().decode("utf-8")
    except UnicodeDecodeError:
        messages.error(
            request,
            "The file could not be read as UTF-8 text. Please save it as a "
            "UTF-8 encoded JSON file.",
        )
        return _render_admin(request, "admin/core/question/import_json.html", {})

# --- Auto-numbering checkbox ------------------------------------------
    # When checked, the question_number values in the JSON are ignored and
    # fresh sequential numbers are assigned from (max existing + 1).
    auto_number = request.POST.get("auto_number") == "on"

    # --- Validate everything ----------------------------------------------
    preview = importer.validate_import_data(content, auto_number=auto_number)

    # Persist the validated result so the preview step can display it.
    request.session[SESSION_PREVIEW_KEY] = {
        "filename": file.name,
        "subject_id": preview.subject.id if preview.subject else None,
        "subject_name": preview.subject_name,
        "auto_number": auto_number,
        "questions": [importer.question_to_dict(q) for q in preview.questions],
        "conflicts": [importer.question_to_dict(q) for q in preview.conflicts],
        "duplicate_numbers": preview.duplicate_numbers,
        "errors": preview.errors,
    }
    return redirect("admin:core_question_import_json_preview")


# ---------------------------------------------------------------------------
# Step 2 — Preview + confirmation
# ---------------------------------------------------------------------------

def import_json_preview(request):
    """Show validation results and ask the user to confirm the import."""
    _ensure_import_permission(request)

    session_data = request.session.get(SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_question_import_json")

    subject = (
        Subject.objects.filter(id=session_data.get("subject_id")).first()
        if session_data.get("subject_id")
        else None
    )

    context = {
        "filename": session_data.get("filename", ""),
        "subject_name": session_data.get("subject_name", ""),
        "subject": subject,
        "auto_number": session_data.get("auto_number", False),
        "questions": [
            importer.dict_to_question(q)
            for q in session_data.get("questions", [])
        ],
        "conflicts": [
            importer.dict_to_question(q)
            for q in session_data.get("conflicts", [])
        ],
        "duplicate_numbers": session_data.get("duplicate_numbers", []),
        "errors": session_data.get("errors", []),
    }
    return _render_admin(
        request, "admin/core/question/import_json_preview.html", context
    )


# ---------------------------------------------------------------------------
# Step 3 — Confirm + import (POST only)
# ---------------------------------------------------------------------------

def import_json_confirm(request):
    """Import the questions inside a single database transaction."""
    _ensure_import_permission(request)

    if request.method != "POST":
        return redirect("admin:core_question_import_json")

    session_data = request.session.get(SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_question_import_json")

    subject_id = session_data.get("subject_id")
    subject = Subject.objects.filter(id=subject_id).first()
    if subject is None:
        messages.error(request, "The subject for this import no longer exists.")
        request.session.pop(SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_question_import_json")

# Rebuild the importable questions and re-check for conflicts. This guards
    # against another admin adding the same question numbers between the
    # preview and the confirm step (race condition).
    questions = [
        importer.dict_to_question(q) for q in session_data.get("questions", [])
    ]
    auto_number = session_data.get("auto_number", False)

    # If auto-numbering is ON, we re-detect the current highest question
    # number and re-assign fresh sequential numbers right before importing.
    # This guards against another admin adding questions between the preview
    # and confirm steps.
    if auto_number:
        importable, start, end = importer.apply_auto_numbering(
            questions, subject=subject
        )
        late_conflicts = []
    else:
        importable, late_conflicts = importer.detect_conflicts(
            subject, questions
        )
        if late_conflicts:
            # New conflicts since the preview — tell the user and stop.
            numbers = sorted(q.question_number for q in late_conflicts)
            messages.warning(
                request,
                "The following question numbers were added by someone else since "
                "the preview and were NOT imported (no overwrites): "
                f"{', '.join(str(n) for n in numbers)}.",
            )
            importable = [q for q in importable if q not in late_conflicts]

    if not importable:
        messages.error(
            request,
            "There are no new questions to import for this subject. "
            "Nothing was changed.",
        )
        request.session.pop(SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_question_import_json")

    # Import everything inside one transaction. If any single question fails,
    # the entire import is rolled back (all-or-nothing).
    try:
        count = importer.import_questions(subject, importable)
    except Exception as exc:  # pragma: no cover - safety net
        request.session.pop(SESSION_PREVIEW_KEY, None)
        messages.error(
            request,
            "The import failed and was fully rolled back. No questions were "
            f"created. Error: {exc}",
        )
        return redirect("admin:core_question_import_json")

    numbers = sorted(q.question_number for q in importable)
    total_for_subject = Question.objects.filter(subject=subject).count()

    request.session[SESSION_RESULT_KEY] = {
        "subject_name": subject.name,
        "imported_count": count,
        "min_number": numbers[0] if numbers else None,
        "max_number": numbers[-1] if numbers else None,
        "auto_number": auto_number,
        "total_for_subject": total_for_subject,
        "skipped_conflicts": len(late_conflicts),
    }
    request.session.pop(SESSION_PREVIEW_KEY, None)
    return redirect("admin:core_question_import_json_result")


# ---------------------------------------------------------------------------
# Step 4 — Result summary
# ---------------------------------------------------------------------------

def import_json_result(request):
    """Show the success summary after a completed import."""
    _ensure_import_permission(request)

    result = request.session.pop(SESSION_RESULT_KEY, None)
    if result is None:
        messages.info(request, "No recent import to show.")
        return redirect("admin:core_question_changelist")

    context = {
        "result": result,
        "changelist_url": reverse("admin:core_question_changelist"),
    }
    return _render_admin(
        request, "admin/core/question/import_json_result.html", context
    )


# ===========================================================================
#  PROJECT JSON IMPORTER
# ===========================================================================
#
# These views are the exact parallel of the subject importer above, but they
# import questions into a Project instead of a Subject. They are mounted under
# the Project admin (see ProjectAdmin.get_urls() in core/admin.py).
#
# The workflow is identical: upload → preview → confirm → result, all
# guarded by the same staff + add_question permission checks.

#: Session keys used to carry the project import between the admin steps.
PROJECT_SESSION_PREVIEW_KEY = "project_import_preview"
PROJECT_SESSION_RESULT_KEY = "project_import_result"


def _render_project_admin(request, template, context):
    """Render a template using the standard admin base template."""
    context.setdefault("site_header", "Django administration")
    context.setdefault("site_title", "Django site admin")
    context.setdefault("title", "Import Project from JSON")
    context.setdefault("has_permission", _has_import_permission(request))
    context.setdefault("is_popup", False)
    context.setdefault("is_nav_sidebar_enabled", True)
    context.setdefault("opts", {"app_label": "core", "model_name": "project"})
    return render(request, template, context)


def project_import_json_upload(request):
    """Upload page for a complete Project JSON file. GET form / POST upload."""
    _ensure_import_permission(request)

    if request.method == "POST":
        return _handle_project_upload(request)

    return _render_project_admin(
        request, "admin/core/project/import_json.html", {}
    )


def _handle_project_upload(request):
    """Validate the uploaded project file and store the preview in session."""
    file = request.FILES.get("json_file")
    if file is None:
        messages.error(request, "No file was selected. Please choose a .json file.")
        return _render_project_admin(
            request, "admin/core/project/import_json.html", {}
        )

    if not file.name.lower().endswith(".json"):
        messages.error(
            request,
            f"'{file.name}' is not a JSON file. Please upload a file ending "
            f"in .json.",
        )
        return _render_project_admin(
            request, "admin/core/project/import_json.html", {}
        )

    if file.size > importer.MAX_FILE_SIZE_BYTES:
        messages.error(
            request,
            f"File is too large ({file.size} bytes). Maximum allowed is "
            f"{importer.MAX_FILE_SIZE_BYTES} bytes.",
        )
        return _render_project_admin(
            request, "admin/core/project/import_json.html", {}
        )

    try:
        content = file.read().decode("utf-8")
    except UnicodeDecodeError:
        messages.error(
            request,
            "The file could not be read as UTF-8 text. Please save it as a "
            "UTF-8 encoded JSON file.",
        )
        return _render_project_admin(
            request, "admin/core/project/import_json.html", {}
        )

# Auto-numbering checkbox (subject importer uses the same field name).
    auto_number = request.POST.get("auto_number") == "on"

    # Validate the COMPLETE project (project fields + questions) before
    # anything is written to the database.
    preview = importer.validate_complete_project_import_data(
        content, auto_number=auto_number
    )

    request.session[PROJECT_SESSION_PREVIEW_KEY] = {
        "filename": file.name,
        "project_data": preview.project_data,
        "project_id": preview.project.id if preview.project else None,
        "project_name": preview.project_data.get("title", ""),
        "project_exists": preview.project_exists,
        "auto_number": auto_number,
        "questions": [importer.question_to_dict(q) for q in preview.questions],
        "conflicts": [importer.question_to_dict(q) for q in preview.conflicts],
        "duplicate_numbers": preview.duplicate_numbers,
        "errors": preview.errors,
    }
    return redirect("admin:core_project_import_json_preview")


def project_import_json_preview(request):
    """Show validation results and ask the user to confirm."""
    _ensure_import_permission(request)

    session_data = request.session.get(PROJECT_SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_project_import_json")

    project = (
        Project.objects.filter(id=session_data.get("project_id")).first()
        if session_data.get("project_id")
        else None
    )

    # The project fields that will be used to create the Project (shown in
    # the preview so the admin can confirm before anything is written).
    project_data = session_data.get("project_data", {})

    context = {
        "filename": session_data.get("filename", ""),
        "project_name": session_data.get("project_name", ""),
        "project": project,
        "project_exists": session_data.get("project_exists", False),
        "project_data": project_data,
        "auto_number": session_data.get("auto_number", False),
        "questions": [
            importer.dict_to_question(q)
            for q in session_data.get("questions", [])
        ],
        "conflicts": [
            importer.dict_to_question(q)
            for q in session_data.get("conflicts", [])
        ],
        "duplicate_numbers": session_data.get("duplicate_numbers", []),
        "errors": session_data.get("errors", []),
    }
    return _render_project_admin(
        request, "admin/core/project/import_json_preview.html", context
    )


def project_import_json_confirm(request):
    """Import the complete project (Project + questions) atomically."""
    _ensure_import_permission(request)

    if request.method != "POST":
        return redirect("admin:core_project_import_json")

    session_data = request.session.get(PROJECT_SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_project_import_json")

    # Rebuild the project_data and questions from the session.
    project_data = session_data.get("project_data", {})
    if not project_data.get("title") or not project_data.get("slug"):
        messages.error(request, "The project data for this import is invalid.")
        request.session.pop(PROJECT_SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_project_import_json")

    questions = [
        importer.dict_to_question(q)
        for q in session_data.get("questions", [])
    ]
    auto_number = session_data.get("auto_number", False)

    project_exists = session_data.get("project_exists", False)
    project = None
    late_conflicts = []
    if project_exists:
        project = Project.objects.filter(id=session_data.get("project_id")).first()
        if project is None:
            messages.error(
                request, "The project for this import no longer exists."
            )
            request.session.pop(PROJECT_SESSION_PREVIEW_KEY, None)
            return redirect("admin:core_project_import_json")

        if auto_number:
            # Re-detect the highest number and re-assign fresh sequential
            # numbers right before importing (race-condition guard).
            questions, start, end = importer.apply_auto_numbering(
                questions, project=project
            )
        else:
            # Re-check for conflicts (race condition guard). Existing
            # questions are never overwritten.
            importable, late_conflicts = importer.detect_project_conflicts(
                project, questions
            )
            if late_conflicts:
                numbers = sorted(q.question_number for q in late_conflicts)
                messages.warning(
                    request,
                    "The following question numbers were added by someone else "
                    "since the preview and were NOT imported (no overwrites): "
                    f"{', '.join(str(n) for n in numbers)}.",
                )
                importable = [q for q in importable if q not in late_conflicts]
            questions = importable

    if len(questions) == 0:
        messages.error(
            request,
            "There are no new questions to import. Nothing was changed.",
        )
        request.session.pop(PROJECT_SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_project_import_json")

    # Build a fresh CompleteProjectPreview for the atomic import.
    preview = importer.CompleteProjectPreview(
        project_data=project_data,
        project=project,
        project_exists=project_exists,
        questions=questions,
    )

    try:
        count = importer.import_complete_project(preview)
    except Exception as exc:  # pragma: no cover - safety net
        request.session.pop(PROJECT_SESSION_PREVIEW_KEY, None)
        messages.error(
            request,
            "The import failed and was fully rolled back. No project or "
            f"questions were created. Error: {exc}",
        )
        return redirect("admin:core_project_import_json")

    numbers = sorted(q.question_number for q in questions)
    created_project = preview.project
    total_for_project = (
        Question.objects.filter(project=created_project).count()
        if created_project is not None
        else 0
    )

    request.session[PROJECT_SESSION_RESULT_KEY] = {
        "project_name": created_project.title if created_project else project_data["title"],
        "project_slug": created_project.slug if created_project else project_data["slug"],
        "project_created": not project_exists,
        "project_exists": project_exists,
        "imported_count": count,
        "min_number": numbers[0] if numbers else None,
        "max_number": numbers[-1] if numbers else None,
        "auto_number": auto_number,
        "total_for_project": total_for_project,
        "skipped_conflicts": len(session_data.get("conflicts", [])),
    }
    request.session.pop(PROJECT_SESSION_PREVIEW_KEY, None)
    return redirect("admin:core_project_import_json_result")


def project_import_json_result(request):
    """Show the success summary after a completed project import."""
    _ensure_import_permission(request)

    result = request.session.pop(PROJECT_SESSION_RESULT_KEY, None)
    if result is None:
        messages.info(request, "No recent import to show.")
        return redirect("admin:core_project_changelist")

    context = {
        "result": result,
        "changelist_url": reverse("admin:core_project_changelist"),
    }
    return _render_project_admin(
        request, "admin/core/project/import_json_result.html", context
    )


# ===========================================================================
#  CODING EXERCISE JSON IMPORTER
# ===========================================================================
#
# These views are the exact parallel of the subject importer above, but they
# import Coding Exercises into a CodingLesson. They are mounted under the
# CodingLesson admin (see CodingLessonAdmin.get_urls() in core/admin.py).
#
# The workflow is identical: upload → preview → confirm → result, all
# guarded by the same staff + add_question permission checks.

#: Session keys used to carry the coding exercise import between admin steps.
CODING_SESSION_PREVIEW_KEY = "coding_import_preview"
CODING_SESSION_RESULT_KEY = "coding_import_result"


def _render_coding_admin(request, template, context):
    """Render a template using the standard admin base template."""
    context.setdefault("site_header", "Django administration")
    context.setdefault("site_title", "Django site admin")
    context.setdefault("title", "Import Coding Exercises from JSON")
    context.setdefault("has_permission", _has_import_permission(request))
    context.setdefault("is_popup", False)
    context.setdefault("is_nav_sidebar_enabled", True)
    context.setdefault("opts", {"app_label": "core", "model_name": "codinglesson"})
    return render(request, template, context)


def coding_lesson_import_upload(request):
    """Upload page for a Coding Lesson JSON file. GET form / POST upload."""
    _ensure_import_permission(request)

    if request.method == "POST":
        return _handle_coding_upload(request)

    return _render_coding_admin(
        request, "admin/core/codinglesson/import_json.html", {}
    )


def _handle_coding_upload(request):
    """Validate the uploaded coding lesson file and store preview in session."""
    file = request.FILES.get("json_file")
    if file is None:
        messages.error(request, "No file was selected. Please choose a .json file.")
        return _render_coding_admin(
            request, "admin/core/codinglesson/import_json.html", {}
        )

    if not file.name.lower().endswith(".json"):
        messages.error(
            request,
            f"'{file.name}' is not a JSON file. Please upload a file ending "
            f"in .json.",
        )
        return _render_coding_admin(
            request, "admin/core/codinglesson/import_json.html", {}
        )

    if file.size > coding_importer.MAX_FILE_SIZE_BYTES:
        messages.error(
            request,
            f"File is too large ({file.size} bytes). Maximum allowed is "
            f"{coding_importer.MAX_FILE_SIZE_BYTES} bytes.",
        )
        return _render_coding_admin(
            request, "admin/core/codinglesson/import_json.html", {}
        )

    try:
        content = file.read().decode("utf-8")
    except UnicodeDecodeError:
        messages.error(
            request,
            "The file could not be read as UTF-8 text. Please save it as a "
            "UTF-8 encoded JSON file.",
        )
        return _render_coding_admin(
            request, "admin/core/codinglesson/import_json.html", {}
        )

    # Auto-numbering checkbox (subject importer uses the same field name).
    auto_number = request.POST.get("auto_number") == "on"

    # Validate the COMPLETE coding lesson (lesson fields + exercises) before
    # anything is written to the database.
    preview = coding_importer.validate_coding_lesson_import_data(
        content, auto_number=auto_number
    )

    request.session[CODING_SESSION_PREVIEW_KEY] = {
        "filename": file.name,
        "lesson_data": preview.lesson_data,
        "lesson_id": preview.lesson.id if preview.lesson else None,
        "lesson_name": preview.lesson_data.get("topic", ""),
        "lesson_exists": preview.lesson_exists,
        "auto_number": auto_number,
        "exercises": [
            coding_importer.exercise_to_dict(e) for e in preview.exercises
        ],
        "conflicts": [
            coding_importer.exercise_to_dict(e) for e in preview.conflicts
        ],
        "duplicate_numbers": preview.duplicate_numbers,
        "errors": preview.errors,
    }
    return redirect("admin:core_codinglesson_import_json_preview")


def coding_lesson_import_preview(request):
    """Show validation results and ask the user to confirm."""
    _ensure_import_permission(request)

    session_data = request.session.get(CODING_SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_codinglesson_import_json")

    lesson = (
        CodingLesson.objects.filter(id=session_data.get("lesson_id")).first()
        if session_data.get("lesson_id")
        else None
    )

    lesson_data = session_data.get("lesson_data", {})

    context = {
        "filename": session_data.get("filename", ""),
        "lesson_name": session_data.get("lesson_name", ""),
        "lesson": lesson,
        "lesson_exists": session_data.get("lesson_exists", False),
        "lesson_data": lesson_data,
        "auto_number": session_data.get("auto_number", False),
        "exercises": [
            coding_importer.dict_to_exercise(e)
            for e in session_data.get("exercises", [])
        ],
        "conflicts": [
            coding_importer.dict_to_exercise(e)
            for e in session_data.get("conflicts", [])
        ],
        "duplicate_numbers": session_data.get("duplicate_numbers", []),
        "errors": session_data.get("errors", []),
    }
    return _render_coding_admin(
        request, "admin/core/codinglesson/import_json_preview.html", context
    )


def coding_lesson_import_confirm(request):
    """Import the complete coding lesson (Lesson + exercises) atomically."""
    _ensure_import_permission(request)

    if request.method != "POST":
        return redirect("admin:core_codinglesson_import_json")

    session_data = request.session.get(CODING_SESSION_PREVIEW_KEY)
    if session_data is None:
        messages.warning(
            request,
            "No import in progress. Please upload a JSON file first.",
        )
        return redirect("admin:core_codinglesson_import_json")

    # Rebuild the lesson_data and exercises from the session.
    lesson_data = session_data.get("lesson_data", {})
    if not lesson_data.get("module") or not lesson_data.get("topic") or not lesson_data.get("lesson_slug"):
        messages.error(request, "The lesson data for this import is invalid.")
        request.session.pop(CODING_SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_codinglesson_import_json")

    exercises = [
        coding_importer.dict_to_exercise(e)
        for e in session_data.get("exercises", [])
    ]
    auto_number = session_data.get("auto_number", False)

    lesson_exists = session_data.get("lesson_exists", False)
    lesson = None
    late_conflicts = []
    if lesson_exists:
        lesson = CodingLesson.objects.filter(id=session_data.get("lesson_id")).first()
        if lesson is None:
            messages.error(
                request, "The lesson for this import no longer exists."
            )
            request.session.pop(CODING_SESSION_PREVIEW_KEY, None)
            return redirect("admin:core_codinglesson_import_json")

    # Auto-numbering applies to BOTH existing and new lessons. For a new
    # lesson there are no existing exercises, so numbering starts at 1. For
    # an existing lesson we re-detect the highest number and continue from
    # max(existing) + 1 (race-condition guard).
    if auto_number:
        if lesson_exists:
            exercises, start, end = coding_importer.apply_auto_numbering(
                exercises, lesson=lesson
            )
        else:
            exercises = coding_importer.assign_sequential_numbers(exercises, 1)
            start, end = (1, len(exercises)) if exercises else (0, 0)
    elif lesson_exists:
        # Re-check for conflicts (race condition guard). Existing
        # exercises are never overwritten.
        importable, late_conflicts = coding_importer.detect_conflicts(
            lesson, exercises
        )
        if late_conflicts:
            numbers = sorted(e.exercise_number for e in late_conflicts)
            messages.warning(
                request,
                "The following exercise numbers were added by someone else "
                "since the preview and were NOT imported (no overwrites): "
                f"{', '.join(str(n) for n in numbers)}.",
            )
            importable = [e for e in importable if e not in late_conflicts]
        exercises = importable

    if len(exercises) == 0:
        messages.error(
            request,
            "There are no new exercises to import. Nothing was changed.",
        )
        request.session.pop(CODING_SESSION_PREVIEW_KEY, None)
        return redirect("admin:core_codinglesson_import_json")

    # Build a fresh CodingLessonPreview for the atomic import.
    preview = coding_importer.CodingLessonPreview(
        lesson_data=lesson_data,
        lesson=lesson,
        lesson_exists=lesson_exists,
        exercises=exercises,
    )

    try:
        count = coding_importer.import_coding_lesson(preview)
    except Exception as exc:  # pragma: no cover - safety net
        request.session.pop(CODING_SESSION_PREVIEW_KEY, None)
        messages.error(
            request,
            "The import failed and was fully rolled back. No lesson or "
            f"exercises were created. Error: {exc}",
        )
        return redirect("admin:core_codinglesson_import_json")

    numbers = sorted(e.exercise_number for e in exercises)
    created_lesson = preview.lesson
    total_for_lesson = (
        CodingExercise.objects.filter(lesson=created_lesson).count()
        if created_lesson is not None
        else 0
    )

    request.session[CODING_SESSION_RESULT_KEY] = {
        "lesson_name": created_lesson.topic if created_lesson else lesson_data["topic"],
        "lesson_slug": created_lesson.lesson_slug if created_lesson else lesson_data["lesson_slug"],
        "lesson_created": not lesson_exists,
        "lesson_exists": lesson_exists,
        "imported_count": count,
        "min_number": numbers[0] if numbers else None,
        "max_number": numbers[-1] if numbers else None,
        "auto_number": auto_number,
        "total_for_lesson": total_for_lesson,
        "skipped_conflicts": len(session_data.get("conflicts", [])),
    }
    request.session.pop(CODING_SESSION_PREVIEW_KEY, None)
    return redirect("admin:core_codinglesson_import_json_result")


def coding_lesson_import_result(request):
    """Show the success summary after a completed coding lesson import."""
    _ensure_import_permission(request)

    result = request.session.pop(CODING_SESSION_RESULT_KEY, None)
    if result is None:
        messages.info(request, "No recent import to show.")
        return redirect("admin:core_codinglesson_changelist")

    context = {
        "result": result,
        "changelist_url": reverse("admin:core_codinglesson_changelist"),
    }
    return _render_coding_admin(
        request, "admin/core/codinglesson/import_json_result.html", context
    )

