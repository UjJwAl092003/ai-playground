"""
Seed script: populates the database with sample subjects and questions.

This script creates:
1. The 8 initial subjects (Python, NumPy, Pandas, Matplotlib, SciPy,
   Statistics, Linear Algebra, Machine Learning).
2. A few sample questions for Python to demonstrate the explanation format.

Run this script using:
    venv\Scripts\python manage.py shell < scripts\sample_questions.py

Or from the Django shell:
    exec(open('scripts/sample_questions.py').read())
"""

import django
import os
import sys

# Set up Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Subject, Question


def create_subjects():
    """Create the 8 initial subjects."""
    subjects_data = [
        ('Python', 'python', 1),
        ('NumPy', 'numpy', 2),
        ('Pandas', 'pandas', 3),
        ('Matplotlib', 'matplotlib', 4),
        ('SciPy', 'scipy', 5),
        ('Statistics', 'statistics', 6),
        ('Linear Algebra', 'linear-algebra', 7),
        ('Machine Learning', 'machine-learning', 8),
    ]

    created = 0
    for name, slug, order in subjects_data:
        _, was_created = Subject.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'order': order},
        )
        if was_created:
            created += 1
            print(f'  ✓ Created subject: {name}')
        else:
            print(f'  - Subject already exists: {name}')

    return created


