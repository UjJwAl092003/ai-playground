"""
Views for the learning platform.

These functions handle HTTP requests and return responses.

The public learning flow is:
    Home (subject list) -> Subject page -> Learn (MCQ) page.

The Learn page loads each question and checks answers through small JSON
"API" endpoints below. This keeps the database logic on the server and the
frontend free of hard-coded questions.

Step 4 additions:
- User registration (register view)
- Dashboard with overall + subject-wise progress (dashboard view)
- Simple profile page (profile view)
- Progress saving when a logged-in user submits an answer
- Continue Learning: next unanswered question detection
- Dynamic navbar: Login/Register for guests, Dashboard/Logout for logged-in users

Review Mistakes additions:
- review_mistakes: lists the current user's incorrectly-answered questions,
  grouped by subject (optionally filtered by one subject via slug).
- review_learn: renders the EXISTING learn shell in "review mode" so the
  learner re-answers their mistakes through the normal MCQ interface.
- review_questions_api: returns the ordered list of the user's mistakes as
  JSON so learn.js can drive review navigation.

No database migration is needed: a "mistake" is simply a UserProgress row
with is_correct=False. Answering correctly in review updates the SAME row
via update_or_create, which removes it from the mistake list automatically.
"""

import json

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import (
    CodingExercise,
    CodingLesson,
    CodingProgress,
    Project,
    Question,
    Subject,
    UserProgress,
)
from .services import access as access_service
from .services.access import get_guest_free_limit


# ============================================================================
#  PUBLIC VIEWS (no login required — public browsing preserved)
# ============================================================================


def home(request):
    """
    Homepage: lists every subject from the database, plus the active projects.
    Each subject shows its name, question count, and a Start Learning button.
    """
    subjects = Subject.objects.all().order_by('order', 'name')
    projects = Project.objects.filter(is_active=True).order_by('order', 'title')
    return render(
        request,
        'core/home.html',
        {'subjects': subjects, 'projects': projects},
    )


def subject_detail(request, slug):
    """
    Subject page: shows the subject name, the number of questions
    available, and a Start Learning button.

    For logged-in users, also shows:
    - How many questions they've completed in this subject
    - How many are correct/incorrect
    - A "Continue Learning" button if they have unanswered questions
    - A "Completed" badge if all questions are done
    """
    subject = get_object_or_404(Subject, slug=slug)
    total = subject.questions.count()

    # Coding lessons optionally linked to this subject (for the MCQ → coding
    # exercise learning flow). Shown only if the subject has any.
    coding_lessons = subject.coding_lessons.all().order_by('module', 'topic')

    context = {
        'subject': subject,
        'question_count': total,
        'coding_lessons': coding_lessons,
    }

    # If the user is logged in, compute their progress for this subject
    if request.user.is_authenticated and total > 0:
        user_progress = UserProgress.objects.filter(
            user=request.user,
            question__subject=subject,
        )
        completed_count = user_progress.count()
        correct_count = user_progress.filter(is_correct=True).count()
        wrong_count = user_progress.filter(is_correct=False).count()

        # Find the next unanswered question number
        answered_numbers = set(
            user_progress.values_list('question__question_number', flat=True)
        )
        all_numbers = set(
            subject.questions.values_list('question_number', flat=True)
        )
        unanswered = sorted(all_numbers - answered_numbers)

        context.update({
            'completed_count': completed_count,
            'correct_count': correct_count,
            'wrong_count': wrong_count,
            'all_completed': completed_count >= total,
            'continue_number': unanswered[0] if unanswered else None,
        })

    return render(request, 'core/subject_detail.html', context)


