"""
URL configuration for the core application.

This maps every URL path to a view function.

URL structure:
/                          → Homepage (subject list)
/subject/<slug>/           → Subject detail page
/subject/<slug>/learn/     → MCQ learning page
/subject/<slug>/data/<int>/ → JSON: question data
/subject/<slug>/check/<int>/ → JSON: check answer
/register/                 → User registration
/accounts/                 → Django's built-in auth (login/logout)
/dashboard/                → User dashboard (progress tracking)
/review/                   → Review Mistakes list (grouped by subject)
/review/subject/<slug>/    → Review Mistakes filtered to one subject
/review/learn/             → Review flow (existing MCQ interface, review mode)
/review/subject/<slug>/learn/  → Review flow for one subject
/review/api/questions/     → JSON: current mistake list for review navigation
"""

from django.urls import include, path

from . import views

urlpatterns = [
    # --- Public pages ---
    path('', views.home, name='home'),
    path(
        'subject/<slug:slug>/',
        views.subject_detail,
        name='subject_detail',
    ),
    path(
        'subject/<slug:slug>/learn/',
        views.learn,
        name='learn',
    ),

    # --- JSON data endpoints (used by the learn page JavaScript) ---
    path(
        'subject/<slug:slug>/data/<int:question_number>/',
        views.question_data,
        name='question_data',
    ),
    path(
        'subject/<slug:slug>/check/<int:question_number>/',
        views.check_answer,
        name='check_answer',
    ),

    # --- Authentication ---
    path('register/', views.register, name='register'),
    path(
        'accounts/',
        include('django.contrib.auth.urls'),
    ),

# --- Dashboard ---
    path('dashboard/', views.dashboard, name='dashboard'),

    # --- Review Mistakes (login required) ---
    path('review/', views.review_mistakes, name='review_mistakes'),
    path(
        'review/subject/<slug:subject_slug>/',
        views.review_mistakes,
        name='review_mistakes_subject',
    ),
    path('review/learn/', views.review_learn, name='review_learn'),
    path(
        'review/subject/<slug:subject_slug>/learn/',
        views.review_learn,
        name='review_learn_subject',
    ),
    path(
        'review/api/questions/',
        views.review_questions_api,
        name='review_questions_api',
    ),
path(
        'review/subject/<slug:subject_slug>/api/questions/',
        views.review_questions_api,
        name='review_questions_api_subject',
    ),
    path(
        'review/project/<slug:project_slug>/learn/',
        views.review_learn,
        name='review_learn_project',
    ),
    path(
        'review/project/<slug:project_slug>/api/questions/',
        views.review_questions_api,
        name='review_questions_api_project',
    ),

    # --- Projects (public browsing + learning, mirrors the subject flow) ---
    path('projects/', views.projects_list, name='projects_list'),
    path(
        'project/<slug:slug>/',
        views.project_detail,
        name='project_detail',
    ),
    path(
        'project/<slug:slug>/learn/',
        views.project_learn,
        name='project_learn',
    ),
    path(
        'project/<slug:slug>/complete/',
        views.project_complete,
        name='project_complete',
    ),
    path(
        'project/<slug:slug>/data/<int:question_number>/',
        views.project_question_data,
        name='project_question_data',
    ),
path(
        'project/<slug:slug>/check/<int:question_number>/',
        views.project_check_answer,
        name='project_check_answer',
    ),

    # --- Coding Exercises (user-facing flow) ---
    path(
        'coding/<slug:lesson_slug>/',
        views.coding_lesson_detail,
        name='coding_lesson_detail',
    ),
    path(
        'coding/<slug:lesson_slug>/<int:exercise_number>/',
        views.coding_exercise_detail,
        name='coding_exercise_detail',
    ),
    path(
        'coding/<int:exercise_id>/complete/',
        views.coding_mark_complete,
        name='coding_mark_complete',
    ),
]
