// ===== SME Growth Advisor - Complete Functional JS controller =====

document.addEventListener('DOMContentLoaded', () => {
    initDate();
    initNavigation();
    initChatAdvisors();
    initCharts();
    initHealthGauge();
    initScenarioSimulator();
});

// === 1. Live Date ===
function initDate() {
    const d = new Date();
    const opts = { day: 'numeric', month: 'short', year: 'numeric' };
    const dateStr = d.toLocaleDateString('en-IN', opts);
    const dateEl = document.getElementById('currentDateText');
    if (dateEl) {
        dateEl.textContent = dateStr;
    }
}

// === 2. SPA Navigation Control ===
const chartsInstances = {};

function showPage(pageId) {
    if (!pageId) return;

    // Toggle pages
    document.querySelectorAll('.page-view').forEach(view => {
        view.classList.remove('active');
    });

    const targetView = document.getElementById(pageId);
    if (targetView) {
        targetView.classList.add('active');
    }

    // Toggle sidebar active highlights
    document.querySelectorAll('.nav-item').forEach(item => {
        if (item.getAttribute('data-target') === pageId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Resize/Update charts that become visible
    triggerChartResize(pageId);
}

function initNavigation() {
    // Sidebar nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const target = item.getAttribute('data-target');
            if (target === 'logout') {
                document.getElementById('logoutModal').classList.add('active');
            } else {
                showPage(target);
            }
        });
    });

    // Top action bar, links and mini cards
    document.querySelectorAll('[data-target]').forEach(el => {
        if (el.classList.contains('nav-item')) return; // handled above
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const target = el.getAttribute('data-target');
            if (target === 'logout') {
                document.getElementById('logoutModal').classList.add('active');
            } else {
                showPage(target);
            }
        });
    });

    // Shortcut actions
    document.querySelectorAll('.shortcut-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const action = item.getAttribute('data-action');
            alert(`Shortcut Action triggered: "${action.toUpperCase()}". Real application will load transaction forms here.`);
        });
    });

    // Upgrade buttons
    const btnUpgrade = document.getElementById('btnUpgrade');
    if (btnUpgrade) {
        btnUpgrade.addEventListener('click', () => {
            alert('🎉 Upgrade to Pro package is requested. Connect to checkout workflow next!');
        });
    }

    // Modal Close
    const btnCancelLogout = document.getElementById('btnCancelLogout');
    if (btnCancelLogout) {
        btnCancelLogout.addEventListener('click', () => {
            document.getElementById('logoutModal').classList.remove('active');
        });
    }

    const btnConfirmLogout = document.getElementById('btnConfirmLogout');
    if (btnConfirmLogout) {
        btnConfirmLogout.addEventListener('click', () => {
            document.getElementById('logoutModal').classList.remove('active');
            alert('Logout simulated successfully. Returning to Dashboard Overview.');
            showPage('dashboard');
        });
    }
}

