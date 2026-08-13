"""
Django Admin configuration for the learning platform.

This is where we tell Django how to display and manage our models
in the built-in admin panel at /admin.

Key features configured below:
- Subjects: easy to add/edit/delete, listed in order.
- Projects: hands-on ML/data-science projects, fully managed from Admin.
- Questions: searchable by question text, filterable by subject or project,
  and the entry form is split into clear sections so that entering
  many questions by hand is comfortable.
- User Progress: read-only view to monitor user activity.
"""

from django.contrib import admin
from django.urls import path, reverse

from . import admin_views
from .models import (
    CodingExercise,
    CodingLesson,
    CodingProgress,
    Project,
    Subject,
    Question,
    UserProgress,
)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """Settings for how Subject rows appear and behave in the admin."""

    list_display = ('order', 'name', 'slug')
    list_display_links = ('name',)
    list_editable = ('order', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Settings for how Question rows appear and behave in the admin."""

    list_display = (
        'id',
        'parent_display',
        'question_number',
        'question_text',
        'correct_answer',
    )
    list_display_links = ('id', 'question_text')
    list_filter = ('subject', 'project', 'correct_answer')
    search_fields = ('question_text', 'explanation', 'python_code')
    ordering = ('question_number',)
    list_per_page = 25

    def parent_display(self, obj):
        """Show the parent (subject OR project) for a question."""
        if obj.subject is not None:
            return f'Subject: {obj.subject.name}'
        if obj.project is not None:
            return f'Project: {obj.project.title}'
        return '— (no parent)'
    parent_display.short_description = 'Belongs to'
    parent_display.admin_order_field = 'subject'

    # Use a custom changelist template so we can add the "Import Questions
    # from JSON" button without touching any built-in admin behavior.
    change_list_template = "admin/core/question/change_list.html"

    fieldsets = (
        ('Question Belongs To', {
            'fields': ('subject', 'project'),
            'description': 'Set EXACTLY ONE: either a Subject or a Project '
                           '(never both, never neither).',
        }),
        ('Question', {
            'fields': ('question_number', 'question_text'),
        }),
        ('Options', {
            'fields': ('option_a', 'option_b', 'option_c', 'option_d'),
            'classes': ('wide',),
        }),
        ('Correct Answer', {
            'fields': ('correct_answer',),
            'description': 'Select only one correct option (A, B, C, or D).',
        }),
        ('Explanation', {
            'fields': ('explanation',),
            'description': 'Core learning content: explain the concept clearly, why the '
                           'answer is correct, and briefly why the others are not.',
        }),
        ('Python Code', {
            'fields': ('python_code',),
            'description': 'Optional: formatted, multiline Python code that demonstrates '
                           'the concept. Leave blank if not applicable.',
        }),
        ('Practical Example', {
            'fields': ('practical_example',),
            'description': 'Optional: a practical example to help the learner. '
                           'Leave blank if not applicable.',
        }),
    )

    # ----------------------------------------------------------------------
    # JSON importer — additional admin pages.
    #
    # These routes are ADDED to the existing Question admin. The standard
    # add / change / delete question forms remain completely unchanged.
    # ----------------------------------------------------------------------
    def get_urls(self):
        """Append the JSON importer URLs to the existing Question admin."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-json/",
                self.admin_site.admin_view(admin_views.import_json_upload),
                name="core_question_import_json",
            ),
            path(
                "import-json/preview/",
                self.admin_site.admin_view(admin_views.import_json_preview),
                name="core_question_import_json_preview",
            ),
            path(
                "import-json/confirm/",
                self.admin_site.admin_view(admin_views.import_json_confirm),
                name="core_question_import_json_confirm",
            ),
            path(
                "import-json/result/",
                self.admin_site.admin_view(admin_views.import_json_result),
                name="core_question_import_json_result",
            ),
        ]
        return custom_urls + urls


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Settings for how Project rows appear and behave in the admin."""

    list_display = ('order', 'title', 'slug', 'is_active', 'is_free', 'question_count')
    list_display_links = ('title',)
    list_editable = ('order', 'is_active', 'is_free')
    search_fields = ('title', 'slug', 'short_description')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('order', 'title')
    list_per_page = 25

    # Use a custom changelist template so we can add the "Import Project
    # Questions from JSON" button without touching built-in admin behavior.
    change_list_template = "admin/core/project/change_list.html"

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'

    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'slug', 'short_description', 'thumbnail',
                       'order', 'is_active', 'is_free', 'access_type'),
        }),
        ('Overview', {
            'fields': ('overview',),
            'description': 'A short intro shown on the project detail page.',
        }),
        ('Full Description', {
            'fields': ('description',),
            'description': 'Detailed write-up of the project.',
        }),
        ('Complete Code', {
            'fields': ('complete_code',),
            'description': 'The full, working Python code for this project.',
        }),
        ('Output', {
            'fields': ('output',),
            'description': 'The expected output of running the code.',
        }),
        ('Step-by-Step Explanation', {
            'fields': ('explanation',),
            'description': 'How the project works, step by step.',
        }),
        ('Learning Outcomes', {
            'fields': ('learning_outcomes',),
            'description': 'What the learner will be able to do after this project.',
        }),
        ('Dataset Information', {
            'fields': ('dataset_info',),
            'description': 'Details about the dataset the project uses.',
        }),
    )

    # ----------------------------------------------------------------------
    # Project JSON importer.
    # ----------------------------------------------------------------------
    def get_urls(self):
        """Append the Project JSON importer URLs to the Project admin."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-json/",
                self.admin_site.admin_view(admin_views.project_import_json_upload),
                name="core_project_import_json",
            ),
            path(
                "import-json/preview/",
                self.admin_site.admin_view(admin_views.project_import_json_preview),
                name="core_project_import_json_preview",
            ),
            path(
                "import-json/confirm/",
                self.admin_site.admin_view(admin_views.project_import_json_confirm),
                name="core_project_import_json_confirm",
            ),
            path(
                "import-json/result/",
                self.admin_site.admin_view(admin_views.project_import_json_result),
                name="core_project_import_json_result",
            ),
        ]
        return custom_urls + urls


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    """Settings for how UserProgress rows appear and behave in the admin."""

    list_display = ('user', 'question', 'selected_answer', 'is_correct', 'attempted_at')
    list_filter = ('is_correct', 'question__subject', 'user')
    search_fields = ('user__username', 'question__question_text')
    ordering = ('-attempted_at',)
    list_per_page = 25

    # Progress is created by the learning flow, not manually
    readonly_fields = ('user', 'question', 'selected_answer', 'is_correct', 'attempted_at')

    def has_add_permission(self, request):
        return False


