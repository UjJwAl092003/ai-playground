/**
 * LearnAI/ML — MCQ Learning Page JavaScript
 *
 * This script drives the interactive MCQ experience on the learn page.
 * It loads questions via JSON endpoints, handles user selection,
 * validates answers against the server, and displays explanations.
 *
 * Architecture:
 * - The page is a "shell" that loads question data on demand.
 * - No questions are hard-coded in the frontend.
 * - All data comes from the server via fetch() calls.
 * - CSRF protection is handled via Django's ensure_csrf_cookie.
 */

(function () {
    'use strict';

    // --- Configuration (set by Django template) ---
    const config = window.LEARN_CONFIG || {};
    const contentType = config.contentType || 'subject';
    const subjectSlug = config.subjectSlug;
    const projectSlug = config.projectSlug;
const reviewMode = !!config.reviewMode;
    const reviewSubjectSlug = config.reviewSubjectSlug || '';
    const reviewProjectSlug = config.reviewProjectSlug || '';
    let currentNumber = config.firstNumber || 1;
    const total = config.total || 0;
    const csrfToken = config.csrfToken || '';

    // --- Guest experience config ---
    const isGuest = !!config.isGuest;
    const guestFreeLimit = config.guestFreeLimit || 0;
    let guestAttemptsUsed = config.guestAttemptsUsed || 0;
    let guestLimitReached = !!config.guestLimitReached;
    const learnUrl = config.learnUrl || '/';

    // --- Review mode state ---
    // mistakes is an ordered list of { id, slug, number } for the user's
    // current mistakes. In review mode we drive navigation from this list
    // instead of from sequential question numbers.
    let mistakeList = Array.isArray(config.mistakes) ? config.mistakes.slice() : [];
    let reviewIndex = 0;

/**
     * Build the base path prefix used by all data/check API calls.
     *
     * Subjects use /subject/<slug>/..., projects use /project/<slug>/...
     * In review mode the effective slug AND content type may change per
     * mistake (mistakes can span multiple subjects and projects), so the
     * caller overrides the slug and content type separately.
     */
    function getApiPrefix(slug, effectiveContentType) {
        const type = effectiveContentType || contentType;
        const root = type === 'project' ? 'project' : 'subject';
        return `/${root}/${slug}/`;
    }

    /**
     * Return the current review mistake's content type (if any).
     * In normal mode this returns undefined and the page-level contentType
     * is used.
     */
    function getCurrentContentType() {
        if (reviewMode && mistakeList.length > 0 && mistakeList[reviewIndex]) {
            return mistakeList[reviewIndex].content_type;
        }
        return undefined;
    }

    /**
     * Return the current content slug for API calls.
     * In review mode the effective slug is the current mistake's slug; in
     * normal mode it is the page-level subject/project slug.
     */
    function getContentSlug() {
        return getCurrentSlug() || subjectSlug || projectSlug || '';
    }

    // --- DOM References ---
    const questionContainer = document.getElementById('question-container');
    const explanationContainer = document.getElementById('explanation-container');
    const nextBtn = document.getElementById('next-btn');
    const currentNumberSpan = document.getElementById('current-number');

    // --- State ---
    let answered = false;       // Has the user answered the current question?
    let correctAnswer = null;   // The correct answer for the current question
    let isLoading = false;      // Prevent double-loading
    let questionDataCache = {}; // Cache loaded questions for faster navigation

    // ====================================================================
    //  HELPERS
    // ====================================================================

    /**
     * Fetch JSON data from the server.
     */
    async function fetchJSON(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }

    /**
     * Show a loading spinner inside the question container.
     */
    function showLoading() {
        if (questionContainer) {
            questionContainer.innerHTML = '<div class="loading-spinner">Loading question...</div>';
        }
    }

    /**
     * Update the current question number display.
     */
    function updateQuestionNumberDisplay() {
        if (currentNumberSpan) {
            currentNumberSpan.textContent = currentNumber;
        }
    }

    // ====================================================================
    //  LOAD QUESTION
    // ====================================================================

    /**
     * Load and display a question by its number.
     * In review mode, 'number' is a question number and the current mistake's
     * slug is used (mistakes can span multiple subjects).
     */
    async function loadQuestion(number) {
        if (isLoading) return;
        isLoading = true;

        answered = false;
        correctAnswer = null;
        if (nextBtn) nextBtn.style.display = 'none';
        if (explanationContainer) explanationContainer.style.display = 'none';

        showLoading();
        updateQuestionNumberDisplay();

// Build the correct API prefix for the current content type and the
        // current mistake's slug (in review mode the mistake may belong to a
        // different subject/project than the page-level context).
        const effectiveSlug = getContentSlug();
        const effectiveContentType = getCurrentContentType();

        try {
            // Check cache first
            let data;
            if (questionDataCache[number]) {
                data = questionDataCache[number];
            } else {
                const url = `${getApiPrefix(effectiveSlug, effectiveContentType)}data/${number}/`;
                data = await fetchJSON(url);
                questionDataCache[number] = data;
            }

            renderQuestion(data);
            currentNumber = number;
        } catch (error) {
            console.error('Failed to load question:', error);
            if (questionContainer) {
                questionContainer.innerHTML = `
                    <div class="empty-state">
                        <p>Failed to load question. Please try again.</p>
                        <button class="btn btn-primary" onclick="location.reload()">Reload</button>
                    </div>
                `;
            }
        } finally {
            isLoading = false;
        }
    }

    /**
     * Return the slug of the current review mistake (if any).
     * In normal mode this returns undefined and subjectSlug is used.
     */
    function getCurrentSlug() {
        if (reviewMode && mistakeList.length > 0 && mistakeList[reviewIndex]) {
            return mistakeList[reviewIndex].slug;
        }
        return undefined;
    }

    /**
     * Return the current review mistake object (if any).
     */
    function getCurrentMistake() {
        if (reviewMode && mistakeList.length > 0 && mistakeList[reviewIndex]) {
            return mistakeList[reviewIndex];
        }
        return null;
    }

    // ====================================================================
    //  RENDER QUESTION
    // ====================================================================

    /**
     * Render a question into the DOM.
     */
    function renderQuestion(data) {
        if (!questionContainer) return;

        const optionsHtml = Object.entries(data.options).map(([label, text]) => {
            return `
                <button class="option-btn" data-option="${label}" onclick="window.handleOptionClick('${label}')" ${answered ? 'disabled' : ''}>
                    <span class="option-label">${label}.</span> ${escapeHtml(text)}
                </button>
            `;
        }).join('');

        const questionNumber = data.question_number;
        correctAnswer = null; // Will be set after check_answer

        questionContainer.innerHTML = `
            <div class="question-text">${renderQuestionText(data.question_text)}</div>
            <div class="options-list">
                ${optionsHtml}
            </div>
        `;

        // If the user has already answered this question (logged in),
        // show their previous answer and the explanation.
        if (data.previous_answer) {
            const prevCorrect = data.previous_is_correct;
            // Mark the selected option
            const selectedBtn = questionContainer.querySelector(`[data-option="${data.previous_answer}"]`);
            if (selectedBtn) {
                selectedBtn.classList.add('selected');
                if (prevCorrect) {
                    selectedBtn.classList.add('correct');
                } else {
                    selectedBtn.classList.add('wrong');
                }
            }

            // Disable all options
            questionContainer.querySelectorAll('.option-btn').forEach(btn => {
                btn.disabled = true;
            });

            // Load the answer check to show the explanation
            loadExplanation(data.question_number, data.previous_answer);
        }
    }

    // ====================================================================
    //  HANDLE OPTION CLICK
    // ====================================================================

    /**
     * Handle the user clicking an option.
     * Exposed on window so inline onclick works.
     */
    window.handleOptionClick = async function (option) {
        if (answered || isLoading) return;
        answered = true;

        // Disable all options
        document.querySelectorAll('.option-btn').forEach(btn => {
            btn.disabled = true;
        });

        // Mark the selected option
        const selectedBtn = document.querySelector(`[data-option="${option}"]`);
        if (selectedBtn) {
            selectedBtn.classList.add('selected');
        }

// Check the answer with the server.
        // In review mode use the current mistake's slug and content type so
        // that questions from multiple subjects/projects are checked against
        // the right one.
        const effectiveSlug = getContentSlug();
        const effectiveContentType = getCurrentContentType();
        const url = `${getApiPrefix(effectiveSlug, effectiveContentType)}check/${currentNumber}/?answer=${option}`;
        try {
            const result = await fetchJSON(url);

            // GUEST EXPERIENCE: if the server rejected this attempt because
            // the free limit was reached, show the friendly prompt and do
            // NOT reveal the correct answer/explanation.
            if (result.error === 'guest_limit_reached') {
                // Remove the selected highlight — the answer was not counted.
                if (selectedBtn) selectedBtn.classList.remove('selected');

                correctAnswer = null;
                guestLimitReached = true;
                renderGuestPrompt('You\'ve reached the free question limit. Create a free account to continue learning.');
                return;
            }

            correctAnswer = result.correct_answer;

            // Highlight correct/incorrect
            document.querySelectorAll('.option-btn').forEach(btn => {
                const btnOption = btn.getAttribute('data-option');
                if (btnOption === result.correct_answer) {
                    btn.classList.add('correct');
                } else if (btnOption === option && !result.is_correct) {
                    btn.classList.add('wrong');
                }
            });

            // Show the explanation
            renderExplanation(result);
        } catch (error) {
            console.error('Failed to check answer:', error);
            answered = false;
            document.querySelectorAll('.option-btn').forEach(btn => {
                btn.disabled = false;
            });
        }
    };

    // ====================================================================
    //  LOAD EXPLANATION (for previously answered questions)
    // ====================================================================

    /**
     * Load the explanation for a previously answered question.
     * In review mode, use the current mistake's slug.
     */
async function loadExplanation(number, selectedAnswer) {
        const effectiveSlug = getContentSlug();
        const effectiveContentType = getCurrentContentType();
        const url = `${getApiPrefix(effectiveSlug, effectiveContentType)}check/${number}/?answer=${selectedAnswer}`;
        try {
            const result = await fetchJSON(url);
            renderExplanation(result);
        } catch (error) {
            console.error('Failed to load explanation:', error);
        }
    }

    // ====================================================================
    //  REVIEW MODE NAVIGATION
    // ====================================================================

/**
     * Build the review API URL for the current context.
     * Supports filtering by a subject OR a project.
     */
    function getReviewApiUrl() {
        if (reviewSubjectSlug) {
            return `/review/subject/${reviewSubjectSlug}/api/questions/`;
        }
        if (reviewProjectSlug) {
            return `/review/project/${reviewProjectSlug}/api/questions/`;
        }
        return '/review/api/questions/';
    }

    /**
     * Refresh the in-memory mistake list from the server.
     * After a mistake is answered correctly it disappears from the list,
     * so this keeps the review flow in sync with the database.
     */
    async function refreshMistakes() {
        try {
            const url = getReviewApiUrl();
            const data = await fetchJSON(url);
            mistakeList = Array.isArray(data.mistakes) ? data.mistakes : [];
            return mistakeList;
        } catch (error) {
            console.error('Failed to refresh mistakes:', error);
            return mistakeList;
        }
    }

    /**
     * Show a friendly "Review Complete" state when there are no mistakes left.
     */
    function showReviewComplete() {
        if (questionContainer) {
            questionContainer.innerHTML = `
                <div class="empty-state review-complete">
                    <p>🎉 Review Complete! You have no more mistakes to review.</p>
                </div>
            `;
        }
        if (explanationContainer) explanationContainer.style.display = 'none';
        if (nextBtn) {
            nextBtn.style.display = 'inline-block';
            nextBtn.textContent = 'Back to Review';
            nextBtn.onclick = function () {
                window.location.href = '/review/';
            };
        }
        if (currentNumberSpan) currentNumberSpan.textContent = '0';
    }

    /**
     * In review mode, advance to the next mistake in the list.
     * Returns true if there was a next mistake, false otherwise.
     */
    async function goToNextMistake() {
        // Refresh first so questions answered correctly drop off the list.
        await refreshMistakes();

        if (mistakeList.length === 0) {
            showReviewComplete();
            return false;
        }

        // Move to the next item (by index). If we've finished the original
        // list, loop around to the first remaining mistake.
        if (reviewIndex >= mistakeList.length - 1) {
            reviewIndex = 0;
        } else {
            reviewIndex += 1;
        }

        const mistake = mistakeList[reviewIndex];
        currentNumber = mistake.number;
        if (currentNumberSpan) currentNumberSpan.textContent = reviewIndex + 1;
        await loadQuestion(mistake.number);
        return true;
    }

    /**
     * Set up the "Next" button behaviour for review mode.
     * Called from renderExplanation after an answer has been checked.
     */
    function setupReviewNext(result) {
        if (!nextBtn) return;
        nextBtn.style.display = 'inline-block';

        if (result.is_correct) {
            // This mistake was just resolved — refresh the list so it drops off.
            nextBtn.textContent = 'Next Mistake →';
            nextBtn.onclick = function () {
                goToNextMistake();
            };
        } else {
            // Still wrong — the same question stays in the list.
            nextBtn.textContent = 'Try Again';
            nextBtn.onclick = function () {
                // Re-render the same question so the user can answer again.
                if (mistakeList[reviewIndex]) {
                    loadQuestion(mistakeList[reviewIndex].number);
                }
            };
        }
    }

    // ====================================================================
    //  GUEST EXPERIENCE (registration prompt)
    // ====================================================================

    /**
     * Build the registration/login URL with the current page as the
     * "next" destination so the user returns right back here after
     * signing up or logging in.
     */
    function getAuthUrl(route) {
        const destination = window.location.pathname + window.location.search;
        return `/${route}/?next=${encodeURIComponent(destination)}`;
    }

    /**
     * Render the friendly "Create a free account" prompt.
     *
     * This is shown AFTER a guest has used up their free questions and seen
     * the full explanation. It is designed to feel like a natural invitation,
     * not a paywall.
     *
     * @param {string} [message] Optional custom message. When omitted, the
     *   default celebratory message is used.
     */
    function renderGuestPrompt(message) {
        if (!explanationContainer) return;

        const registerUrl = getAuthUrl('register');
        const loginUrl = getAuthUrl('login');

        const promptText = message || 'You\'ve completed your free practice questions. Create a free account to continue learning and save your progress.';

        explanationContainer.innerHTML += `
            <div class="guest-prompt">
                <h3>🎉 You're getting the hang of it!</h3>
                <p>${escapeHtml(promptText)}</p>
                <ul class="guest-benefits">
                    <li>✓ Save your learning progress</li>
                    <li>✓ Continue from where you stopped</li>
                    <li>✓ Track correct and incorrect answers</li>
                    <li>✓ Review your mistakes</li>
                    <li>✓ Track your subject-wise performance</li>
                </ul>
                <div class="guest-prompt-actions">
                    <a href="${registerUrl}" class="btn btn-primary">Create Free Account</a>
                    <a href="${loginUrl}" class="btn btn-secondary">Login</a>
                </div>
            </div>
        `;

        // Hide the "Next Question" button — the prompt replaces it.
        if (nextBtn) nextBtn.style.display = 'none';
    }

    // ====================================================================
    //  RENDER EXPLANATION
    // ====================================================================

    /**
     * Render the full explanation content.
     * This is the CORE LEARNING FEATURE of the platform.
     */
    function renderExplanation(result) {
        if (!explanationContainer) return;

        const isCorrect = result.is_correct;
        const correctAnswerLabel = result.correct_answer;

        let html = '';

        // Answer result header
        if (isCorrect) {
            html += '<p class="answer-result answer-correct">✅ Correct!</p>';
        } else {
            html += `<p class="answer-result answer-wrong">❌ Incorrect. The correct answer is <strong>${correctAnswerLabel}</strong>.</p>`;
        }

// Explanation
        if (result.explanation) {
            html += `
                <div class="explanation-section">
                    <h3>💡 Explanation</h3>
                    ${renderExplanationText(result.explanation)}
                </div>
            `;
        }

        // Python Code
        if (result.python_code) {
            html += `
                <div class="explanation-section">
                    <h3>🐍 Python Implementation</h3>
                    <pre><code>${escapeHtml(result.python_code)}</code></pre>
                </div>
            `;
        }

        // Practical Example
        if (result.practical_example) {
            html += `
                <div class="explanation-section">
                    <h3>📝 Example</h3>
                    <div class="practical-example">${escapeHtml(result.practical_example)}</div>
                </div>
            `;
        }

        // Update guest attempt state from the server response.
        if (isGuest && typeof result.guest_attempts_used === 'number') {
            guestAttemptsUsed = result.guest_attempts_used;
        }
        if (isGuest && typeof result.limit_reached === 'boolean') {
            guestLimitReached = result.limit_reached;
        }

        explanationContainer.innerHTML = html;
        explanationContainer.style.display = 'block';

        // GUEST EXPERIENCE: when a guest reaches the free-question limit,
        // show the friendly registration prompt INSTEAD of the next button.
        // The guest has already seen the full explanation (with Python code
        // and example), so this is a natural invitation, not an interruption.
        if (isGuest && guestLimitReached && !reviewMode) {
            renderGuestPrompt();
            return;
        }

        // Show the "Next Question" / "Next Mistake" button
        if (nextBtn) {
            if (reviewMode) {
                setupReviewNext(result);
            } else if (currentNumber < total) {
                nextBtn.style.display = 'inline-block';
                nextBtn.textContent = 'Next Question →';
                nextBtn.onclick = function () {
                    loadQuestion(currentNumber + 1);
                };
            } else {
                // Last question — show the appropriate completion link.
                nextBtn.style.display = 'inline-block';
                if (contentType === 'project') {
                    nextBtn.textContent = '🎉 Project Complete! View Walkthrough';
                    nextBtn.onclick = function () {
                        window.location.href = `/project/${projectSlug}/complete/`;
                    };
                } else {
                    nextBtn.textContent = '🎉 Completed! Back to Subject';
                    nextBtn.onclick = function () {
                        window.location.href = `/subject/${subjectSlug}/`;
                    };
                }
            }
        }
    }

    // ====================================================================
    //  UTILITY: Escape HTML to prevent XSS
    // ====================================================================

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Render the question text.
     *
     * question_text may contain Markdown (including ```python code blocks).
     * We render it through the XSS-safe renderer in markdown.js.
     * If that renderer is unavailable for any reason, we fall back to plain
     * escaped text so the question is still readable (old behaviour).
     */
    function renderQuestionText(text) {
        if (typeof window.renderQuestionMarkdown === 'function') {
            return window.renderQuestionMarkdown(text);
        }
        return escapeHtml(text);
    }

    /**
     * Render the explanation text.
     *
     * The explanation is a CORE learning feature and may contain Markdown:
     * paragraphs (blank-line separated), fenced ```python code blocks,
     * **bold**, *italic*, inline `code`, and lists.
     *
     * We reuse the EXACT same XSS-safe Markdown renderer used for
     * question_text (markdown.js), so:
     *   - Blank-line-separated paragraphs become separate <p> blocks.
     *   - Single newlines become <br> (natural line breaks, NOT one break
     *     after every sentence — only where the author wrote a newline).
     *   - Fenced ```python code blocks become styled <pre><code> blocks
     *     instead of literal triple backticks.
     *   - **bold**, *italic*, and inline `code` are preserved.
     *
     * If that renderer is unavailable for any reason, we fall back to
     * escaped plain text so the explanation is still readable.
     */
    function renderExplanationText(text) {
        if (typeof window.renderQuestionMarkdown === 'function') {
            return window.renderQuestionMarkdown(text);
        }
        return '<p>' + escapeHtml(text) + '</p>';
    }

    // ====================================================================
    //  INITIALIZATION
    // ====================================================================

    // In review mode, drive the flow from the mistake list provided by the
    // server. The list is always filtered to the current user's mistakes.
    if (reviewMode) {
        if (mistakeList.length === 0) {
            showReviewComplete();
        } else {
            reviewIndex = 0;
            currentNumber = mistakeList[0].number;
            if (currentNumberSpan) currentNumberSpan.textContent = 1;
            loadQuestion(mistakeList[0].number);
        }
    } else if (total > 0 && currentNumber) {
        // Normal learning mode — load the first (or Continue Learning) question
        loadQuestion(currentNumber);
    }

})();