// === 3. AI Chat Panels (Both right sidebar & central chat view) ===
function initChatAdvisors() {
    // A: Right Sidebar Chat Panel
    const panelInput = document.getElementById('panelChatInput');
    const panelSend = document.getElementById('btnSendPanelChat');
    const panelBody = document.getElementById('panelChatBody');
    const btnRestartChat = document.getElementById('btnRestartChat');

    // B: Full-screen Chat Page
    const fullInput = document.getElementById('fullChatInput');
    const fullSend = document.getElementById('btnSendFullChat');
    const fullBody = document.getElementById('fullChatHistory');

    const cannedResponses = {
        'which products are most profitable?': `📊 **Pricing Analysis (Gemma):**\n\n- **Coffee Beans** are your highest gross-margin product (approx. **62% profit margin**), generating ₹1,35,860 in revenue.\n- **Green Tea** follows closely with **58% profit margin**.\n- **Recommendation:** Increase Coffee Beans shelf placement and bundle with slower-moving Sugar items.`,
        'how can i improve my cash flow?': `💰 **Cashflow Copilot advisory:**\n\n1. **Overdue Invoices:** Follow up with *Rahul Traders* (₹40,000, 45 days overdue) and *Sharma Stores* (₹22,500, 30 days overdue).\n2. **Inventory Lockup:** Reduce milk powder stock by 10% to free up ₹8,700 cash.\n3. **Vendor Optimization:** Negotiate xyz Suppliers terms from Net-30 to Net-45.`,
        'who are my high value customers?': `👥 **Customer Intelligence:**\n\n- Your top 20% customers contribute to **63% of your profit**.\n- **Rahul Traders** is your largest buyer, but has an average payment delay of **38 days**.\n- **Recommendation:** Offer a 1.5% discount for payments cleared within 10 days to improve collections speed.`,
        'should i increase prices?': `📈 **Pricing Advisor Prediction:**\n\n- **Yes, for Coffee Beans:** Strong local demand and low local competition allows a **5-7% pricing uptick** without significant customer churn.\n- **No, for Milk Powder:** High local price sensitivity. A price hike of 5% is forecasted to contract volume by 12%.`
    };

    function appendMessage(chatContainer, text, isUser = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `panel-msg ${isUser ? 'user' : 'bot'}`;
        if (chatContainer === fullBody) {
            msgDiv.className = `full-chat-msg ${isUser ? 'user' : 'bot'}`;
        }

        const avatar = isUser ? '' : `<div class="msg-avatar">🤖</div>`;
        const content = `<div class="msg-content"><p>${text.replace(/\n/g, '<br>')}</p></div>`;

        msgDiv.innerHTML = isUser ? content : (avatar + content);
        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function processChat(inputEl, container) {
        const text = inputEl.value.trim();
        if (!text) return;

        appendMessage(container, text, true);
        inputEl.value = '';

        // Add thinking element
        const thinking = document.createElement('div');
        thinking.className = container === fullBody ? 'full-chat-msg bot' : 'panel-msg bot';
        thinking.innerHTML = `<div class="msg-avatar">🤖</div><div class="msg-content"><em>Gemma is thinking...</em></div>`;
        container.appendChild(thinking);
        container.scrollTop = container.scrollHeight;

        setTimeout(() => {
            thinking.remove();
            const query = text.toLowerCase();
            let matchedResponse = "I've received your query. Based on your current transaction streams and ledger history, everything looks solid. Let me know if you would like me to generate a specific forecast or product markdown simulation.";

            for (const [key, response] of Object.entries(cannedResponses)) {
                if (query.includes(key) || key.includes(query)) {
                    matchedResponse = response;
                    break;
                }
            }
            appendMessage(container, matchedResponse, false);
        }, 800);
    }

    // Bind Right Sidebar Chat events
    if (panelSend && panelInput) {
        panelSend.addEventListener('click', () => processChat(panelInput, panelBody));
        panelInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') processChat(panelInput, panelBody);
        });
    }

    // Bind Full Chat Page events
    if (fullSend && fullInput) {
        fullSend.addEventListener('click', () => processChat(fullInput, fullBody));
        fullInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') processChat(fullInput, fullBody);
        });
    }

    // Suggestion chips handler
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.getAttribute('data-query');
            panelInput.value = query;
            processChat(panelInput, panelBody);
        });
    });

    // Reset Chat panel button
    if (btnRestartChat) {
        btnRestartChat.addEventListener('click', () => {
            panelBody.innerHTML = `
                <div class="panel-msg bot">
                    <div class="msg-avatar">🤖</div>
                    <div class="msg-content">
                        <p>Hi Arjun! I'm your AI Business Advisor. I can help you analyze your business, find opportunities and solve problems.</p>
                        <p>How can I help you today?</p>
                    </div>
                </div>
            `;
        });
    }
}

// === 4. Business Health Score Gauge Animation ===
function initHealthGauge() {
    const fillCircle = document.getElementById('dashHealthScoreFill');
    if (fillCircle) {
        const val = 82;
        const circumference = 2 * Math.PI * 40; // ~251.2
        const offset = circumference - (val / 100) * circumference;

        // Apply with a minor delay for loading visual transition
        setTimeout(() => {
            fillCircle.style.strokeDashoffset = offset;
        }, 300);
    }
}

