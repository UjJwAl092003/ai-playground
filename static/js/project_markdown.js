/**
 * project_markdown.js — Applies the existing XSS-safe Markdown renderer
 * (static/js/markdown.js) to the Project detail and Project completion pages.
 *
 * WHY THIS EXISTS
 * --------------
 * The project pages (project_detail.html, project_complete.html) display
 * Markdown content fields (description, overview, complete_code, output,
 * explanation, learning_outcomes, dataset_info). Previously these were
 * rendered as raw text, so fenced ```python blocks and **bold** markers
 * appeared literally instead of as formatted HTML.
 *
 * This script does NOT parse Markdown itself. It reuses the exact same
 * XSS-safe renderer used by the MCQ learn page (markdown.js -> the
 * `window.renderQuestionMarkdown` function). All HTML escaping/sanitization
 * happens inside that renderer, so no unsafe innerHTML is introduced here.
 *
 * HOW IT WORKS
 * ------------
 * The templates wrap each Markdown field in an empty element carrying a
 * `data-markdown` attribute that holds the raw Markdown (Django-escaped).
 * This script reads each attribute, runs it through the existing renderer,
 * and writes the safe HTML back into the element. Because the divs start
 * empty, there is no flash of raw Markdown text.
 *
 * SECURITY MODEL
 * --------------
 * - The raw Markdown is stored in an HTML attribute (Django auto-escapes it).
 * - Every value is passed through renderQuestionMarkdown, which HTML-escapes
 *   ALL input before emitting only a small allowlist of tags. Raw HTML can
 *   never reach the DOM.
 */

(function (global) {
    'use strict';

    function renderProjectMarkdown() {
        var render = global.renderQuestionMarkdown;
        if (typeof render !== 'function') {
            // Renderer not loaded yet — do nothing (safe fallback).
            return;
        }

        var nodes = document.querySelectorAll('[data-markdown]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var raw = el.getAttribute('data-markdown') || '';
            el.innerHTML = render(raw);
        }
    }

    // Run after the DOM is ready (including when the script is deferred).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderProjectMarkdown);
    } else {
        renderProjectMarkdown();
    }
})(window);
