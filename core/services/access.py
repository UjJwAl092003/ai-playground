"""
Centralized access control service.

This module is the single place where "what can this user access?" questions
are answered. It keeps ALL content-access logic in one file so that future
monetization (free vs registered vs premium vs purchased content) can be added
here WITHOUT rebuilding the rest of the application.

Currently implemented:
- Guest (anonymous) free-question limit tracking.

The limit is stored in the Django session so it:
- survives page refreshes (prevents refresh-bypass),
- is server-side only (cannot be bypassed by hiding buttons in JS),
- never writes UserProgress rows for guests.

Future-ready design:
- Access tiers are checked through small, focused functions (see below).
- To add "Premium" content later, add a field to the Question model
  (e.g. `access_tier`) and a function here like `can_access_question(user,
  question)`. The learn/check views would call it in exactly the same way
  they call `get_guest_attempts` / `can_attempt_more` today.
"""

from django.conf import settings

# Session keys (namespaced to avoid collisions with future session data).
_SESSION_ATTEMPTS_KEY = 'guest_attempted_question_ids'


# ---------------------------------------------------------------------------
# Guest attempt tracking
# ---------------------------------------------------------------------------

def get_guest_attempts(request):
    """
    Return the list of question IDs this guest has already attempted.

    Works ONLY for anonymous (guest) users. Authenticated users do not use
    session tracking — their progress is stored in UserProgress instead.
    """
    if request.user.is_authenticated:
        return []
    return request.session.get(_SESSION_ATTEMPTS_KEY, [])


def get_guest_attempts_used(request):
    """Return how many of the free guest attempts have been used."""
    return len(get_guest_attempts(request))


def get_guest_free_limit():
    """
    Return the configured guest free-question limit.

    Reads GUEST_FREE_QUESTION_LIMIT from settings so the number can be changed
    in ONE place (settings.py) without touching any other code.
    """
    return getattr(settings, 'GUEST_FREE_QUESTION_LIMIT', 5)


def can_attempt_more(request):
    """
    Return True if this request may attempt another question.

    - Authenticated users: always True (no guest limit).
    - Guests: True until they have used their free question limit.
    """
    if request.user.is_authenticated:
        return True
    used = get_guest_attempts_used(request)
    return used < get_guest_free_limit()


def record_guest_attempt(request, question_id):
    """
    Record that a guest attempted a question.

    Only stores the question ID in the session (no database writes, no
    UserProgress row). Duplicate attempts are de-duplicated so re-answering
    the same question does not consume extra free questions.
    """
    if request.user.is_authenticated:
        # Authenticated users use UserProgress, not session tracking.
        return

    attempted = set(request.session.get(_SESSION_ATTEMPTS_KEY, []))
    attempted.add(question_id)
    request.session[_SESSION_ATTEMPTS_KEY] = sorted(attempted)


def guest_limit_reached(request):
    """
    Return True when a guest has reached (but NOT exceeded) the free limit.

    Used by the frontend to decide whether to show the registration prompt.
    """
    if request.user.is_authenticated:
        return False
    return get_guest_attempts_used(request) >= get_guest_free_limit()