// === 5. Growth Scenario Simulator Modal ===
function initScenarioSimulator() {
    const modal = document.getElementById('scenarioSimulatorModal');
    const openBtn = document.getElementById('btnOpenScenarioSimulator');
    const closeBtn = document.getElementById('btnCloseSimulatorModal');
    const submitBtn = document.getElementById('btnSubmitSim');
    const resultBox = document.getElementById('simResultsOutput');
    const outputGrid = document.getElementById('simOutputGrid');

    if (openBtn && modal) {
        openBtn.addEventListener('click', () => {
            modal.classList.add('active');
            resultBox.style.display = 'none';
        });
    }

    if (closeBtn && modal) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
    });

    if (submitBtn) {
        submitBtn.addEventListener('click', () => {
            const product = document.getElementById('simProductOption').value;
            const action = document.getElementById('simActionOption').value;

            // Generate simulated calculations dynamically
            let revenueDiff = "+12%";
            let profitDiff = "+18%";
            let risk = "Medium";
            let riskColor = "text-orange";

            if (action.includes('Decrease')) {
                revenueDiff = "+4%";
                profitDiff = "-3%";
                risk = "Low";
                riskColor = "text-green";
            } else if (action.includes('Marketing')) {
                revenueDiff = "+15%";
                profitDiff = "+8%";
                risk = "Low";
                riskColor = "text-green";
            } else if (action.includes('Reduce Cost')) {
                revenueDiff = "0%";
                profitDiff = "+20%";
                risk = "Low";
                riskColor = "text-green";
            }

            outputGrid.innerHTML = `
                <div class="pred-item"><span>Est. Revenue</span><strong class="text-green">${revenueDiff}</strong></div>
                <div class="pred-item"><span>Est. Profit</span><strong class="${profitDiff.startsWith('-') ? 'text-red' : 'text-green'}">${profitDiff}</strong></div>
                <div class="pred-item"><span>Risk Level</span><strong class="${riskColor}">${risk}</strong></div>
            `;

            resultBox.style.display = 'block';
        });
    }
}

