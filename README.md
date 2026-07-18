# AI Growth Advisor - Built with Gemma

An intelligent business operating system powered by Gemma. This application provides real-time cashflow management, pricing intelligence, and supplier advisory to help SMEs optimize their operations and maximize growth.

## Features

- **Dashboard**: Real-time KPI tracking for revenue, profit, receivables, and business health.
- **Pricing Advisor (AI)**: Analyzes demand, competitor pricing, and elasticity to recommend price adjustments.
- **Supplier Intelligence**: Monitors supplier performance (on-time delivery, quality, cost) and provides AI-driven recommendations for procurement optimization.
- **Growth Simulator**: Interactive "What-If" scenario planning to forecast the impact of price, volume, and cost changes on net profit.

## Tech Stack

- **Frontend**: HTML5, CSS3, Vanilla JavaScript, Chart.js
- **Backend**: Python, FastAPI/Flask (API), SQLite
- **AI Integration**: Powered by Gemma models for advanced analytics and reasoning.

## How to Run

1. Ensure you have Python installed.
2. Install the required dependencies (if any).
3. Run the backend API server:
   ```bash
   python api.py
   ```
4. Open `index.html` in your modern web browser to access the application.

## Structure

- `index.html`: Main dashboard and application UI.
- `app.js`: Frontend logic, chart initialization, and API communication.
- `styles.css`: Custom styling, fluid animations, and responsive design.
- `api.py`: Python backend providing data and AI responses.
- `*.csv`: Sample datasets for suppliers, products, and inventory.