@ensure_csrf_cookie
def learn(request, slug):
    """
    The MCQ learning page (application shell).

    The page itself is a shell: the actual question content is loaded
    through the JSON endpoints below, so moving between questions does
    not reload the whole application.

For logged-in users:
    - If they have existing progress, they start from the first unanswered
      question (Continue Learning).
    - If they have no progress, they start from question 1.
    - If they've completed all questions, they start from question 1
      (they can review).
    """
    subject = get_object_or_404(Subject, slug=slug)
    total = subject.questions.count()

    context = {
        'subject': subject,
        'total': total,
        'no_questions': total == 0,
        # Guest experience config (passed to the template → LEARN_CONFIG)
        'is_guest': not request.user.is_authenticated,
        'guest_free_limit': get_guest_free_limit(),
        'guest_attempts_used': access_service.get_guest_attempts_used(request),
        'guest_limit_reached': access_service.guest_limit_reached(request),
    }

    if total > 0:
        if request.user.is_authenticated:
            # Find the first unanswered question for Continue Learning
            answered_numbers = set(
                UserProgress.objects.filter(
                    user=request.user,
                    question__subject=subject,
                ).values_list('question__question_number', flat=True)
            )
            all_numbers = set(
                subject.questions.values_list('question_number', flat=True)
            )
            unanswered = sorted(all_numbers - answered_numbers)

            if unanswered:
                context['first_number'] = unanswered[0]
            else:
                # All questions completed — start from the beginning (review)
                first = subject.questions.order_by('question_number').first()
                context['first_number'] = first.question_number
        else:
            # Not logged in — start from question 1
            first = subject.questions.order_by('question_number').first()
            context['first_number'] = first.question_number

    return render(request, 'core/learn.html', context)


# ============================================================================
#  JSON DATA ENDPOINTS (used by the JavaScript frontend on the Learn page)
# ============================================================================


def question_data(request, slug, question_number):
    """
    JSON endpoint: returns one question (WITHOUT the correct answer)
    for a given subject and question number.

    The frontend calls this to display each question.

    The correct answer is intentionally omitted from this response
    so that the user cannot cheat by inspecting the network traffic.
    """
    subject = get_object_or_404(Subject, slug=slug)
    question = get_object_or_404(
        Question,
        subject=subject,
        question_number=question_number,
    )

    # Build the options dict with labels A, B, C, D
    options = {
        'A': question.option_a,
        'B': question.option_b,
        'C': question.option_c,
        'D': question.option_d,
    }

    # Check if the user has already answered this question
    previous_answer = None
    previous_is_correct = None
    if request.user.is_authenticated:
        try:
            progress = UserProgress.objects.get(
                user=request.user,
                question=question,
            )
            previous_answer = progress.selected_answer
            previous_is_correct = progress.is_correct
        except UserProgress.DoesNotExist:
            pass

    return JsonResponse({
        'question_number': question.question_number,
        'question_text': question.question_text,
        'options': options,
        'total': subject.questions.count(),
        'previous_answer': previous_answer,
        'previous_is_correct': previous_is_correct,
    })


def check_answer(request, slug, question_number):
    """
    JSON endpoint: checks the user's selected answer against the database.

    Returns:
    - Whether the answer is correct
    - The correct answer
    - The full explanation content (core feature)
    - Python code if applicable
    - Practical example if applicable

    Also saves the user's progress if they are logged in.
    """
    subject = get_object_or_404(Subject, slug=slug)
    question = get_object_or_404(
        Question,
        subject=subject,
        question_number=question_number,
    )

    # --- Guest access control (server-side enforcement) ------------------
    # The free-question limit is ALWAYS enforced here, in the server, not in
    # the frontend. Guests cannot bypass it by refreshing the page (attempts
    # are stored in the session) or by navigating directly to later questions
    # (every check_answer call for a guest is guarded by this logic).
    #
    # IMPORTANT: a blocked guest does NOT receive the correct answer or the
    # explanation — those are only shown for questions they were allowed to
    # attempt. The response here only signals that the free limit was reached.
    #
    # Future monetization: to add paid/premium tiers, extend this check via
    # core/services/access.py (e.g. access_service.can_access_question(...)).
    is_guest = not request.user.is_authenticated
    if is_guest and not access_service.can_attempt_more(request):
        return JsonResponse({
            'error': 'guest_limit_reached',
            'message': 'You have reached the free question limit. '
                       'Create a free account to continue learning.',
            'limit_reached': True,
            'guest_free_limit': get_guest_free_limit(),
        })

    selected = request.GET.get('answer', '')
    is_correct = selected.upper() == question.correct_answer

    # Build the response with all explanation content
    response_data = {
        'is_correct': is_correct,
        'correct_answer': question.correct_answer,
        'explanation': question.explanation,
        'python_code': question.python_code,
        'practical_example': question.practical_example,
        # Guests see how many free questions remain / whether limit is reached
        'limit_reached': False,
        'guest_free_limit': get_guest_free_limit(),
    }

    # Save progress if the user is logged in
    if request.user.is_authenticated:
        UserProgress.objects.update_or_create(
            user=request.user,
            question=question,
            defaults={
                'selected_answer': selected.upper(),
                'is_correct': is_correct,
            },
        )
    else:
        # Guest: record the attempt in the session ONLY (no UserProgress row,
        # no permanent database record).
        access_service.record_guest_attempt(request, question.id)

        # Tell the frontend whether this was the final free attempt so it can
        # show the registration prompt naturally after the explanation.
        response_data['guest_attempts_used'] = (
            access_service.get_guest_attempts_used(request)
        )
        response_data['guest_free_limit'] = get_guest_free_limit()
        response_data['limit_reached'] = (
            access_service.guest_limit_reached(request)
        )

    return JsonResponse(response_data)


