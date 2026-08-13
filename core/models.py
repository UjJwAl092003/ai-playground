"""
Database models for the learning platform.

These models define the database tables that store the platform's content.

Current tables:

1. Subject  — the broad learning areas (Python, NumPy, Pandas, ...).
2. Project  — hands-on ML/data-science projects (Titanic, House Prices, ...).
3. Question — the MCQs. Each belongs to EXACTLY ONE parent: either a Subject
              or a Project (never both, never neither).
4. UserProgress — a user's answer to a single Question (works identically
              for Subject questions and Project questions).

This design lets us add unlimited Projects from the Django Admin without any
code changes, while keeping the existing Subject system fully intact.
"""

from django.db import models


class Subject(models.Model):
    """
    A learning subject, e.g. "Python", "NumPy", "Machine Learning".

    Each subject is identified by a unique 'slug' (a URL-friendly name
    like 'python' or 'machine-learning') so we can create clean URLs later.
    The 'order' field lets us control the order subjects appear in.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Project(models.Model):
    """
    A hands-on ML/data-science project, e.g. "Titanic Survivor Prediction".

    Projects are COMPLETELY database-driven: adding a new Project through the
    Django Admin automatically makes it appear on the Projects page, its
    detail page, the dashboard, and Review Mistakes — no code changes needed.

    Content fields (all Markdown where noted):
    - ``short_description`` — one-liner shown on the project card.
    - ``description``       — Markdown introduction on the project detail page.
    - ``overview``          — Markdown project overview (shown after MCQs).
    - ``complete_code``     — Markdown; the FULL project Python code, with
                              multiline ```python blocks.
    - ``output``            — Markdown; formatted output / results, may include
                              text and/or images later.
    - ``explanation``       — Markdown; step-by-step explanation of the code.
    - ``learning_outcomes`` — Markdown; what the learner will have learned.
    - ``dataset_info``      — Markdown; optional dataset description/source.

    Monetization-ready (NOT implemented yet): ``is_free`` and ``access_type``
    let us mark a Project as free/premium/paid later without a redesign.

    IMPORTANT: uploaded Python code is stored as plain text/Markdown and is
    NEVER executed on the server.
    """

    # --- Identity --------------------------------------------------------
    title = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Title',
        help_text='The project title, e.g. "Titanic Survivor Prediction".',
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name='Slug',
        help_text='URL-friendly name, e.g. "titanic-survivor-prediction".',
    )

    # --- Card / listing --------------------------------------------------
    short_description = models.CharField(
        max_length=300,
        blank=True,
        verbose_name='Short Description',
        help_text='One or two sentences shown on the project card.',
    )
    thumbnail = models.ImageField(
        upload_to='project_thumbnails/',
        blank=True,
        null=True,
        verbose_name='Thumbnail',
        help_text='Optional image shown on the project card.',
    )

    # --- Detail / learning-journey content -------------------------------
    description = models.TextField(
        blank=True,
        verbose_name='Description',
        help_text='Markdown introduction shown on the project detail page.',
    )
    overview = models.TextField(
        blank=True,
        verbose_name='Overview',
        help_text='Markdown project overview. Shown after the MCQs are done.',
    )
    complete_code = models.TextField(
        blank=True,
        verbose_name='Complete Python Code',
        help_text='Markdown. The full project code with ```python code blocks.',
    )
    output = models.TextField(
        blank=True,
        verbose_name='Output / Results',
        help_text='Markdown. Formatted output, results, screenshots (later).',
    )
    explanation = models.TextField(
        blank=True,
        verbose_name='Explanation',
        help_text='Markdown. Step-by-step explanation of the code and approach.',
    )
    learning_outcomes = models.TextField(
        blank=True,
        verbose_name='Learning Outcomes',
        help_text='Markdown. What the learner will take away from this project.',
    )
    dataset_info = models.TextField(
        blank=True,
        verbose_name='Dataset Information',
        help_text='Markdown. Dataset description, source, and format (optional).',
    )

    # --- Ordering / visibility / monetization ----------------------------
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Order',
        help_text='Controls the order projects appear in.',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Uncheck to hide this project from the public site.',
    )
    is_free = models.BooleanField(
        default=True,
        verbose_name='Is Free',
        help_text='Future monetization: whether this project is free.',
    )
    ACCESS_FREE = 'free'
    ACCESS_PREMIUM = 'premium'
    ACCESS_PAID = 'paid'
    ACCESS_TYPE_CHOICES = [
        (ACCESS_FREE, 'Free'),
        (ACCESS_PREMIUM, 'Premium'),
        (ACCESS_PAID, 'Paid'),
    ]
    access_type = models.CharField(
        max_length=20,
        choices=ACCESS_TYPE_CHOICES,
        default=ACCESS_FREE,
        verbose_name='Access Type',
        help_text='Future monetization: free / premium / paid.',
    )

    # --- Timestamps ------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

    def __str__(self):
        return self.title

    @property
    def question_count(self):
        """Number of MCQs associated with this project."""
        return self.questions.count()


