"""Rebrand page titles and remaining hardcoded platform name to 'AI Playground'.

Only updates user-facing display text. Does NOT touch URLs, models, business
logic, or functionality.
"""
import os

root = 'templates'

# Replacements: (old, new) — applied as plain substring replacements.
replacements = [
    ('— LearnAI/ML', '— AI Playground'),
    ('Thank you for using LearnAI/ML.', 'Thank you for using AI Playground.'),
]

changed = []
for r, _, fs in os.walk(root):
    for f in fs:
        if not f.endswith('.html'):
            continue
        path = os.path.join(r, f)
        with open(path, encoding='utf-8') as fh:
            content = fh.read()
        original = content
        for old, new in replacements:
            content = content.replace(old, new)
        if content != original:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(content)
            changed.append(path)

if changed:
    print('Updated:')
    for c in changed:
        print(' -', c)
else:
    print('No files changed.')