# ============================================================================
#  AUTHENTICATION VIEWS (user registration, login, logout, profile)
# ============================================================================


def register(request):
    """
    User registration page.

    Uses Django's built-in UserCreationForm which handles:
    - Username, password, password confirmation
    - Validation and error messages

    Supports an optional 'next' query parameter so that a guest who signs up
    from the registration prompt on the learn page is returned to the page
    they were on (e.g. back to the subject they were learning).
    """
    next_url = request.POST.get('next') or request.GET.get('next') or ''

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # Return the new user to where they were, if safe, else home.
            if next_url and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect('home')
    else:
        form = UserCreationForm()

    return render(
        request,
        'registration/register.html',
        {'form': form, 'next_url': next_url},
    )


@login_required
def dashboard(request):
    """
    User dashboard: shows overall progress + subject-wise breakdown.

    Overall stats:
    - Total questions attempted
    - Correct answers
    - Wrong answers
    - Accuracy percentage

    Subject-wise table:
    - Each subject with attempted, correct, accuracy
    - A "Completed" badge if all questions are done
    """
    user = request.user
    all_progress = UserProgress.objects.filter(user=user)

    # --- Overall stats ---
    total_attempted = all_progress.count()
    total_correct = all_progress.filter(is_correct=True).count()
    total_wrong = all_progress.filter(is_correct=False).count()
    accuracy = round(
        (total_correct / total_attempted * 100) if total_attempted > 0 else 0,
        1,
    )

    # --- Subject-wise breakdown ---
    subjects = Subject.objects.all().order_by('order', 'name')
    subject_stats = []

    for subject in subjects:
        subject_progress = all_progress.filter(question__subject=subject)
        attempted = subject_progress.count()
        correct = subject_progress.filter(is_correct=True).count()
        wrong = subject_progress.filter(is_correct=False).count()
        sub_accuracy = round(
            (correct / attempted * 100) if attempted > 0 else 0,
            1,
        )
        total_questions = subject.questions.count()
        all_done = attempted >= total_questions and total_questions > 0

        subject_stats.append({
            'subject': subject,
            'attempted': attempted,
            'correct': correct,
            'wrong': wrong,
            'accuracy': sub_accuracy,
            'total': total_questions,
            'all_done': all_done,
        })

# --- Project-wise breakdown ---
    projects = Project.objects.filter(is_active=True).order_by('order', 'title')
    project_stats = []

    for project in projects:
        project_progress = all_progress.filter(question__project=project)
        attempted = project_progress.count()
        correct = project_progress.filter(is_correct=True).count()
        wrong = project_progress.filter(is_correct=False).count()
        proj_accuracy = round(
            (correct / attempted * 100) if attempted > 0 else 0,
            1,
        )
        total_questions = project.questions.count()
        all_done = attempted >= total_questions and total_questions > 0

        project_stats.append({
            'project': project,
            'attempted': attempted,
            'correct': correct,
            'wrong': wrong,
            'accuracy': proj_accuracy,
            'total': total_questions,
            'all_done': all_done,
        })

    # --- Mistakes to review (latest recorded answer is incorrect) ---
    wrong_progress = all_progress.filter(is_correct=False)
    mistake_count = wrong_progress.count()

    context = {
        'total_attempted': total_attempted,
        'total_correct': total_correct,
        'total_wrong': total_wrong,
        'accuracy': accuracy,
        'subject_stats': subject_stats,
        'project_stats': project_stats,
        'mistake_count': mistake_count,
        'has_mistakes': mistake_count > 0,
    }

    return render(request, 'core/dashboard.html', context)