class Question(models.Model):
    """
    A single multiple-choice question.

    Each question belongs to EXACTLY ONE parent — either a Subject OR a
    Project (enforced by a database CheckConstraint). Existing Subject
    questions keep their ``subject``; new Project questions use ``project``
    with ``subject=NULL``.

    It stores the four options, the correct answer, and the detailed
    explanation content which is a core part of this platform.

    'python_code' is a dedicated multiline field for formatted Python code
    that demonstrates the concept. 'practical_example' is a separate
    multiline field for a practical example. Both may be left blank for
    questions where they are not applicable.
    """

    # --- Which parent this question belongs to ----------------------------
    # Exactly ONE of these must be set (never both, never neither).
    # Existing subject questions are unchanged: subject=<id>, project=NULL.
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Subject',
        help_text='The subject this question belongs to. Leave empty if the '
                  'question belongs to a Project.',
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Project',
        help_text='The project this question belongs to. Leave empty if the '
                  'question belongs to a Subject.',
        null=True,
        blank=True,
    )

    # --- The question itself ----------------------------------------------
    question_number = models.PositiveIntegerField(
        verbose_name='Question Number',
        help_text='The position of this question within its subject.',
    )
    question_text = models.TextField(
        verbose_name='Question Text',
        help_text='The question the learner will see.',
    )

    # --- The four options -------------------------------------------------
    option_a = models.CharField(
        max_length=500,
        verbose_name='Option A',
        help_text='The text for option A.',
    )
    option_b = models.CharField(
        max_length=500,
        verbose_name='Option B',
        help_text='The text for option B.',
    )
    option_c = models.CharField(
        max_length=500,
        verbose_name='Option C',
        help_text='The text for option C.',
    )
    option_d = models.CharField(
        max_length=500,
        verbose_name='Option D',
        help_text='The text for option D.',
    )

    # --- Correct answer (only one of the four options) --------------------
    CORRECT_ANSWER_CHOICES = [
        ('A', 'Option A'),
        ('B', 'Option B'),
        ('C', 'Option C'),
        ('D', 'Option D'),
    ]
    correct_answer = models.CharField(
        max_length=1,
        choices=CORRECT_ANSWER_CHOICES,
        verbose_name='Correct Answer',
        help_text='Select which option (A, B, C, or D) is the correct answer.',
    )

    # --- Explanation content (core feature) -------------------------------
    explanation = models.TextField(
        verbose_name='Explanation',
        help_text='Detailed explanation of the concept and why the answer is correct.',
    )
    python_code = models.TextField(
        blank=True,
        verbose_name='Python Code',
        help_text='Multiline formatted Python code demonstrating the concept (optional).',
    )
    practical_example = models.TextField(
        blank=True,
        verbose_name='Practical Example',
        help_text='A practical example that helps the learner understand the concept (optional).',
    )

    class Meta:
        ordering = ['question_number']
        constraints = [
            # A question must belong to exactly one parent: a Subject OR a
            # Project, never both and never neither.
            models.CheckConstraint(
                condition=(
                    models.Q(subject__isnull=False, project__isnull=True)
                    | models.Q(subject__isnull=True, project__isnull=False)
                ),
                name='question_belongs_to_subject_or_project',
            ),
            # A question number must be unique within its subject.
            models.UniqueConstraint(
                fields=['subject', 'question_number'],
                condition=models.Q(subject__isnull=False),
                name='unique_question_number_per_subject',
            ),
            # A question number must be unique within its project.
            models.UniqueConstraint(
                fields=['project', 'question_number'],
                condition=models.Q(project__isnull=False),
                name='unique_question_number_per_project',
            ),
        ]
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'

    def __str__(self):
        return f'Q{self.question_number}: {self.question_text[:60]}'


