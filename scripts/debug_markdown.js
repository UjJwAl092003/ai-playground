'use strict';
const r = require('../static/js/markdown.js');

console.log('--- script test ---');
console.log(JSON.stringify(r('<script>alert(1)</script>')));

console.log('--- onerror test ---');
console.log(JSON.stringify(r('<img src=x onerror=alert(1)>')));

console.log('--- code block xss ---');
console.log(JSON.stringify(r('```python\nprint("<script>alert(1)</script>")\n```')));

console.log('--- fence example ---');
const input = [
    'What does this print?',
    '',
    '```python',
    'import pandas as pd',
    '',
    "wide_df = pd.DataFrame({f'col{i}': [1, 2] for i in range(15)})",
    'print(wide_df)',
    '',
    'pd.options.display.max_columns = None',
    'print(wide_df)',
    '```',
    '',
    'What happens?'
].join('\n');
console.log(JSON.stringify(r(input)));

console.log('--- inline code ---');
console.log(JSON.stringify(r('Use `pd.DataFrame()` to create a frame.')));