# ============================================================================
#  REVIEW MISTAKES VIEWS (login required — only the current user's data)
# ============================================================================

# A "mistake" is a UserProgress row where the latest recorded answer is
# incorrect. Because check_answer uses update_or_create, answering a mistake
# correctly updates the SAME row to is_correct=True, which automatically
# removes it from the mistake list. No duplicate records are ever created.


def get_mistake_queryset(user, subject=None, project=None):
    """
    Return the current user's mistakes, optionally filtered by one subject
    or one project.

    The resulting queryset is ordered by subject/project order then
    question_number so the review flow is predictable and grouped.
    """
    qs = UserProgress.objects.filter(user=user, is_correct=False)
    if subject is not None:
        qs = qs.filter(question__subject=subject)
    if project is not None:
        qs = qs.filter(question__project=project)
    return qs.select_related('question__subject', 'question__project').order_by(
        'question__subject__order',
        'question__subject__name',
        'question__question_number',
    )


@login_required
def review_mistakes(request, subject_slug=None):
    """
    Page that lists the current user's incorrectly-answered questions.

    - Shows ALL mistakes grouped by subject by default.
    - When a subject_slug is given, shows only that subject's mistakes.
    - Each mistake links into the existing MCQ learning interface in review
      mode (review_learn), reusing the normal question rendering / checking.
    - Never exposes another user's mistakes.
    """
    user = request.user
    subject = None
    if subject_slug:
        subject = get_object_or_404(Subject, slug=subject_slug)
        mistake_qs = get_mistake_queryset(user, subject=subject)
    else:
        mistake_qs = get_mistake_queryset(user)

    mistake_count = mistake_qs.count()

# Group mistakes by subject OR project for display.
    # A question belongs to exactly one of subject/project (enforced by the
    # model's CheckConstraint), so we can safely branch on which one is set.
    grouped = {}
    for progress in mistake_qs:
        question = progress.question
        if question.project_id:
            key = ('project', question.project_id)
            title = question.project.title
            kind = 'project'
            slug = question.project.slug
        else:
            key = ('subject', question.subject_id)
            title = question.subject.name
            kind = 'subject'
            slug = question.subject.slug

        group = grouped.setdefault(key, {
            'kind': kind,
            'title': title,
            'slug': slug,
            'questions': [],
            'count': 0,
        })
        group['count'] += 1
        group['questions'].append({
            'question_number': question.question_number,
            'question_text': question.question_text,
            'question_id': question.id,
            'slug': slug,
        })

    # Sort groups: subjects first (by order/name), then projects (by order/title).
    # We keep subject/project ordering consistent by using the model's order.
    def group_sort_key(g):
        if g['kind'] == 'subject':
            return (0, g['title'].lower())
        return (1, g['title'].lower())

    content_groups = sorted(grouped.values(), key=group_sort_key)

    context = {
        'content_groups': content_groups,
        'mistake_count': mistake_count,
        'active_subject': subject,
        'is_subject_review': subject is not None,
    }
    return render(request, 'core/review_mistakes.html', context)