class UserProgress(models.Model):
    """
    Tracks a user's answer to a single question.

    Each (user, question) pair appears at most once. If a user answers a
    question again, the existing record is updated (using update_or_create)
    rather than creating a duplicate.

    Future flexibility: this model can be extended with fields like
    attempts_count, time_taken, bookmarked, etc. without breaking
    existing code.
    """
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='progress',
        verbose_name='User',
        help_text='The user who answered this question.',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='progress',
        verbose_name='Question',
        help_text='The question that was answered.',
    )
    selected_answer = models.CharField(
        max_length=1,
        verbose_name='Selected Answer',
        help_text='The option (A, B, C, or D) the user selected.',
    )
    is_correct = models.BooleanField(
        verbose_name='Is Correct',
        help_text='Whether the user selected the correct answer.',
    )
    attempted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Attempted At',
        help_text='When the user submitted this answer.',
    )

    class Meta:
        verbose_name = 'User Progress'
        verbose_name_plural = 'User Progress Records'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'question'],
                name='unique_user_question_progress',
            )
        ]
        ordering = ['user', 'question__subject', 'question__question_number']

    def __str__(self):
        q = self.question
        if q.subject is not None:
            parent = q.subject.name
        else:
            parent = q.project.title if q.project is not None else 'Unknown'
        return f'{self.user.username} → Q{q.question_number} ({parent})'


class CodingLesson(models.Model):
    """
    Represents one uploaded Coding Exercise JSON "lesson".

    This is the normalized grouping record for a single import. Each uploaded
    JSON file has a ``module``, ``topic``, and a unique ``lesson_slug``. The
    exercises that belong to this lesson link back to it via a ForeignKey, so
    module/topic/lesson information is NOT repeated on every exercise.

    Auto-numbering is scoped **per lesson**: new exercises continue from the
    highest existing ``exercise_number`` within this lesson (like MCQ
    numbering works per subject).
    """

    module = models.CharField(
        max_length=100,
        verbose_name='Module',
        help_text='The broader module, e.g. "Pandas".',
    )
    topic = models.CharField(
        max_length=200,
        verbose_name='Topic',
        help_text='The topic of this lesson, e.g. "Filtering & GroupBy".',
    )
    lesson_slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name='Lesson Slug',
        help_text='URL-friendly lesson identifier, e.g. '
                  '"pandas-filtering-sorting-groupby-aggregation".',
    )
    # Optional link to a Subject so coding exercises can be surfaced under a
    # subject's learning flow (e.g. Pandas lessons appear under the Pandas
    # subject). Nullable so existing lessons remain valid and the JSON
    # importer stays the source of truth.
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        related_name='coding_lessons',
        verbose_name='Subject',
        help_text='Optional: link this coding lesson to a subject so it '
                  'appears in that subject\'s learning flow.',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module', 'topic']
        verbose_name = 'Coding Lesson'
        verbose_name_plural = 'Coding Lessons'

    def __str__(self):
        return f'{self.module} — {self.topic}'

    @property
    def exercise_count(self):
        """Number of coding exercises in this lesson."""
        return self.exercises.count()


