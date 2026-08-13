"""
Tests for the "Review Mistakes" feature.

These tests verify the full review flow end-to-end:

1. Guest (anonymous) users cannot access any review page.
2. A logged-in user with no mistakes sees the empty state.
3. Wrong answers appear in Review Mistakes.
4. Correctly answered questions do NOT appear.
5. Answering a mistake correctly REMOVES it from the mistake list.
6. Answering a mistake incorrectly again KEEPS it in the list.
7. Subject-wise filtering works.
8. Review All Mistakes works (learn page review mode).
9. Existing normal MCQ learning still works.
10. Existing dashboard progress still works.
11. Existing authentication still works.
12. A user can only see their OWN mistakes, never another user's.

Run with:
    venv\\Scripts\\python manage.py test core.tests_review
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Question, Subject, UserProgress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_subject(name, slug, order=0):
    """Create a subject with a deterministic order."""
    subject, _ = Subject.objects.get_or_create(
        name=name,
        defaults={'slug': slug, 'order': order},
    )
    # Ensure slug/order are set even if the subject already existed.
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


def record_progress(user, question, answer, is_correct):
    """Create or update a UserProgress record (mirrors check_answer)."""
    return UserProgress.objects.update_or_create(
        user=user,
        question=question,
        defaults={
            'selected_answer': answer,
            'is_correct': is_correct,
        },
    )


class ReviewBaseTest(TestCase):
    """Shared setup: two subjects with questions, plus two users."""

    def setUp(self):
        self.pandas = create_subject('Pandas', 'pandas', order=1)
        self.numpy = create_subject('NumPy', 'numpy', order=2)

        self.pandas_q1 = create_question(self.pandas, 1)
        self.pandas_q2 = create_question(self.pandas, 2)
        self.pandas_q3 = create_question(self.pandas, 3)
        self.numpy_q1 = create_question(self.numpy, 1)
        self.numpy_q4 = create_question(self.numpy, 4)

        self.user = User.objects.create_user(
            username='alice', password='secret123'
        )
        self.other_user = User.objects.create_user(
            username='bob', password='secret123'
        )
        self.client.force_login(self.user)


# ---------------------------------------------------------------------------
# 1. Guest users cannot access review pages
# ---------------------------------------------------------------------------

class GuestAccessTests(ReviewBaseTest):

    def test_guest_cannot_view_review_list(self):
        self.client.logout()
        response = self.client.get(reverse('review_mistakes'))
        # login_required redirects to the login page.
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_guest_cannot_view_review_learn(self):
        self.client.logout()
        response = self.client.get(reverse('review_learn'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_guest_cannot_view_review_api(self):
        self.client.logout()
        response = self.client.get(reverse('review_questions_api'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)


# ---------------------------------------------------------------------------
# 2. Empty state (no mistakes)
# ---------------------------------------------------------------------------

class EmptyStateTests(ReviewBaseTest):

    def test_no_mistakes_shows_empty_state(self):
        # User answers everything correctly.
        record_progress(self.user, self.pandas_q1, 'A', True)
        record_progress(self.user, self.numpy_q1, 'A', True)

        response = self.client.get(reverse('review_mistakes'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no mistakes to review')

        # API also returns an empty list.
        api = self.client.get(reverse('review_questions_api'))
        self.assertEqual(api.status_code, 200)
        self.assertEqual(api.json()['count'], 0)
        self.assertEqual(api.json()['mistakes'], [])

    def test_review_learn_with_no_mistakes(self):
        response = self.client.get(reverse('review_learn'))
        self.assertEqual(response.status_code, 200)
        # The page renders in review mode with an empty mistake list.
        self.assertContains(response, 'reviewMode')


# ---------------------------------------------------------------------------
# 3. Wrong answers appear; 4. Correct answers do NOT appear
# ---------------------------------------------------------------------------

class MistakeListTests(ReviewBaseTest):

    def test_wrong_answers_appear_correct_answers_do_not(self):
        # Wrong on pandas_q1, correct on pandas_q2, wrong on numpy_q1.
        record_progress(self.user, self.pandas_q1, 'B', False)
        record_progress(self.user, self.pandas_q2, 'A', True)
        record_progress(self.user, self.numpy_q1, 'C', False)

        response = self.client.get(reverse('review_mistakes'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2')
        self.assertContains(response, 'Pandas')
        self.assertContains(response, 'NumPy')

        # The correct question must NOT be listed.
        self.assertNotContains(response, 'Question 2 for Pandas')

        # API list contains exactly the two mistakes.
        api = self.client.get(reverse('review_questions_api'))
        data = api.json()
        self.assertEqual(data['count'], 2)
        numbers = {(m['slug'], m['number']) for m in data['mistakes']}
        self.assertEqual(numbers, {('pandas', 1), ('numpy', 1)})

    def test_dashboard_shows_mistake_count(self):
        record_progress(self.user, self.pandas_q1, 'B', False)
        record_progress(self.user, self.pandas_q2, 'B', False)
        record_progress(self.user, self.numpy_q1, 'A', True)

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mistakes to Review')
        self.assertContains(response, '2')

        # Overall stats still work.
        self.assertContains(response, 'Attempted')
        self.assertContains(response, 'Correct')
        self.assertContains(response, 'Wrong')
        self.assertContains(response, 'Accuracy')


# ---------------------------------------------------------------------------
# 5. Answering a mistake correctly removes it
# 6. Answering incorrectly again keeps it
# ---------------------------------------------------------------------------

class MistakeRemovalTests(ReviewBaseTest):

    def test_correct_answer_removes_mistake(self):
        record_progress(self.user, self.pandas_q1, 'B', False)

        # Before: 1 mistake.
        self.assertEqual(
            UserProgress.objects.filter(
                user=self.user, is_correct=False
            ).count(),
            1,
        )

        # Answer correctly through the check endpoint (reuses existing flow).
        response = self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_correct'])

        # The same UserProgress row is updated — not duplicated.
        progress_rows = UserProgress.objects.filter(
            user=self.user, question=self.pandas_q1
        )
        self.assertEqual(progress_rows.count(), 1)
        self.assertTrue(progress_rows.first().is_correct)

        # Review Mistakes no longer shows it.
        response = self.client.get(reverse('review_mistakes'))
        self.assertContains(response, 'no mistakes to review')

        # API is empty.
        api = self.client.get(reverse('review_questions_api'))
        self.assertEqual(api.json()['count'], 0)

    def test_wrong_answer_again_keeps_mistake(self):
        record_progress(self.user, self.pandas_q1, 'B', False)

        # Answer incorrectly again.
        response = self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'C'},
        )
        self.assertFalse(response.json()['is_correct'])

        # Still exactly one progress row, still wrong.
        progress_rows = UserProgress.objects.filter(
            user=self.user, question=self.pandas_q1
        )
        self.assertEqual(progress_rows.count(), 1)
        self.assertFalse(progress_rows.first().is_correct)

        # Still appears in review.
        api = self.client.get(reverse('review_questions_api'))
        self.assertEqual(api.json()['count'], 1)

    def test_no_duplicate_progress_records(self):
        """Answering the same question many times must not duplicate rows."""
        for answer, correct in [('B', False), ('A', True), ('C', False)]:
            self.client.get(
                reverse('check_answer', args=['pandas', 1]),
                {'answer': answer},
            )
        self.assertEqual(
            UserProgress.objects.filter(user=self.user).count(), 1
        )


# ---------------------------------------------------------------------------
# 7. Subject-wise filtering
# ---------------------------------------------------------------------------

class SubjectFilterTests(ReviewBaseTest):

    def test_subject_filter_shows_only_that_subject(self):
        record_progress(self.user, self.pandas_q1, 'B', False)
        record_progress(self.user, self.pandas_q2, 'C', False)
        record_progress(self.user, self.numpy_q1, 'B', False)

        url = reverse('review_mistakes_subject', args=['pandas'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pandas')
        self.assertContains(response, '2')
        self.assertNotContains(response, 'NumPy')

        # Subject-specific API returns only that subject's mistakes.
        api = self.client.get(
            reverse('review_questions_api_subject', args=['pandas'])
        )
        data = api.json()
        self.assertEqual(data['count'], 2)
        self.assertTrue(all(m['slug'] == 'pandas' for m in data['mistakes']))

    def test_unknown_subject_filter_404(self):
        response = self.client.get(
            reverse('review_mistakes_subject', args=['does-not-exist'])
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# 8. Review All Mistakes (learn page review mode)
# ---------------------------------------------------------------------------

class ReviewAllTests(ReviewBaseTest):

    def test_review_learn_renders_with_mistakes(self):
        record_progress(self.user, self.pandas_q1, 'B', False)
        record_progress(self.user, self.numpy_q1, 'C', False)

        response = self.client.get(reverse('review_learn'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review Mode')
        self.assertContains(response, 'reviewMode')

        # The mistakes are passed to JS as JSON.
        self.assertContains(response, '"slug": "pandas"')
        self.assertContains(response, '"slug": "numpy"')

    def test_review_learn_subject_renders_filtered(self):
        record_progress(self.user, self.pandas_q1, 'B', False)
        record_progress(self.user, self.numpy_q1, 'C', False)

        response = self.client.get(
            reverse('review_learn_subject', args=['pandas'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review Mode')
        self.assertContains(response, '"slug": "pandas"')
        self.assertNotContains(response, '"slug": "numpy"')


# ---------------------------------------------------------------------------
# 9. Existing normal MCQ learning still works
# ---------------------------------------------------------------------------

class NormalLearningStillWorksTests(ReviewBaseTest):

    def test_learn_page_loads(self):
        response = self.client.get(reverse('learn', args=['pandas']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pandas')
        # The learn page is NOT in review mode — the JS config must say so.
        self.assertContains(response, 'reviewMode: false')
        self.assertNotContains(response, 'reviewMode: true')

    def test_question_data_endpoint(self):
        response = self.client.get(
            reverse('question_data', args=['pandas', 1])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['question_number'], 1)
        # Correct answer must not be exposed in the data endpoint.
        self.assertNotIn('correct_answer', data)

    def test_check_answer_endpoint(self):
        response = self.client.get(
            reverse('check_answer', args=['pandas', 1]),
            {'answer': 'A'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_correct'])
        self.assertEqual(data['correct_answer'], 'A')
        self.assertEqual(data['explanation'], 'Explanation text.')
        self.assertIn('python_code', data)
        self.assertIn('practical_example', data)


# ---------------------------------------------------------------------------
# 10. Dashboard progress still works
# ---------------------------------------------------------------------------

class DashboardStillWorksTests(ReviewBaseTest):

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_dashboard_overall_stats(self):
        record_progress(self.user, self.pandas_q1, 'A', True)
        record_progress(self.user, self.pandas_q2, 'B', False)
        record_progress(self.user, self.numpy_q1, 'C', False)

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Attempted')
        self.assertContains(response, 'Correct')
        self.assertContains(response, 'Wrong')
        self.assertContains(response, 'Accuracy')
        # 3 attempted, 1 correct, 2 wrong.
        self.assertContains(response, '3')
        self.assertContains(response, '1')
        self.assertContains(response, '2')
        # Mistakes to review = 2.
        self.assertContains(response, 'Mistakes to Review')


# ---------------------------------------------------------------------------
# 11. Authentication still works
# ---------------------------------------------------------------------------

class AuthStillWorksTests(ReviewBaseTest):

    def test_register_page_loads(self):
        self.client.logout()
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_login_page_loads(self):
        self.client.logout()
        response = self.client.get(
            reverse('login')
        )
        self.assertEqual(response.status_code, 200)

    def test_home_page_public(self):
        self.client.logout()
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pandas')
        self.assertContains(response, 'NumPy')


# ---------------------------------------------------------------------------
# 12. Users only see their own mistakes
# ---------------------------------------------------------------------------

class IsolationTests(ReviewBaseTest):

    def test_user_does_not_see_other_users_mistakes(self):
        # Other user has wrong answers on pandas_q1 and numpy_q1.
        record_progress(self.other_user, self.pandas_q1, 'B', False)
        record_progress(self.other_user, self.numpy_q1, 'C', False)

        # Current user has one wrong answer.
        record_progress(self.user, self.pandas_q2, 'B', False)

        response = self.client.get(reverse('review_mistakes'))
        self.assertContains(response, 'Question 2 for Pandas')
        self.assertNotContains(response, 'Question 1 for Pandas')
        self.assertNotContains(response, 'Question 1 for NumPy')

        # API only returns the current user's mistakes.
        api = self.client.get(reverse('review_questions_api'))
        data = api.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['mistakes'][0]['number'], 2)
        self.assertEqual(data['mistakes'][0]['slug'], 'pandas')

