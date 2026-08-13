/**
 * coding.js — Interactive behaviour for the Coding Exercise detail page.
 *
 * Responsibilities:
 *  1. Render Markdown fields (objective, ml_connection, problem_statement,
 *     starter_code, expected_solution, expected_output, explanation) using the
 *     existing XSS-safe renderer (window.renderQuestionMarkdown from
 *     markdown.js). This is the SAME approach used by project_markdown.js.
 *  2. "Show Hints" — reveal the hints list.
 *  3. "Show Solution" — reveal the reference solution block.
 *  4. "Dataset Preview" — render the dataset_preview JSON into an HTML table.
 *
 * SECURITY
 * --------
 *  - All Markdown is passed through renderQuestionMarkdown, which HTML-escapes
 *    every value before emitting a small allowlist of tags. Raw HTML never
 *    reaches the DOM.
 *  - The dataset preview is read from a data-dataset attribute (Django-escaped
 *    JSON). We build table cells with textContent (never innerHTML), so any
 *    cell content is safely rendered as text.
 */

(function (global) {
    'use strict';

    function renderMarkdown() {
        var render = global.renderQuestionMarkdown;
        if (typeof render !== 'function') {
            return; // renderer not loaded yet — safe no-op
        }
        var nodes = document.querySelectorAll('[data-markdown]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var raw = el.getAttribute('data-markdown') || '';
            el.innerHTML = render(raw);
        }
    }

    // --- Show Hints ------------------------------------------------------
    function setupHints() {
        var btn = document.getElementById('reveal-hints-btn');
        var list = document.getElementById('hints-list');
        if (!btn || !list) {
            return;
        }
        btn.addEventListener('click', function () {
            var hidden = list.style.display === 'none';
            list.style.display = hidden ? 'block' : 'none';
            btn.textContent = hidden ? 'Hide Hints' : 'Show Hints';
        });
    }

    // --- Show Solution ---------------------------------------------------
    function setupSolution() {
        var btn = document.getElementById('reveal-solution-btn');
        var block = document.getElementById('solution-block');
        if (!btn || !block) {
            return;
        }
        btn.addEventListener('click', function () {
            var hidden = block.style.display === 'none';
            block.style.display = hidden ? 'block' : 'none';
            btn.textContent = hidden ? 'Hide Solution' : 'Show Solution';
        });
    }

    // --- Dataset Preview table ------------------------------------------
    function setupDataset() {
        var container = document.querySelector('[data-dataset]');
        if (!container) {
            return;
        }
        var raw;
        try {
            raw = JSON.parse(container.getAttribute('data-dataset') || '[]');
        } catch (e) {
            raw = [];
        }
        if (!Array.isArray(raw) || raw.length === 0) {
            container.innerHTML = '<p class="empty-state">No dataset preview available.</p>';
            return;
        }

        // Build an HTML table safely. Headers from the first row object keys.
        var headers = Object.keys(raw[0]);
        var table = document.createElement('table');
        table.className = 'dataset-table';

        // Header row
        var thead = document.createElement('thead');
        var headTr = document.createElement('tr');
        (headers || []).forEach(function (h) {
            var th = document.createElement('th');
            th.textContent = h;
            headTr.appendChild(th);
        });
        thead.appendChild(headTr);
        table.appendChild(thead);

        // Body rows
        var tbody = document.createElement('tbody');
        raw.forEach(function (row) {
            var tr = document.createElement('tr');
            headers.forEach(function (h) {
                var td = document.createElement('td');
                var val = row[h];
                td.textContent = (val === null || val === undefined) ? '' : String(val);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        container.innerHTML = '';
        container.appendChild(table);
    }

    // --- Init ------------------------------------------------------------
    function init() {
        renderMarkdown();
        setupHints();
        setupSolution();
        setupDataset();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
