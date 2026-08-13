# TODO — User-Facing Coding Exercise Flow

## Goal
Integrate Coding Exercises into the existing lesson flow:
Subject → Lesson → MCQs → Coding Exercises → Lesson Complete

## Steps
- [ ] Add nullable `subject` ForeignKey to `CodingLesson`
- [ ] Add `CodingProgress` model (user, exercise, is_completed, completed_at)
- [ ] Register `CodingProgress` in admin
- [ ] Generate + apply migration
- [ ] Add views: coding_lesson_detail, coding_exercise_detail, coding_mark_complete
- [ ] Add URLs for coding exercise pages
- [ ] Create templates: coding_lesson_detail, coding_exercise_detail
- [ ] Update subject_detail to link to coding exercises
- [ ] Update dashboard to show coding progress
- [ ] Add CSS for coding exercise page
- [ ] Add JS for hints/solution/dataset
- [ ] Write tests
- [ ] Run full test suite
