"""
Tests for the "Guest Experience" feature.

The guest experience lets anonymous users try a limited number of free
questions before being invited to create an account. This is enforced
SERVER-SIDE (in the session), so it cannot be bypassed by refreshing the
page or by hiding buttons in the browser.

These tests verify:

1. Guests can learn the first few questions without an account.
2. The guest free-question limit is enforced in the session.
3. A guest cannot bypass the limit by refreshing the page.
4. A guest cannot bypass the limit by navigating to a specific question.
5. A blocked guest does NOT receive the correct answer or explanation.
6. Guest attempts are NOT saved to UserProgress (no permanent record).
7. Registering with a 'next' parameter returns the user to the learn page.
8. The learn page passes the guest config to the frontend.
9. Authenticated users have NO guest limit (unlimited access).
10. The registration prompt route is reachable from the learn page.

Run with:
    venv\\Scripts\\python manage.py test core.tests_guest
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Question, Subject, UserProgress
from core.services import access as access_service
from core.services.access import get_guest_free_limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_subject(name, slug, order=0):
    """Create a subject with a deterministic order."""
    subject, _ = Subject.objects.get_or_create(
        name=name,
        defaults={'slug': slug, 'order': order},
    )
    if subject.slug != slug:
        subject.slug = slug
    if subject.order != order:
        subject.order = order
    subject.save()
    return subject


def create_question(subject, number, correct='A'):
    """Create a simple question with four options."""
    return Question.objects.create(
        subject=subject,
        question_number=number,
        question_text=f'Question {number} for {subject.name}?',
        option_a='Option A',
        option_b='Option B',
        option_c='Option C',
        option_d='Option D',
        correct_answer=correct,
        explanation='Explanation text.',
        python_code='print("hi")',
        practical_example='Example text.',
    )


class GuestBaseTest(TestCase):
    """Shared setup: a subject with several questions, NOT logged in."""

    def setUp(self):
        self.pandas = create_subject('Pandas', 'pandas', order=1)
        self.q1 = create_question(self.pandas, 1)
        self.q2 = create_question(self.pandas, 2)
        self.q3 = create_question(self.pandas, 3)
        self.q4 = create_question(self.pandas, 4)
        self.q5 = create_question(self.pandas, 5)
        self.q6 = create_question(self.pandas, 6)
        self.q7 = create_question(self.pandas, 7)
        self.q8 = create_question(self.pandas, 8)
        # Ensure we are anonymous (guest) unless a test logs in.
        self.client.logout()


# ---------------------------------------------------------------------------
# 1. Guests can learn the first few questions without an account
# ---------------------------------------------------------------------------

class GuestCanLearnTests(GuestBaseTest):

    def test_guest_can_view_learn_page(self):
        response = self.client.get(reverse('learn', args=['pandas']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pandas')
        # The page must tell the frontend this user is a guest.
        self.assertContains(response, 'isGuest: true')

    def test_guest_can_view_question_data(self):
        response = self.client.get(
            reverse('question_data', args=['pandas', 1])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['question_number'], 1)
        # Correct answer must not be exposed in the data endpoint.
        self.assertNotIn('correct_answer', data)

    def test_guest_can_check_answer_before_limit(self):
        response = self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_correct'])
        self.assertEqual(data['correct_answer'], 'A')
        # A guest below the limit gets the full explanation content.
        self.assertEqual(data['explanation'], 'Explanation text.')
        self.assertIn('python_code', data)
        self.assertIn('practical_example', data)
        self.assertFalse(data['limit_reached'])


# ---------------------------------------------------------------------------
# 2. The guest free-question limit is enforced in the session
# 3. Cannot bypass by refreshing
# ---------------------------------------------------------------------------

class GuestLimitTests(GuestBaseTest):

    def test_guest_limit_is_enforced(self):
        limit = get_guest_free_limit()

        # The first `limit - 1` free questions do NOT trip the limit.
        for number in range(1, limit):
            response = self.client.get(
                reverse('check_answer', args=['pandas', number]),
                {'answer': 'A'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['limit_reached'])

        # Answering the FINAL free question uses up the last attempt, so the
        # "limit reached" flag turns on (the frontend then shows the prompt
        # after this explanation instead of a Next button).
        response = self.client.get(
            reverse('check_answer', args=['pandas', limit]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['limit_reached'])

        # The NEXT question is blocked because the limit is reached.
        response = self.client.get(
            reverse('check_answer', args=['pandas', limit + 1]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['error'], 'guest_limit_reached')
        self.assertTrue(data['limit_reached'])

    def test_guest_limit_survives_refresh(self):
        limit = get_guest_free_limit()
        for number in range(1, limit + 1):
            self.client.get(
                reverse('check_answer', args=['pandas', number]),
                {'answer': 'A'},
            )

        # Simulate a page refresh: the session is preserved, so the limit
        # is still enforced. Navigating to a new question is blocked.
        response = self.client.get(
            reverse('check_answer', args=['pandas', limit + 1]),
            {'answer': 'A'},
        )
        self.assertEqual(response.json()['error'], 'guest_limit_reached')


# ---------------------------------------------------------------------------
# 4. Cannot bypass by navigating directly to a specific question
# ---------------------------------------------------------------------------

class GuestBypassTests(GuestBaseTest):

    def test_guest_cannot_skip_ahead_of_limit(self):
        limit = get_guest_free_limit()
        # Use up every free attempt by answering the first `limit` questions.
        for number in range(1, limit + 1):
            self.client.get(
                reverse('check_answer', args=['pandas', number]),
                {'answer': 'A'},
            )

        # Now the limit is reached. The guest tries to jump directly to a
        # question they never saw (Q6) — this is still blocked server-side.
        response = self.client.get(
            reverse('check_answer', args=['pandas', self.q6.question_number]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['error'], 'guest_limit_reached')
        self.assertTrue(data['limit_reached'])


# ---------------------------------------------------------------------------
# 5. A blocked guest does NOT receive the correct answer or explanation
# ---------------------------------------------------------------------------

class GuestBlockedContentTests(GuestBaseTest):

    def test_blocked_guest_gets_no_answer_or_explanation(self):
        limit = get_guest_free_limit()
        for number in range(1, limit + 1):
            self.client.get(
                reverse('check_answer', args=['pandas', number]),
                {'answer': 'A'},
            )

        response = self.client.get(
            reverse('check_answer', args=['pandas', limit + 1]),
            {'answer': 'A'},
        )
        data = response.json()
        self.assertEqual(data['error'], 'guest_limit_reached')
        # The correct answer and explanation must NOT be leaked.
        self.assertNotIn('correct_answer', data)
        self.assertNotIn('explanation', data)
        self.assertNotIn('python_code', data)
        self.assertNotIn('practical_example', data)


# ---------------------------------------------------------------------------
# 6. Guest attempts are NOT saved to UserProgress (no permanent record)
# ---------------------------------------------------------------------------

class GuestNoPersistenceTests(GuestBaseTest):

    def test_guest_attempts_do_not_create_progress(self):
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.client.get(
            reverse('check_answer', args=['pandas', 2]),
            {'answer': 'B'},
        )
        # No UserProgress rows exist for the guest.
        self.assertEqual(UserProgress.objects.count(), 0)

    def test_guest_attempts_stored_in_session_only(self):
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.client.get(
            reverse('check_answer', args=['pandas', 2]),
            {'answer': 'B'},
        )
        # The session tracks the guest's attempts (2 unique question IDs).
        session = self.client.session
        self.assertEqual(len(session['guest_attempted_question_ids']), 2)

    def test_duplicate_guest_attempt_counts_once(self):
        # Re-answering the same question must not consume extra free attempts.
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'B'},
        )
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'C'},
        )
        # Only one unique question ID is stored, so it counts once.
        session = self.client.session
        self.assertEqual(len(session['guest_attempted_question_ids']), 1)


# ---------------------------------------------------------------------------
# 7. Registering with a 'next' parameter returns to the learn page
# ---------------------------------------------------------------------------

class GuestRegisterReturnTests(GuestBaseTest):

    def test_register_with_next_returns_to_learn_page(self):
        next_url = reverse('learn', args=['pandas'])
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'complex-password-123',
                'password2': 'complex-password-123',
                'next': next_url,
            },
        )
        # After successful registration, redirect to the 'next' page.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

    def test_register_without_next_goes_home(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser2',
                'password1': 'complex-password-123',
                'password2': 'complex-password-123',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))


# ---------------------------------------------------------------------------
# 8. The learn page passes guest config to the frontend
# ---------------------------------------------------------------------------

class GuestConfigTests(GuestBaseTest):

    def test_learn_page_contains_guest_config(self):
        response = self.client.get(reverse('learn', args=['pandas']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'isGuest: true')
        self.assertContains(response, 'guestFreeLimit:')
        self.assertContains(response, 'guestAttemptsUsed:')
        self.assertContains(response, 'guestLimitReached:')

    def test_learn_page_shows_attempts_used(self):
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        response = self.client.get(reverse('learn', args=['pandas']))
        self.assertContains(response, 'guestAttemptsUsed: 1')


# ---------------------------------------------------------------------------
# 9. Authenticated users have NO guest limit (unlimited access)
# ---------------------------------------------------------------------------

class AuthenticatedNoLimitTests(GuestBaseTest):

    def test_logged_in_user_has_no_guest_limit(self):
        user = User.objects.create_user(
            username='alice', password='secret123'
        )
        self.client.force_login(user)

        # Even beyond the guest limit, an authenticated user can keep learning.
        limit = get_guest_free_limit()
        for number in range(1, limit + 3):
            response = self.client.get(
                reverse('check_answer', args=['pandas', number]),
                {'answer': 'A'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.json().get('error'), 'guest_limit_reached')
            self.assertFalse(response.json()['limit_reached'])

    def test_logged_in_user_progress_is_saved(self):
        user = User.objects.create_user(
            username='bob', password='secret123'
        )
        self.client.force_login(user)
        self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        # Authenticated users DO get a UserProgress row.
        self.assertEqual(UserProgress.objects.count(), 1)


# ---------------------------------------------------------------------------
# 10. The registration prompt route is reachable from the learn page
# ---------------------------------------------------------------------------

class RegistrationPromptRouteTests(GuestBaseTest):

    def test_register_page_accepts_next_query(self):
        response = self.client.get(
            reverse('register'),
            {'next': '/subject/pandas/learn/'},
        )
        self.assertEqual(response.status_code, 200)
        # The hidden next field is rendered so the guest returns to learn.
        self.assertContains(response, 'name="next"')

    def test_login_page_accepts_next_query(self):
        response = self.client.get(
            reverse('login'),
            {'next': '/subject/pandas/learn/'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next"')