// === 6. Charts configurations (Chart.js) ===
function initCharts() {
    Chart.defaults.color = '#64748b';
    Chart.defaults.font.family = 'Inter';

    // Helper to generate sparkline datasets
    function createSparkline(canvasId, data, color) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        chartsInstances[canvasId] = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [1, 2, 3, 4, 5, 6, 7],
                datasets: [{
                    data: data,
                    borderColor: color,
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
        });
    }

    // Sparklines for dashboard cards
    createSparkline('sparklineRev', [42, 44, 43, 45, 47, 46, 48.5], '#6366f1');
    createSparkline('sparklineProf', [10, 11, 10.5, 12, 11.8, 12.2, 12.5], '#10b981');
    createSparkline('sparklineCash', [80, 78, 79, 76, 75, 74.5, 73.9], '#3b82f6');
    createSparkline('sparklineRec', [85, 88, 90, 89, 92, 94, 96.8], '#f59e0b');

    // 6.1 Dashboard Revenue Chart
    const dashRevCtx = document.getElementById('dashRevenueChart');
    if (dashRevCtx) {
        const ctx = dashRevCtx.getContext('2d');
        const revGrad = ctx.createLinearGradient(0, 0, 0, 150);
        revGrad.addColorStop(0, 'rgba(99, 102, 241, 0.35)');
        revGrad.addColorStop(1, 'rgba(99, 102, 241, 0.01)');

        chartsInstances['dashRevenueChart'] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['1 May', '6 May', '11 May', '16 May', '21 May', '26 May', '31 May'],
                datasets: [{
                    label: 'Revenue',
                    data: [180000, 240000, 310000, 280000, 360000, 420000, 485230],
                    borderColor: '#6366f1',
                    borderWidth: 2.5,
                    backgroundColor: revGrad,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#6366f1'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: '#e2e8f0' }, ticks: { callback: v => '₹' + (v / 1000) + 'k' } },
                    x: { grid: { color: '#e2e8f0' } }
                }
            }
        });
    }

    // 6.2 Dashboard Products Donut
    const dashProdCtx = document.getElementById('dashProductsChart');
    if (dashProdCtx) {
        chartsInstances['dashProductsChart'] = new Chart(dashProdCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Coffee Beans', 'Green Tea', 'Milk Powder', 'Sugar', 'Others'],
                datasets: [{
                    data: [28, 22, 18, 12, 20],
                    backgroundColor: ['#6366f1', '#10b981', '#3b82f6', '#f59e0b', '#94a3b8'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: { legend: { display: false } }
            }
        });
    }

    // 6.3 Mini Cash Flow Bar Chart
    const miniBarCtx = document.getElementById('miniBarChart');
    if (miniBarCtx) {
        chartsInstances['miniBarChart'] = new Chart(miniBarCtx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: ['W1', 'W2', 'W3', 'W4'],
                datasets: [
                    {
                        label: 'Cash In',
                        data: [120, 150, 140, 155],
                        backgroundColor: '#00b894',
                        borderRadius: 3
                    },
                    {
                        label: 'Cash Out',
                        data: [100, 130, 110, 151],
                        backgroundColor: '#e74c3c',
                        borderRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { display: false } },
                    y: { grid: { display: false }, ticks: { display: false } }
                }
            }
        });
    }

    // 6.4 Sales Page Trend Line
    const salesTrendCtx = document.getElementById('salesTrendChart');
    if (salesTrendCtx) {
        chartsInstances['salesTrendChart'] = new Chart(salesTrendCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: ['1 May', '8 May', '15 May', '22 May', '31 May'],
                datasets: [{
                    label: 'Sales Trend',
                    data: [180000, 310000, 350000, 460000, 485230],
                    borderColor: '#6c5ce7',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } }
            }
        });
    }

    // 6.5 Sales Page Category
    const salesCatCtx = document.getElementById('salesCategoryChart');
    if (salesCatCtx) {
        chartsInstances['salesCategoryChart'] = new Chart(salesCatCtx.getContext('2d'), {
            type: 'pie',
            data: {
                labels: ['Beverages', 'Food', 'Groceries', 'Others'],
                datasets: [{
                    data: [40, 30, 20, 10],
                    backgroundColor: ['#6c5ce7', '#00b894', '#fdcb6e', '#5e5e8c'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, position: 'right', labels: { boxWidth: 10 } } }
            }
        });
    }

    // 6.6 Inventory Category Donut
    const invCatCtx = document.getElementById('inventoryCategoryChart');
    if (invCatCtx) {
        chartsInstances['inventoryCategoryChart'] = new Chart(invCatCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Beverages', 'Food', 'Groceries', 'Others'],
                datasets: [{
                    data: [40, 25, 20, 15],
                    backgroundColor: ['#6c5ce7', '#00b894', '#fdcb6e', '#5e5e8c'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: { legend: { display: false } }
            }
        });
    }

    // 6.7 Expenses Category Donut
    const expCatCtx = document.getElementById('expensesCategoryChart');
    if (expCatCtx) {
        chartsInstances['expensesCategoryChart'] = new Chart(expCatCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Rent', 'Salaries', 'Utilities', 'Marketing', 'Others'],
                datasets: [{
                    data: [30, 25, 15, 10, 20],
                    backgroundColor: ['#6c5ce7', '#00b894', '#fdcb6e', '#e17055', '#5e5e8c'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: { legend: { display: false } }
            }
        });
    }

    // 6.8 Actual vs Forecasted Revenue
    const actualForecastCtx = document.getElementById('actualForecastChart');
    if (actualForecastCtx) {
        chartsInstances['actualForecastChart'] = new Chart(actualForecastCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: ['1 May', '15 May', '1 Jun', '15 Jun', '30 Jun'],
                datasets: [
                    {
                        label: 'Actual Revenue',
                        data: [420000, 485230, null, null, null],
                        borderColor: '#6c5ce7',
                        borderWidth: 3,
                        fill: false,
                        spanGaps: true
                    },
                    {
                        label: 'Forecast',
                        data: [null, 485230, 500000, 510000, 520000],
                        borderColor: '#00b894',
                        borderDash: [5, 5],
                        borderWidth: 3,
                        fill: false,
                        spanGaps: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, position: 'bottom' } }
            }
        });
    }
}

// Chart resizing trigger helper
function triggerChartResize(pageId) {
    setTimeout(() => {
        if (pageId === 'dashboard') {
            const list = ['sparklineRev', 'sparklineProf', 'sparklineCash', 'sparklineRec', 'dashRevenueChart', 'dashProductsChart', 'miniBarChart'];
            list.forEach(id => {
                if (chartsInstances[id]) chartsInstances[id].resize();
            });
        } else if (pageId === 'sales-analytics') {
            if (chartsInstances['salesTrendChart']) chartsInstances['salesTrendChart'].resize();
            if (chartsInstances['salesCategoryChart']) chartsInstances['salesCategoryChart'].resize();
        } else if (pageId === 'inventory') {
            if (chartsInstances['inventoryCategoryChart']) chartsInstances['inventoryCategoryChart'].resize();
        } else if (pageId === 'expenses') {
            if (chartsInstances['expensesCategoryChart']) chartsInstances['expensesCategoryChart'].resize();
        } else if (pageId === 'revenue-forecast') {
            if (chartsInstances['actualForecastChart']) chartsInstances['actualForecastChart'].resize();
        }
    }, 80);
}
