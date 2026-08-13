/**
 * verify_explanation.js — Unit verification for the Explanation rendering fix.
 *
 * Confirms that the existing XSS-safe Markdown renderer (static/js/markdown.js)
 * correctly formats an explanation that contains:
 *   - multiple paragraphs (blank-line separated)
 *   - a Python fenced code block
 *   - **bold** text, *italic* text, and inline `code`
 *   - normal sentences before and after the code block
 *
 * Run with:  node scripts/verify_explanation.js
 */

'use strict';

const assert = require('assert');
const renderMarkdown = require('../static/js/markdown.js');

const pass = [];
const fail = [];

function test(name, fn) {
    try {
        fn();
        pass.push(name);
        console.log('  OK  ' + name);
    } catch (err) {
        fail.push(name);
        console.error('  FAIL  ' + name);
        console.error('        ' + err.message);
    }
}

console.log('');
console.log('Explanation Markdown verification');
console.log('');

// ---------------------------------------------------------------------------
// The exact style of explanation used by project MCQs: multiple paragraphs,
// a bold phrase, inline code, and a fenced ```python block in the middle.
// ---------------------------------------------------------------------------
var EXPLANATION = [
    'Concept: The nature of the target variable determines the type of ML problem.',
    '',
    'Why the correct option is correct: With exactly two possible output categories, this is a **binary classification** problem.',
    '',
    'Python Code:',
    '```python',
    'import pandas as pd',
    "titanic_data = pd.read_csv('./train.csv')",
    "print(titanic_data['Survived'].unique())",
    '# [0 1] -- only two distinct values',
    '```',
    '',
    'Practical Example: Other classic examples include *spam detection* and `fraud detection`.'
].join('\n');

test('fenced ```python block becomes a styled <pre><code> block', function () {
    var html = renderMarkdown(EXPLANATION);
    assert.ok(
        html.indexOf('<pre><code class="language-python">') !== -1,
        'expected <pre><code class="language-python">'
    );
    // No literal triple backticks may remain anywhere.
    assert.ok(html.indexOf('```') === -1, 'no stray triple backticks');
});

test('code content is preserved exactly (escaped for XSS, never altered/executed)', function () {
    var html = renderMarkdown(EXPLANATION);
    // The renderer HTML-escapes the whole input first (XSS safety), so single
    // quotes inside code become &#39; — which the browser renders back as '.
    // The code is preserved EXACTLY as written; it is never altered/executed.
    assert.ok(
        html.indexOf('import pandas as pd\n') !== -1,
        'import line preserved with newline'
    );
    assert.ok(
        html.indexOf('print(titanic_data') !== -1,
        'code is preserved (quotes are HTML-escaped for safety)'
    );
    assert.ok(
        html.indexOf('# [0 1] -- only two distinct values') !== -1,
        'comment preserved'
    );
    assert.ok(
        html.indexOf('<pre><code class="language-python">') !== -1,
        'code is inside a fenced block'
    );
});

test('paragraphs are separated into individual <p> blocks', function () {
    var html = renderMarkdown(EXPLANATION);
    assert.ok(
        html.indexOf('<p>Concept: The nature of the target variable determines the type of ML problem.</p>') !== -1
    );
    // The bold marker is FORMATTED into <strong> — that is the desired behaviour.
    assert.ok(
        html.indexOf('<p>Why the correct option is correct: With exactly two possible output categories, this is a <strong>binary classification</strong> problem.</p>') !== -1,
        'bold is formatted inside its own paragraph'
    );
    assert.ok(html.indexOf('<p>Python Code:</p>') !== -1);
    // Italic + inline code are both formatted inside the final paragraph.
    assert.ok(
        html.indexOf('<p>Practical Example: Other classic examples include <em>spam detection</em> and <code>fraud detection</code>.</p>') !== -1,
        'italic and inline code are formatted inside their paragraph'
    );
});

test('bold text is preserved (formatted by the renderer)', function () {
    var html = renderMarkdown('This is **important** text.');
    assert.ok(html.indexOf('<strong>important</strong>') !== -1, 'bold renders as <strong>');
});

test('italic text is preserved (formatted by the renderer)', function () {
    var html = renderMarkdown('This is *emphasised* text.');
    assert.ok(html.indexOf('<em>emphasised</em>') !== -1, 'italic renders as <em>');
});

test('inline code is preserved', function () {
    var html = renderMarkdown('Use `pd.read_csv()` here.');
    assert.ok(html.indexOf('<code>pd.read_csv()</code>') !== -1, 'inline code renders as <code>');
});

test('explanations already containing Markdown/blank lines keep working', function () {
    var html = renderMarkdown('First paragraph.\n\nSecond paragraph.\n\nThird paragraph.');
    assert.ok(html.indexOf('<p>First paragraph.</p>') !== -1);
    assert.ok(html.indexOf('<p>Second paragraph.</p>') !== -1);
    assert.ok(html.indexOf('<p>Third paragraph.</p>') !== -1);
});

test('single newline inside a paragraph becomes a <br>, not a paragraph break', function () {
    var html = renderMarkdown('Line one\nLine two');
    assert.ok(html.indexOf('<p>Line one<br>Line two</p>') !== -1);
});

// ---------------------------------------------------------------------------
// Security: raw HTML in an explanation must stay escaped.
// ---------------------------------------------------------------------------
test('XSS: raw HTML in an explanation is escaped', function () {
    var AMP = String.fromCharCode(38);
    var html = renderMarkdown('<script>alert(1)</script>');
    assert.ok(html.indexOf('<script>') === -1, 'no raw script tag');
    assert.ok(html.indexOf(AMP + 'lt;script' + AMP + 'gt;') !== -1, 'escaped form present');
});

console.log('');
console.log(pass.length + ' passed, ' + fail.length + ' failed');
console.log('');
process.exit(fail.length === 0 ? 0 : 1);

