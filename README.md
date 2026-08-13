# AI Playground

AI Playground is a hands-on learning platform for Python, data science, and artificial intelligence. It combines structured lessons with multiple-choice practice, coding exercises, and project-based learning.

The project is built with Django and is designed around a simple idea: concepts should be followed by practice and then applied in a complete project.

## What it includes

- Subject-based learning for areas such as Python, NumPy, Pandas, Matplotlib, Statistics, Linear Algebra, and Machine Learning.
- MCQs with explanations, optional Python code, and practical examples.
- User accounts with saved progress, subject-wise statistics, and mistake review.
- Coding exercises with starter code, hints, solutions, expected output, explanations, and common mistakes.
- Project-based learning with project-specific MCQs and a complete project walkthrough containing code, results, and step-by-step explanations.
- JSON-based content importers for adding batches of MCQs, projects, and coding lessons without manually entering every item.
- Automatic numbering for new batches of questions and coding exercises.
- Admin-side validation, conflict detection, and transaction-safe imports.
- Markdown rendering for educational content, including fenced Python code blocks.

## Tech stack

- Python
- Django
- SQLite for local development
- HTML/CSS
- JavaScript
- Bootstrap

## Application structure

```text
AI Playground
├── config/                 # Django project configuration
├── core/                   # Models, views, admin, services, tests
│   ├── migrations/
│   └── services/
├── static/
│   ├── css/
│   └── js/
├── templates/
│   ├── admin/
│   ├── core/
│   └── registration/
├── sample_data/            # Sample import data
├── manage.py
└── requirements.txt
```

## Learning flow

The platform is organized around three kinds of practice:

```text
Lesson
  ↓
Concepts
  ↓
MCQs
  ↓
Coding Exercises
  ↓
Projects
```

For projects, the flow is:

```text
Project
  ↓
Project MCQs
  ↓
Project completion
  ↓
Complete code + output + step-by-step explanation
```

## Content management

Content is stored in the database and can be added through the Django admin.

For larger batches, JSON importers are provided for:

- Subject MCQs
- Complete projects with their MCQs
- Coding lessons with their exercises

The import workflow validates the input, shows a preview, detects conflicts, and performs the database write as an atomic transaction. Existing content is not silently overwritten.

## Local setup

Clone the repository and open the project directory:

```bash
git clone https://github.com/UjJwAl092003/ai-playground.git
cd ai-playground
```

Create and activate a virtual environment on Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Apply migrations:

```powershell
python manage.py migrate
```

Create an admin account:

```powershell
python manage.py createsuperuser
```

Start the development server:

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Admin:

```text
http://127.0.0.1:8000/admin/
```

## Testing

Run the full Django test suite:

```powershell
python manage.py test
```

Run Django's system checks:

```powershell
python manage.py check
```

## Screenshots

Screenshots are kept outside the application code so the repository stays easy to navigate.

Suggested screenshots:

1. `docs/screenshots/home.png` — landing page
2. `docs/screenshots/mcq.png` — MCQ with explanation and Python code
3. `docs/screenshots/coding-exercise.png` — coding exercise page
4. `docs/screenshots/project.png` — project page
5. `docs/screenshots/dashboard.png` — progress dashboard
6. `docs/screenshots/admin-import.png` — JSON import preview in Django Admin

Example Markdown for the README:

```markdown
## Screenshots

### Home
![AI Playground home page](docs/screenshots/home.png)

### MCQ practice
![MCQ practice page](docs/screenshots/mcq.png)

### Coding exercise
![Coding exercise page](docs/screenshots/coding-exercise.png)

### Project learning flow
![Project page](docs/screenshots/project.png)

### Progress dashboard
![Progress dashboard](docs/screenshots/dashboard.png)

### Admin content import
![Admin import preview](docs/screenshots/admin-import.png)
```

## Design notes

The application is intentionally built around database-backed content rather than hard-coded question sets. This makes it possible to keep adding new lessons, exercises, and projects without changing the learning interface.

The project also keeps content management separate from the learner experience. Django Admin is used for content operations, while the public application focuses on learning and practice.

## Current scope

The current version focuses on the learning workflow and content-management infrastructure. It is a local Django application and is not presented as a production deployment.

## License

Add a license here if you decide to make the repository open source.