@login_required
def review_learn(request, subject_slug=None, project_slug=None):
    """
    Renders the EXISTING MCQ learn shell in "review mode".

    The learn.js script receives the ordered list of the user's current
    mistakes via API and drives review navigation through the standard
    question_data / check_answer endpoints. This means the normal question,
    options, feedback, explanation, Python code and practical example
    rendering are ALL reused unchanged.

    Supports filtering mistakes by a subject OR a project:
    - review/subject/<slug>/learn/  filters by subject
    - review/project/<slug>/learn/  filters by project
    """
    user = request.user
    subject = None
    project = None
    if subject_slug:
        subject = get_object_or_404(Subject, slug=subject_slug)
    if project_slug:
        project = get_object_or_404(Project, slug=project_slug, is_active=True)

    # Build the ordered mistake list, with the correct parent slug for each.
    mistake_qs = get_mistake_queryset(user, subject=subject, project=project)
    mistakes = list(
        mistake_qs.values(
            'question__id',
            'question__subject__slug',
            'question__project__slug',
            'question__question_number',
        )
    )

    mistake_list = []
    for m in mistakes:
        if m['question__project__slug']:
            # Project question → review through the project learn endpoints.
            content_slug = m['question__project__slug']
            content_type = 'project'
        else:
            # Subject question → review through the subject learn endpoints.
            content_slug = m['question__subject__slug']
            content_type = 'subject'
        mistake_list.append({
            'id': m['question__id'],
            'slug': content_slug,
            'content_type': content_type,
            'number': m['question__question_number'],
        })

    context = {
        'review_mode': True,
        'review_subject_slug': subject.slug if subject else '',
        'review_project_slug': project.slug if project else '',
        'mistake_count': len(mistake_list),
        'mistakes_json': json.dumps(mistake_list),
    }
    return render(request, 'core/learn.html', context)


@login_required
def review_questions_api(request, subject_slug=None, project_slug=None):
    """
    JSON endpoint used by learn.js in review mode.

    Returns the CURRENT ordered list of the logged-in user's mistakes, so the
    review flow always reflects the latest progress. After a mistaken question
    is answered correctly, it disappears from this list on the next call.

    Supports filtering by a subject OR a project.
    """
    user = request.user
    subject = None
    project = None
    if subject_slug:
        subject = get_object_or_404(Subject, slug=subject_slug)
    if project_slug:
        project = get_object_or_404(Project, slug=project_slug, is_active=True)

    mistake_qs = get_mistake_queryset(user, subject=subject, project=project)
    mistakes = list(
        mistake_qs.values(
            'question__id',
            'question__subject__slug',
            'question__project__slug',
            'question__question_number',
        )
    )
    mistake_list = []
    for m in mistakes:
        if m['question__project__slug']:
            content_slug = m['question__project__slug']
            content_type = 'project'
        else:
            content_slug = m['question__subject__slug']
            content_type = 'subject'
        mistake_list.append({
            'id': m['question__id'],
            'slug': content_slug,
            'content_type': content_type,
            'number': m['question__question_number'],
        })
    return JsonResponse({'mistakes': mistake_list, 'count': len(mistake_list)})


# ============================================================================
#  PROJECTS (public browsing + learn flow, mirrors the subject flow)
# ============================================================================


def projects_list(request):
    """
    Projects page: lists every active project from the database.
    Each project shows its title, short description, question count, and a
    'Start Project' / 'View Project' button.
    """
    projects = Project.objects.filter(is_active=True).order_by('order', 'title')
    return render(request, 'core/projects.html', {'projects': projects})


def project_detail(request, slug):
    """
    Project detail page: shows the project's description, question count,
    and a Start Learning button.

    For logged-in users, also computes progress within this project.
    """
    project = get_object_or_404(Project, slug=slug, is_active=True)
    total = project.questions.count()

    context = {
        'project': project,
        'question_count': total,
    }

    if request.user.is_authenticated and total > 0:
        user_progress = UserProgress.objects.filter(
            user=request.user,
            question__project=project,
        )
        completed_count = user_progress.count()
        correct_count = user_progress.filter(is_correct=True).count()
        wrong_count = user_progress.filter(is_correct=False).count()

        answered_numbers = set(
            user_progress.values_list('question__question_number', flat=True)
        )
        all_numbers = set(
            project.questions.values_list('question_number', flat=True)
        )
        unanswered = sorted(all_numbers - answered_numbers)

        context.update({
            'completed_count': completed_count,
            'correct_count': correct_count,
            'wrong_count': wrong_count,
            'all_completed': completed_count >= total,
            'continue_number': unanswered[0] if unanswered else None,
        })

    return render(request, 'core/project_detail.html', context)


