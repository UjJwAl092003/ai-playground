/**
 * markdown.js — A tiny, XSS-safe Markdown renderer for question text only.
 *
 * WHY THIS EXISTS
 * --------------
 * The MCQ `question_text` field may contain Markdown, including fenced
 * ```python code blocks, inline `code`, bold and italic text. Previously
 * the text was inserted via escapeHtml() alone, so triple backticks and
 * newlines were displayed literally on a single line.
 *
 * This renderer fixes THAT field only. The explanation and python_code
 * fields keep their existing dedicated rendering.
 *
 * SECURITY MODEL (important)
 * --------------------------
 * 1. The ENTIRE input is HTML-escaped FIRST. Any `<`, `>`, `&`, `"`, `'`
 *    in the user content becomes an entity, so raw HTML can never pass
 *    through to the DOM.
 * 2. Only AFTER escaping does the renderer emit a small allowlist of
 *    fixed HTML tags: <p>, <br>, <strong>, <em>, <code>, <pre>.
 * 3. Inline formatting is applied via placeholder substitution so that
 *    code spans are never processed as bold/italic markup.
 *
 * This renderer is dependency-free (vanilla JS, no build step).
 */

(function (global) {
    'use strict';

    // HTML entities written as ASCII so the file is never corrupted by
    // any layer that might decode HTML entities while saving the file.
    var ENT_LT = String.fromCharCode(38) + 'lt;';      // <
    var ENT_GT = String.fromCharCode(38) + 'gt;';      // >
    var ENT_AMP = String.fromCharCode(38) + 'amp;';    // &amp;
    var ENT_QUOT = String.fromCharCode(38) + 'quot;';  // "
    var ENT_APOS = String.fromCharCode(38) + '#39;';   // &#39;

    /**
     * Escape a string for safe insertion into HTML.
     * Escapes & < > " '  (in that order, & first so it is not double-escaped).
     */
    function escapeHtml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, ENT_AMP)
            .replace(/</g, ENT_LT)
            .replace(/>/g, ENT_GT)
            .replace(/"/g, ENT_QUOT)
            .replace(/'/g, ENT_APOS);
    }

    /**
     * Apply inline formatting (bold, italic) with code-span protection.
     * Inline code spans are first swapped for placeholder tokens so that
     * the bold/italic rules cannot alter content inside `code`.
     */
    function formatInline(text) {
        var codeSpans = [];

        // 1) Extract inline code spans and replace with placeholders.
        text = text.replace(/`([^`\n]+)`/g, function (match, code) {
            codeSpans.push(code);
            return '\u0000CODE' + (codeSpans.length - 1) + '\u0000';
        });

        // 2) Bold **text**
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // 3) Italic *text* (avoid matching the ** already consumed above).
        text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');

        // 4) Restore code spans as safe <code> elements.
        text = text.replace(/\u0000CODE(\d+)\u0000/g, function (match, idx) {
            return '<code>' + codeSpans[Number(idx)] + '</code>';
        });

        return text;
    }

    /**
     * Render Markdown text to safe HTML.
     *
     * Supported (safe subset):
     *   - Fenced code blocks:  ```lang ... ```  -> <pre><code class="language-lang">
     *   - Inline code:        `code`           -> <code>
     *   - Bold:               **text**         -> <strong>
     *   - Italic:             *text*           -> <em>
     *   - Paragraphs (blank-line separated)    -> <p>
     *   - Single newlines inside a paragraph   -> <br>
     *
     * Everything else is emitted as escaped plain text.
     */
    function renderMarkdown(rawText) {
        if (rawText == null) return '';

        // Normalise line endings so fenced blocks work with \r\n too.
        var text = String(rawText).replace(/\r\n/g, '\n').replace(/\r/g, '\n');

        // --- STEP 1: escape everything. No raw HTML can survive this. ---
        text = escapeHtml(text);

        // --- STEP 2: extract fenced code blocks -------------------------
        var lines = text.split('\n');
        var pieces = [];
        var inFence = false;
        var fenceLang = '';
        var codeLines = [];

        function flushCode() {
            if (!inFence) return;
            var code = codeLines.join('\n');
            var cls = fenceLang ? ' class="language-' + fenceLang + '"' : '';
            pieces.push('<pre><code' + cls + '>' + code + '</code></pre>');
            codeLines = [];
            inFence = false;
            fenceLang = '';
        }

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var fenceMatch = line.match(/^`{3,}\s*([A-Za-z0-9_+-]*)\s*$/);
            if (fenceMatch) {
                if (inFence) {
                    flushCode(); // closing fence
                } else {
                    flushCode(); // safety: close any stray block
                    inFence = true;
                    fenceLang = fenceMatch[1];
                    codeLines = [];
                }
            } else if (inFence) {
                codeLines.push(line);
            } else {
                pieces.push(line);
            }
        }
        flushCode();

        // --- STEP 3: group non-code lines into paragraphs ----------------
        var output = [];
        var para = [];

        function flushPara() {
            if (para.length) {
                output.push('<p>' + para.join('<br>') + '</p>');
                para = [];
            }
        }

        for (var j = 0; j < pieces.length; j++) {
            var piece = pieces[j];
            if (piece.indexOf('<pre>') === 0) {
                flushPara();
                output.push(piece);
            } else if (piece.trim() === '') {
                flushPara();
            } else {
                para.push(piece);
            }
        }
        flushPara();

        var result = output.join('\n');

        // --- STEP 4: inline formatting (never inside <pre> blocks) -------
        var segments = result.split(/(<pre>[\s\S]*?<\/pre>)/g);
        for (var k = 0; k < segments.length; k++) {
            if (segments[k].indexOf('<pre>') === 0) {
                continue; // code blocks stay untouched
            }
            segments[k] = formatInline(segments[k]);
        }
        result = segments.join('');

        return result;
    }

    // --- Exports ----------------------------------------------------------
    // Browser global (used by learn.js)
    global.renderQuestionMarkdown = renderMarkdown;
    // Named export for potential future use / tests
    global.MarkdownRenderer = { render: renderMarkdown };

    // CommonJS export so the renderer can be unit-tested in Node.
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = renderMarkdown;
    }
})(typeof window !== 'undefined' ? window : globalThis);

