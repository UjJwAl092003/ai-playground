/**
 * test_markdown.js — Unit tests for static/js/markdown.js
 *
 * Run with:  node scripts/test_markdown.js
 *
 * Covers:
 *   - The exact multi-line ```python code block from the bug report
 *   - Inline code spans stay readable
 *   - XSS attempts are escaped (no raw HTML / script injection)
 *   - Normal question text renders normally
 *   - Bold / italic
 */

'use strict';

const assert = require('assert');
const renderMarkdown = require('../static/js/markdown.js');

let passed = 0;
let failed = 0;

// Build entity strings at runtime so this source file never contains a
// literal ampersand-entity sequence (which can be HTML-decoded on save).
const AMP = String.fromCharCode(38);     // &
const LT_ENT = AMP + 'lt;';              // <
const GT_ENT = AMP + 'gt;';              // >

function test(name, fn) {
    try {
        fn();
        passed++;
        console.log('  OK  ' + name);
    } catch (err) {
        failed++;
        console.error('  FAIL  ' + name);
        console.error('        ' + err.message);
    }
}

console.log('');
console.log('markdown.js renderer tests');
console.log('');

// ------------------------------------------------------------------------
// 1. The exact bug-report example: a multi-line ```python code block.
// ------------------------------------------------------------------------
test('renders a multi-line ```python code block as <pre><code>', function () {
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

    const html = renderMarkdown(input);

    // Must contain a code block with the python language class.
    assert.ok(
        html.indexOf('<pre><code class="language-python">') !== -1,
        'expected a <pre><code class="language-python"> block'
    );

    // The code content must be multi-line (newlines preserved inside <pre>).
    assert.ok(
        html.indexOf('import pandas as pd\n') !== -1,
        'code lines must be separated by real newlines'
    );
    assert.ok(
        html.indexOf('pd.DataFrame({f') !== -1,
        'code content must be preserved'
    );
    assert.ok(
        html.indexOf('for i in range(15)})') !== -1,
        'code content must be preserved (end of line)'
    );

    // The surrounding text must still be present as paragraphs.
    assert.ok(html.indexOf('<p>What does this print?</p>') !== -1);
    assert.ok(html.indexOf('<p>What happens?</p>') !== -1);

    // Backticks must NOT appear literally in the output.
    assert.ok(
        html.indexOf('```') === -1,
        'no stray triple backticks should remain'
    );
});

// ------------------------------------------------------------------------
// 2. Inline code remains readable (no bold/italic corruption inside code).
// ------------------------------------------------------------------------
test('inline `code` renders as <code> and stays readable', function () {
    const html = renderMarkdown('Use `pd.DataFrame()` to create a frame.');
    assert.ok(html.indexOf('<code>pd.DataFrame()</code>') !== -1);
    assert.ok(
        html.indexOf('<p>Use <code>pd.DataFrame()</code> to create a frame.</p>') !== -1
    );
});

// ------------------------------------------------------------------------
// 3. XSS safety — no raw HTML / script injection survives.
// ------------------------------------------------------------------------
test('XSS: script tag is escaped', function () {
    const html = renderMarkdown('<script>alert(1)</script>');
    const rawScript = '<script>';
    // The raw tag must NOT appear; its escaped form must appear instead.
    assert.ok(html.indexOf(rawScript) === -1, 'raw script tag must not appear');
    const escapedTag = LT_ENT + 'script' + GT_ENT;
    assert.ok(html.indexOf(escapedTag) !== -1, 'escaped form must be present');
});

test('XSS: onerror attribute is escaped', function () {
    const html = renderMarkdown('<img src=x onerror=alert(1)>');
    const rawImg = '<img';
    assert.ok(html.indexOf(rawImg) === -1, 'raw img tag must not appear');
    assert.ok(html.indexOf('img') !== -1, 'text still present');
});

test('XSS: javascript URL is not rendered as a link', function () {
    // The renderer has no link support, so this stays plain escaped text.
    const html = renderMarkdown('[click](javascript:alert(1))');
    const anchorTag = '<a ';
    assert.ok(html.indexOf(anchorTag) === -1, 'no anchor tag should be emitted');
    assert.ok(html.indexOf('javascript:alert(1)') !== -1, 'text is preserved');
});

test('XSS: markup inside code block is not interpreted', function () {
    const html = renderMarkdown(
        '```python\nprint("<script>alert(1)</script>")\n```'
    );
    const rawScript = '<script>';
    assert.ok(html.indexOf(rawScript) === -1, 'no raw script tag');
    const escapedTag = LT_ENT + 'script' + GT_ENT;
    assert.ok(
        html.indexOf(escapedTag) !== -1,
        'code content stays escaped inside the block'
    );
});

// ------------------------------------------------------------------------
// 4. Normal question text renders normally.
// ------------------------------------------------------------------------
test('normal paragraph text renders as a <p>', function () {
    const html = renderMarkdown('Which of the following is a DataFrame method?');
    assert.ok(
        html.indexOf('<p>Which of the following is a DataFrame method?</p>') !== -1
    );
});

test('multiple paragraphs are separated', function () {
    const html = renderMarkdown('First paragraph.\n\nSecond paragraph.');
    assert.ok(html.indexOf('<p>First paragraph.</p>') !== -1);
    assert.ok(html.indexOf('<p>Second paragraph.</p>') !== -1);
});

test('single newline becomes <br> inside a paragraph', function () {
    const html = renderMarkdown('Line one\nLine two');
    assert.ok(html.indexOf('<p>Line one<br>Line two</p>') !== -1);
});

// ------------------------------------------------------------------------
// 5. Bold / italic.
// ------------------------------------------------------------------------
test('**bold** renders as <strong>', function () {
    const html = renderMarkdown('This is **important**.');
    assert.ok(html.indexOf('<strong>important</strong>') !== -1);
});

test('*italic* renders as <em>', function () {
    const html = renderMarkdown('This is *emphasised*.');
    assert.ok(html.indexOf('<em>emphasised</em>') !== -1);
});

// ------------------------------------------------------------------------
// Summary
// ------------------------------------------------------------------------
console.log('');
console.log(passed + ' passed, ' + failed + ' failed');
console.log('');
process.exit(failed === 0 ? 0 : 1);