def create_python_questions():
    """Create sample Python questions with rich explanations."""
    python = Subject.objects.get(slug='python')

    questions_data = [
        # =================================================================
        # Question 1
        # =================================================================
        {
            'question_number': 1,
            'question_text': 'What is the correct way to create a list in Python?',
            'option_a': 'list = (1, 2, 3)',
            'option_b': 'list = [1, 2, 3]',
            'option_c': 'list = {1, 2, 3}',
            'option_d': 'list = <1, 2, 3>',
            'correct_answer': 'B',
            'explanation': (
                'In Python, a list is an ordered, mutable collection of items. '
                'Lists are created using square brackets [] with items separated by commas.\n\n'
                'Concept:\n'
                'Python has four built-in data types for storing collections: '
                'list ([]), tuple (()), set ({}), and dict ({key: value}). '
                'A list is the most commonly used collection type because it is '
                'ordered, mutable (can be changed), and allows duplicate values.\n\n'
                'Why B is correct:\n'
                'Square brackets [1, 2, 3] correctly create a Python list containing '
                'the integers 1, 2, and 3.\n\n'
                'Why the others are incorrect:\n'
                '- A: Parentheses (1, 2, 3) create a tuple, which is immutable (cannot be changed).\n'
                '- C: Curly braces {1, 2, 3} create a set, which is unordered and does not allow duplicates.\n'
                '- D: Angle brackets are not valid Python syntax for any collection.'
            ),
            'python_code': (
                '# Creating a list in Python\n'
                'my_list = [1, 2, 3, 4, 5]\n'
                'print(my_list)  # Output: [1, 2, 3, 4, 5]\n\n'
                '# Lists can hold mixed data types\n'
                'mixed = [1, "hello", 3.14, True]\n'
                'print(mixed)  # Output: [1, \'hello\', 3.14, True]\n\n'
                '# Lists are mutable — we can change elements\n'
                'my_list[0] = 99\n'
                'print(my_list)  # Output: [99, 2, 3, 4, 5]\n\n'
                '# Common list operations\n'
                'print(len(my_list))         # Length: 5\n'
                'print(my_list[1:3])         # Slicing: [2, 3]\n'
                'my_list.append(6)           # Add element\n'
                'print(my_list)              # Output: [99, 2, 3, 4, 5, 6]'
            ),
            'practical_example': (
                'Lists are used everywhere in Python. For example, when analyzing '
                'student scores:\n\n'
                'scores = [85, 92, 78, 90, 88]\n'
                'average = sum(scores) / len(scores)\n'
                'print(f"Average score: {average}")  # Average score: 86.6\n\n'
                'You can also filter lists using list comprehensions:\n'
                'high_scores = [s for s in scores if s >= 90]\n'
                'print(high_scores)  # Output: [92, 90]'
            ),
        },

        # =================================================================
        # Question 2
        # =================================================================
        {
            'question_number': 2,
            'question_text': (
                'What will be the output of the following code?\n\n'
                'x = 10\n'
                'y = 3\n'
                'print(x // y)'
            ),
            'option_a': '3.333',
            'option_b': '3',
            'option_c': '3.0',
            'option_d': '1',
            'correct_answer': 'B',
            'explanation': (
                'In Python, the // operator performs floor division (also called '
                'integer division). It divides two numbers and rounds DOWN to the '
                'nearest integer.\n\n'
                'Concept:\n'
                'Python has two division operators:\n'
                '- /  : Float division — returns a float result\n'
                '- // : Floor division — returns an integer result (rounded down)\n\n'
                'Why B is correct:\n'
                '10 // 3 = 3 because 3 goes into 10 three times (3 * 3 = 9), '
                'and the remainder (1) is discarded. The result is an integer 3.\n\n'
                'Why the others are incorrect:\n'
                '- A: 3.333 would be the result of / (float division): 10 / 3 = 3.333...\n'
                '- C: 3.0 would be a float. // always returns an int when both operands are ints.\n'
                '- D: 1 is the remainder (10 % 3 = 1), not the quotient.'
            ),
            'python_code': (
                '# Floor division vs float division\n'
                'x = 10\n'
                'y = 3\n\n'
                'print(x // y)  # Floor division: 3\n'
                'print(x / y)   # Float division:  3.3333333333333335\n'
                'print(x % y)   # Modulo (remainder): 1\n\n'
                '# Floor division with negative numbers\n'
                'print(-10 // 3)  # Output: -4 (rounds DOWN, not toward zero)\n'
                'print(10 // -3)  # Output: -4\n\n'
                '# Floor division always returns an integer when both operands are ints\n'
                'print(type(10 // 3))  # Output: <class \'int\'>'
            ),
            'practical_example': (
                'Floor division is commonly used when you need to split items '
                'into groups. For example, if you have 47 students and each '
                'classroom can hold 20 students:\n\n'
                'students = 47\n'
                'capacity = 20\n'
                'full_classrooms = students // capacity\n'
                'remaining = students % capacity\n\n'
                'print(f"Full classrooms: {full_classrooms}")  # Output: 2\n'
                'print(f"Remaining students: {remaining}")     # Output: 7'
            ),
        },

        # =================================================================
        # Question 3
        # =================================================================
        {
            'question_number': 3,
            'question_text': (
                'What is the correct way to check if a key exists in a dictionary?'
            ),
            'option_a': 'dict.has_key("key")',
            'option_b': '"key" in dict',
            'option_c': 'dict.exists("key")',
            'option_d': 'dict.contains("key")',
            'correct_answer': 'B',
            'explanation': (
                'In Python, the correct way to check if a key exists in a dictionary '
                'is to use the "in" operator.\n\n'
                'Concept:\n'
                'Python dictionaries are key-value stores. The "in" operator checks '
                'membership in the dictionary\'s keys. This is efficient (O(1) average '
                'time complexity) because dictionaries are implemented as hash tables.\n\n'
                'Why B is correct:\n'
                '"key" in my_dict returns True if "key" exists as a key in my_dict, '
                'False otherwise. This is the Pythonic and recommended approach.\n\n'
                'Why the others are incorrect:\n'
                '- A: .has_key() was a method in Python 2 but was removed in Python 3.\n'
                '- C: .exists() is not a dictionary method in Python.\n'
                '- D: .contains() is not a dictionary method in Python.'
            ),
            'python_code': (
                '# Checking if a key exists in a dictionary\n'
                'student = {\n'
                '    "name": "Alice",\n'
                '    "age": 22,\n'
                '    "major": "Computer Science"\n'
                '}\n\n'
                '# Using "in" (Pythonic way)\n'
                'if "name" in student:\n'
                '    print(f"Name: {student[\'name\']}")\n\n'
                'if "gpa" not in student:\n'
                '    print("GPA not found")  # This will execute\n\n'
                '# Using .get() to safely access with a default value\n'
                'gpa = student.get("gpa", "Not available")\n'
                'print(f"GPA: {gpa}")  # Output: GPA: Not available\n\n'
                '# The "in" operator works on keys, not values\n'
                'print("Alice" in student)  # Output: False (checks keys, not values)'
            ),
            'practical_example': (
                'Checking key existence is essential when processing JSON API responses. '
                'For example:\n\n'
                'response = {"status": "ok", "data": {"users": [...]}}\n\n'
                'if "data" in response and "users" in response["data"]:\n'
                '    users = response["data"]["users"]\n'
                '    print(f"Found {len(users)} users")\n'
                'else:\n'
                '    print("Invalid response format")\n\n'
                'This prevents KeyError exceptions and makes your code robust.'
            ),
        },
    ]

    created = 0
    for q_data in questions_data:
        _, was_created = Question.objects.get_or_create(
            subject=python,
            question_number=q_data['question_number'],
            defaults=q_data,
        )
        if was_created:
            created += 1
            print(f'  ✓ Created Python Q{q_data["question_number"]}: {q_data["question_text"][:50]}...')
        else:
            print(f'  - Python Q{q_data["question_number"]} already exists')

    return created


def main():
    """Run the seed script."""
    print('\n' + '=' * 60)
    print('  Seeding the database with sample data...')
    print('=' * 60)

    print('\n📚 Creating subjects...')
    subjects_created = create_subjects()
    print(f'  → {subjects_created} new subject(s) created.')

    print('\n❓ Creating Python questions...')
    questions_created = create_python_questions()
    print(f'  → {questions_created} new question(s) created.')

    print('\n' + '=' * 60)
    print('  Seeding complete!')
    print('=' * 60)
    print(f'\nSubjects: {Subject.objects.count()}')
    print(f'Questions: {Question.objects.count()}')
    print('\nStart the server: venv\\Scripts\\python manage.py runserver')
    print('Visit: http://127.0.0.1:8000/')


if __name__ == '__main__':
    main()