class CodingExercise(models.Model):
    """
    A single coding exercise belonging to a CodingLesson.

    Every field here maps directly to a key in the uploaded JSON file. The
    ``exercise_number`` must be unique within its lesson (enforced by a
    database constraint), mirroring how ``question_number`` works for MCQs.

    Markdown fields (``problem_statement``, ``starter_code``,
    ``expected_solution``, ``expected_output``, ``explanation``, ``objective``,
    ``ml_connection``) may contain multiline Markdown and are preserved
    verbatim during import.

    List fields (``dataset_preview``, ``common_mistakes``, ``hints``,
    ``concepts_covered``) are stored as JSON.

    IMPORTANT: imported code is stored as plain text/Markdown and is NEVER
    executed on the server.
    """

    # --- Which lesson this exercise belongs to ---------------------------
    lesson = models.ForeignKey(
        CodingLesson,
        on_delete=models.CASCADE,
        related_name='exercises',
        verbose_name='Lesson',
        help_text='The coding lesson this exercise belongs to.',
    )

    # --- Identity --------------------------------------------------------
    exercise_number = models.PositiveIntegerField(
        verbose_name='Exercise Number',
        help_text='The position of this exercise within its lesson.',
    )
    title = models.CharField(
        max_length=300,
        verbose_name='Title',
        help_text='A short, descriptive title for the exercise.',
    )
    difficulty = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Difficulty',
        help_text='e.g. beginner / intermediate / advanced.',
    )
    estimated_time = models.PositiveIntegerField(
        default=5,
        verbose_name='Estimated Time (minutes)',
        help_text='Approximate time to complete, in minutes.',
    )

    # --- Learning content (Markdown) -------------------------------------
    objective = models.TextField(
        blank=True,
        verbose_name='Objective',
        help_text='Markdown. What the learner should achieve.',
    )
    ml_connection = models.TextField(
        blank=True,
        verbose_name='ML Connection',
        help_text='Markdown. How this connects to machine learning (optional).',
    )

    # --- Dataset ----------------------------------------------------------
    dataset_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Dataset Name',
        help_text='Name of the dataset used (optional).',
    )
    dataset_description = models.TextField(
        blank=True,
        verbose_name='Dataset Description',
        help_text='Markdown. Description of the dataset (optional).',
    )
    dataset_preview = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Dataset Preview',
        help_text='Optional preview rows of the dataset (JSON).',
    )

    # --- The problem ------------------------------------------------------
    problem_statement = models.TextField(
        verbose_name='Problem Statement',
        help_text='Markdown. The problem the learner must solve.',
    )
    starter_code = models.TextField(
        blank=True,
        verbose_name='Starter Code',
        help_text='Markdown. Initial code the learner starts from (```python).',
    )
    expected_solution = models.TextField(
        blank=True,
        verbose_name='Expected Solution',
        help_text='Markdown. A reference solution (```python).',
    )
    expected_output = models.TextField(
        blank=True,
        verbose_name='Expected Output',
        help_text='Markdown. The expected output of a correct solution.',
    )

    # --- Explanation ------------------------------------------------------
    explanation = models.TextField(
        verbose_name='Explanation',
        help_text='Markdown. Step-by-step explanation of the solution.',
    )

    # --- Additional structured content (JSON) ----------------------------
    common_mistakes = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Common Mistakes',
        help_text='Optional list of common mistakes (JSON).',
    )
    hints = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Hints',
        help_text='Optional list of hints (JSON).',
    )
    concepts_covered = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Concepts Covered',
        help_text='Optional list of concepts covered (JSON).',
    )

    # --- Timestamps ------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['lesson', 'exercise_number']
        constraints = [
            # Exercise number must be unique within its lesson.
            models.UniqueConstraint(
                fields=['lesson', 'exercise_number'],
                name='unique_exercise_number_per_lesson',
            ),
        ]
        verbose_name = 'Coding Exercise'
        verbose_name_plural = 'Coding Exercises'

    @property
    def starter_code_plain(self):
        """
        Return the starter code with any surrounding ```python fence markers
        stripped, so it can be placed into the code editor textarea directly.
        """
        code = self.starter_code or ''
        lines = code.strip('\n').split('\n')
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        return '\n'.join(lines)

    @property
    def dataset_preview_json(self):
        """
        Return the dataset_preview list as a JSON string for the template's
        data-dataset attribute (used by coding.js to render a table).
        """
        import json
        return json.dumps(self.dataset_preview or [])

    def __str__(self):
        return f'{self.lesson.module} — Ex{self.exercise_number}: {self.title[:40]}'


class CodingProgress(models.Model):
    """
    Tracks a user's completion of a single coding exercise.

    Each (user, exercise) pair appears at most once. When a user marks an
    exercise complete, an update_or_create writes/updates the row so we can
    track "continue where you left off" and dashboard progress.

    Future flexibility: this model can be extended with fields like
    attempts_count, time_taken, bookmarked, etc. without breaking existing
    code.
    """
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='coding_progress',
        verbose_name='User',
        help_text='The user who completed this coding exercise.',
    )
    exercise = models.ForeignKey(
        CodingExercise,
        on_delete=models.CASCADE,
        related_name='progress',
        verbose_name='Exercise',
        help_text='The coding exercise that was completed.',
    )
    is_completed = models.BooleanField(
        default=True,
        verbose_name='Is Completed',
        help_text='Whether the user marked this exercise as complete.',
    )
    completed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Completed At',
        help_text='When the user completed this exercise.',
    )

    class Meta:
        verbose_name = 'Coding Progress'
        verbose_name_plural = 'Coding Progress Records'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'exercise'],
                name='unique_user_exercise_progress',
            )
        ]
        ordering = ['user', 'exercise__lesson', 'exercise__exercise_number']

    def __str__(self):
        return f'{self.user.username} → {self.exercise.lesson.module} Ex{self.exercise.exercise_number}'

