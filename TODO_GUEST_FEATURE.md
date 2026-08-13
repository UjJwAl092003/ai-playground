# Guest Experience Feature — TODO

- [x] Add `GUEST_FREE_QUESTION_LIMIT = 5` to `config/settings.py`
- [x] Create `core/services/access.py` (centralized access control)
- [x] Modify `core/views.py`:
  - [x] `check_answer`: enforce guest limit server-side (session tracking, no UserProgress for guests, `limit_reached`/`guest_limit_reached` flags)
  - [x] `learn`: pass guest config to template
  - [x] `register`: support `?next=` so guests return to the learn page after signup
- [x] Update `templates/core/learn.html` (add guest fields to LEARN_CONFIG)
- [x] Update `templates/registration/register.html` + `login.html` (hidden `next` field)
- [x] Update `static/js/learn.js` (registration prompt logic)
- [x] Update `static/css/style.css` (guest prompt styles)
- [x] Create `core/tests_guest.py` (guest flow tests)
- [x] Run `manage.py check`
- [x] Run full test suite (`manage.py test core`) — 71 tests OK
</content>