@ensure_csrf_cookie
def project_learn(request, slug):
    """
    The MCQ learning page for a project (application shell).

    Mirrors the subject learn page, but the questions belong to the project.
    The learn.html template is shared; the template must know this is a
    project so the JS builds the correct API URLs.
    """
    project = get_object_or_404(Project, slug=slug, is_active=True)
    total = project.questions.count()

    context = {
        'project': project,
        'total': total,
        'no_questions': total == 0,
        'contentType': 'project',
        'is_guest': not request.user.is_authenticated,
        'guest_free_limit': get_guest_free_limit(),
        'guest_attempts_used': access_service.get_guest_attempts_used(request),
        'guest_limit_reached': access_service.guest_limit_reached(request),
    }

    if total > 0:
        if request.user.is_authenticated:
            answered_numbers = set(
                UserProgress.objects.filter(
                    user=request.user,
                    question__project=project,
                ).values_list('question__question_number', flat=True)
            )
            all_numbers = set(
                project.questions.values_list('question_number', flat=True)
            )
            unanswered = sorted(all_numbers - answered_numbers)

            if unanswered:
                context['first_number'] = unanswered[0]
            else:
                first = project.questions.order_by('question_number').first()
                context['first_number'] = first.question_number
        else:
            first = project.questions.order_by('question_number').first()
            context['first_number'] = first.question_number

    return render(request, 'core/learn.html', context)


def project_question_data(request, slug, question_number):
    """
    JSON endpoint: returns one project question (WITHOUT the correct answer).
    Mirrors question_data for subjects.
    """
    project = get_object_or_404(Project, slug=slug, is_active=True)
    question = get_object_or_404(
        Question,
        project=project,
        question_number=question_number,
    )

    options = {
        'A': question.option_a,
        'B': question.option_b,
        'C': question.option_c,
        'D': question.option_d,
    }

    previous_answer = None
    previous_is_correct = None
    if request.user.is_authenticated:
        try:
            progress = UserProgress.objects.get(
                user=request.user,
                question=question,
            )
            previous_answer = progress.selected_answer
            previous_is_correct = progress.is_correct
        except UserProgress.DoesNotExist:
            pass

    return JsonResponse({
        'question_number': question.question_number,
        'question_text': question.question_text,
        'options': options,
        'total': project.questions.count(),
        'previous_answer': previous_answer,
        'previous_is_correct': previous_is_correct,
    })


def project_check_answer(request, slug, question_number):
    """
    JSON endpoint: checks the user's answer for a project question.
    Mirrors check_answer for subjects, including guest limits and progress.
    """
    project = get_object_or_404(Project, slug=slug, is_active=True)
    question = get_object_or_404(
        Question,
        project=project,
        question_number=question_number,
    )

    is_guest = not request.user.is_authenticated
    if is_guest and not access_service.can_attempt_more(request):
        return JsonResponse({
            'error': 'guest_limit_reached',
            'message': 'You have reached the free question limit. '
                       'Create a free account to continue learning.',
            'limit_reached': True,
            'guest_free_limit': get_guest_free_limit(),
        })

    selected = request.GET.get('answer', '')
    is_correct = selected.upper() == question.correct_answer

    response_data = {
        'is_correct': is_correct,
        'correct_answer': question.correct_answer,
        'explanation': question.explanation,
        'python_code': question.python_code,
        'practical_example': question.practical_example,
        'limit_reached': False,
        'guest_free_limit': get_guest_free_limit(),
    }

    if request.user.is_authenticated:
        UserProgress.objects.update_or_create(
            user=request.user,
            question=question,
            defaults={
                'selected_answer': selected.upper(),
                'is_correct': is_correct,
            },
        )
    else:
        access_service.record_guest_attempt(request, question.id)
        response_data['guest_attempts_used'] = (
            access_service.get_guest_attempts_used(request)
        )
        response_data['guest_free_limit'] = get_guest_free_limit()
        response_data['limit_reached'] = (
            access_service.guest_limit_reached(request)
        )

    return JsonResponse(response_data)


def project_complete(request, slug):
    """
    Project completion page: shows the full project write-up (code, output,
    explanation, learning outcomes, dataset info) after the MCQs are done.
    """
    project = get_object_or_404(Project, slug=slug, is_active=True)
    return render(request, 'core/project_complete.html', {'project': project})


# ============================================================================
#  CODING EXERCISES (user-facing flow)
# ============================================================================
#
# These views integrate Coding Exercises into the existing lesson flow:
#     Subject → (MCQs) → Coding Exercises → Next Exercise
#
# They are server-rendered pages (simpler and beginner-friendly) that show
# every section of a coding exercise. Logged-in users can mark exercises
# complete, which is stored in CodingProgress so they can "continue where
# they left off" and see progress on the dashboard.