@admin.register(CodingLesson)
class CodingLessonAdmin(admin.ModelAdmin):
    """Settings for how CodingLesson rows appear and behave in the admin."""

    list_display = ('module', 'topic', 'lesson_slug', 'exercise_count')
    list_display_links = ('topic',)
    search_fields = ('module', 'topic', 'lesson_slug')
    ordering = ('module', 'topic')
    list_per_page = 25

    # Use a custom changelist template so we can add the "Import Coding
    # Exercises from JSON" button.
    change_list_template = "admin/core/codinglesson/change_list.html"

    def exercise_count(self, obj):
        return obj.exercises.count()
    exercise_count.short_description = 'Exercises'

    # ----------------------------------------------------------------------
    # JSON importer — additional admin pages for Coding Exercises.
    # ----------------------------------------------------------------------
    def get_urls(self):
        """Append the Coding Exercise importer URLs to the lesson admin."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-json/",
                self.admin_site.admin_view(admin_views.coding_lesson_import_upload),
                name="core_codinglesson_import_json",
            ),
            path(
                "import-json/preview/",
                self.admin_site.admin_view(admin_views.coding_lesson_import_preview),
                name="core_codinglesson_import_json_preview",
            ),
            path(
                "import-json/confirm/",
                self.admin_site.admin_view(admin_views.coding_lesson_import_confirm),
                name="core_codinglesson_import_json_confirm",
            ),
            path(
                "import-json/result/",
                self.admin_site.admin_view(admin_views.coding_lesson_import_result),
                name="core_codinglesson_import_json_result",
            ),
        ]
        return custom_urls + urls


@admin.register(CodingExercise)
class CodingExerciseAdmin(admin.ModelAdmin):
    """Settings for how CodingExercise rows appear and behave in the admin."""

    list_display = ('lesson', 'exercise_number', 'title', 'difficulty')
    list_display_links = ('title',)
    list_filter = ('lesson', 'difficulty')
    search_fields = ('title', 'problem_statement', 'explanation')
    ordering = ('lesson', 'exercise_number')
    list_per_page = 25

    fieldsets = (
        ('Lesson', {
            'fields': ('lesson', 'exercise_number', 'title', 'difficulty'),
        }),
        ('Learning Content', {
            'fields': ('objective', 'ml_connection', 'concepts_covered'),
        }),
        ('Dataset', {
            'fields': ('dataset_name', 'dataset_description', 'dataset_preview'),
        }),
        ('Problem', {
            'fields': ('problem_statement', 'starter_code'),
        }),
        ('Solution & Output', {
            'fields': ('expected_solution', 'expected_output'),
        }),
        ('Explanation', {
            'fields': ('explanation',),
            'description': 'Core learning content: step-by-step explanation.',
        }),
('Additional', {
            'fields': ('common_mistakes', 'hints', 'estimated_time'),
        }),
    )


@admin.register(CodingProgress)
class CodingProgressAdmin(admin.ModelAdmin):
    """Settings for how CodingProgress rows appear and behave in the admin."""

    list_display = ('user', 'exercise', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'exercise__lesson', 'user')
    search_fields = ('user__username', 'exercise__title')
    ordering = ('-completed_at',)
    list_per_page = 25

    # Progress is created by the learning flow, not manually
    readonly_fields = ('user', 'exercise', 'is_completed', 'completed_at')

    def has_add_permission(self, request):
        return False
