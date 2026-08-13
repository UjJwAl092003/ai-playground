"""One-off: append the CodingProgress model to core/models.py."""

f = 'core/models.py'
s = open(f, encoding='utf-8').read()

marker = "        return f'{self.lesson.module} — Ex{self.exercise_number}: {self.title[:40]}'"

if 'class CodingProgress' in s:
    print('CodingProgress already present; skipping.')
else:
    addition = marker + """


class CodingProgress(models.Model):
    \"\"\"
    Tracks a user's completion of a single coding exercise.

    Each (user, exercise) pair appears at most once. When a user marks an
    exercise complete, an update_or_create writes/updates the row so we can
    track "continue where you left off" and dashboard progress.

    Future flexibility: this model can be extended with fields like
    attempts_count, time_taken, bookmarked, etc. without breaking existing
    code.
    \"\"\"
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
"""

    s = s.replace(marker, addition)
    open(f, 'w', encoding='utf-8').write(s)
    print('ADDED CodingProgress model')

import py_compile
py_compile.compile(f, doraise=True)
print('COMPILE OK')