def coding_lesson_detail(request, lesson_slug):
    """
    Coding lesson landing page: shows the lesson topic, module, the list of
    coding exercises with per-user completion status, and a "Continue" /
    "Start" button that jumps to the first incomplete exercise.
    """
    lesson = get_object_or_404(CodingLesson, lesson_slug=lesson_slug)
    exercises = list(
        lesson.exercises.all().order_by('exercise_number')
    )

    context = {
        'lesson': lesson,
        'exercises': exercises,
    }

    # Per-user progress so we can show checkmarks and a continue button.
    if request.user.is_authenticated and exercises:
        completed_ids = set(
            CodingProgress.objects.filter(
                user=request.user,
                exercise__lesson=lesson,
                is_completed=True,
            ).values_list('exercise_id', flat=True)
        )
        for ex in exercises:
            ex.is_done = ex.id in completed_ids
        # First incomplete exercise = "continue where you left off".
        first_incomplete = next(
            (ex for ex in exercises if not ex.is_done), None
        )
        context['continue_exercise'] = first_incomplete
        context['all_completed'] = first_incomplete is None
        context['completed_count'] = len(completed_ids)
    else:
        context['all_completed'] = False
        context['completed_count'] = 0

    return render(request, 'core/coding_lesson_detail.html', context)


def coding_exercise_detail(request, lesson_slug, exercise_number):
    """
    A single coding exercise page.

    Shows every required section:
      Title, Difficulty, Objective, ML Connection, Dataset Preview,
      Problem Statement, Starter Code, Code Editor/Answer Area, Hints,
      Show Solution, Expected Output, Explanation, Common Mistakes,
      Next Exercise.
    """
    lesson = get_object_or_404(CodingLesson, lesson_slug=lesson_slug)
    exercise = get_object_or_404(
        CodingExercise,
        lesson=lesson,
        exercise_number=exercise_number,
    )

    # Ordered list of exercise numbers so we can build Next/Prev navigation
    # and a "continue" target.
    all_numbers = list(
        lesson.exercises.order_by('exercise_number')
        .values_list('exercise_number', flat=True)
    )
    idx = all_numbers.index(exercise.exercise_number)
    next_number = all_numbers[idx + 1] if idx + 1 < len(all_numbers) else None
    prev_number = all_numbers[idx - 1] if idx > 0 else None

    context = {
        'lesson': lesson,
        'exercise': exercise,
        'next_number': next_number,
        'prev_number': prev_number,
        'exercise_index': idx + 1,
        'exercise_total': len(all_numbers),
    }

    # Mark completion status for this exercise / whether the lesson is done.
    if request.user.is_authenticated:
        is_completed = CodingProgress.objects.filter(
            user=request.user,
            exercise=exercise,
            is_completed=True,
        ).exists()
        context['is_completed'] = is_completed
    else:
        context['is_completed'] = False

    return render(request, 'core/coding_exercise_detail.html', context)


def coding_mark_complete(request, exercise_id):
    """
    POST-only: mark a coding exercise as complete for the logged-in user.
    Redirects to the next exercise (or the lesson page if this was last).
    """
    if request.method != 'POST':
        return redirect('home')

    exercise = get_object_or_404(CodingExercise, id=exercise_id)
    lesson = exercise.lesson

    if request.user.is_authenticated:
        CodingProgress.objects.update_or_create(
            user=request.user,
            exercise=exercise,
            defaults={'is_completed': True},
        )

    # Determine the next exercise number to continue.
    all_numbers = list(
        lesson.exercises.order_by('exercise_number')
        .values_list('exercise_number', flat=True)
    )
    idx = all_numbers.index(exercise.exercise_number)
    next_number = all_numbers[idx + 1] if idx + 1 < len(all_numbers) else None

    if next_number is not None:
        return redirect(
            'coding_exercise_detail',
            lesson_slug=lesson.lesson_slug,
            exercise_number=next_number,
        )
    # Last exercise → back to the lesson page (shown as complete).
    return redirect('coding_lesson_detail', lesson_slug=lesson.lesson_slug)
