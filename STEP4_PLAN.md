# Step 4 Plan — Authentication + User Progress Tracking

## Files to Modify (6 files)

1. **`core/models.py`** — Add `UserProgress` model
2. **`core/views.py`** — Add register, dashboard, profile views; modify `check_answer` and `learn` to handle progress
3. **`core/urls.py`** — Add new URL patterns
4. **`core/admin.py`** — Register `UserProgress` in admin
5. **`templates/base.html`** — Dynamic navbar (Login/Register vs Dashboard/Logout)
6. **`templates/core/subject_detail.html`** — Show "Continue Learning" + progress for logged-in users

## Files to Create (4 new templates)

7. **`templates/registration/login.html`** — Login page
8. **`templates/registration/register.html`** — Registration page
9. **`templates/core/dashboard.html`** — Dashboard with overall + subject-wise stats
10. **`templates/core/profile.html`** — Simple profile page

## Detailed Changes

### 1. `core/models.py` — UserProgress

```python
class UserProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='progress')
    selected_answer = models.CharField(max_length=1)
    is_correct = models.BooleanField()
    attempted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'question'], name='unique_user_question_progress')
        ]
```

- `User` from `django.contrib.auth.models`
- Unique constraint on (user, question) — `update_or_create` will be used

### 2. `core/views.py` — New views

- **`register`** — GET/POST: Show registration form, validate, create user, auto-login, redirect to dashboard
- **`dashboard`** — @login_required: Show overall stats + subject-wise stats
- **`profile`** — @login_required: Show username, email, stats

### 3. `core/views.py` — Modified views

- **`learn`** — If user is authenticated and has progress, calculate `first_number` as the next unanswered question
- **`subject_detail`** — If user is authenticated, pass progress data and a `continue_number`
- **`check_answer`** — If user is authenticated, save/update UserProgress before returning JSON response

### 4. `core/urls.py` — New routes

```
/register/              -> register
/accounts/              -> include('django.contrib.auth.urls')  (login, logout)
/dashboard/             -> dashboard
/profile/               -> profile
```

### 5. `templates/base.html` — Navbar

```
{% if user.is_authenticated %}
    Dashboard | Logout
{% else %}
    Login | Register
{% endif %}
```

### 6. `templates/core/subject_detail.html` — Continue Learning

```
{% if user.is_authenticated and completed_count > 0 %}
    <p>X / Y completed</p>
    {% if all_completed %}
        <button disabled>Completed ✓</button>
    {% else %}
        <a href=".../learn/?continue=true">Continue Learning</a>
    {% endif %}
{% else %}
    <a href=".../learn/">Start Learning</a>
{% endif %}
```

### 7. Auth URLs

Use Django's built-in `django.contrib.auth.urls` for login/logout:
- `/accounts/login/` → login
- `/accounts/logout/` → logout (POST required, auto-redirect to home)

## Security

- All auth views use Django's built-in `@login_required` decorator
- Dashboard/profile only show the logged-in user's data
- `request.user` is used to filter progress — never another user's ID
- Passwords are hashed by Django's `UserCreationForm` automatically
- CSRF protection already active
- Existing public access preserved (no auth required for browsing)

## Testing Checklist

- [ ] Register a new user
- [ ] Login
- [ ] Logout
- [ ] Attempt a question while logged in → verify progress saved
- [ ] Refresh page → verify progress persists
- [ ] Dashboard shows correct overall stats
- [ ] Dashboard shows subject-wise stats
- [ ] Continue Learning button works
- [ ] Profile page shows correct info
- [ ] Another user cannot see first user's progress
- [ ] Logged-out users can still use the public learning interface
- [ ] `python manage.py check` — no errors
