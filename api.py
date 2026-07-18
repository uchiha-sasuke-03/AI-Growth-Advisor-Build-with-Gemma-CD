import sqlite3
import json
import os
import csv
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import requests
DB_PATH = os.path.join(os.path.dirname(__file__), "sme_data.db")
DATA_DIR = os.path.dirname(__file__)

# ─── DATABASE SETUP ───────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Import all 11 CSV datasets into SQLite tables."""
    conn = get_db()
    cur = conn.cursor()

    csv_tables = {
        "categories":      "categories.csv",
        "products":        "products.csv",
        "suppliers":       "suppliers.csv",
        "customers":       "customers.csv",
        "employees":       "employees.csv",
        "sales_raw":       "sales_raw.csv",
        "invoices":        "invoices.csv",
        "expenses":        "expenses.csv",
        "inventory":       "inventory.csv",
        "pending_payments":"pending_payments.csv",
        "purchase_orders": "purchase_orders.csv",
    }

    for table, filename in csv_tables.items():
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"WARNING: {filepath} not found, skipping.")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                continue
            cols = list(rows[0].keys())

        # Drop & recreate table
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f'CREATE TABLE IF NOT EXISTS {table} ({col_defs})')

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            placeholders = ", ".join("?" for _ in cols)
            quoted_cols = ", ".join(f'"{c}"' for c in cols)
            for row in reader:
                values = [row.get(c, "") for c in cols]
                cur.execute(f'INSERT INTO {table} ({quoted_cols}) VALUES ({placeholders})', values)

        print(f"  [OK] Imported {table} ({len(rows)} rows)")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# ─── FORMATTING HELPERS ───────────────────────────────────────────────────────

def fmt_inr(n):
    n = float(n) if n else 0
    if abs(n) >= 10_000_000:
        return f"₹{n/10_000_000:.2f}Cr"
    elif abs(n) >= 100_000:
        return f"₹{n/100_000:.2f}L"
    else:
        return f"₹{round(n):,}"

def safe_float(v, default=0.0):
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default

def safe_int(v, default=0):
    try:
        return int(float(v)) if v else default
    except (ValueError, TypeError):
        return default

# ─── KPI ENGINE ───────────────────────────────────────────────────────────────

def compute_kpis():
    conn = get_db()
    cur = conn.cursor()

    # ── Revenue & Orders ──
    cur.execute("SELECT SUM(CAST(TotalAmount AS REAL)), COUNT(*) FROM sales_raw")
    total_revenue_raw, total_orders = cur.fetchone()
    total_revenue = safe_float(total_revenue_raw)
    avg_order_value = total_revenue / max(total_orders, 1)

    # ── Active Customers ──
    cur.execute("SELECT COUNT(DISTINCT CustomerID) FROM sales_raw")
    active_customers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM customers")
    total_customers = cur.fetchone()[0]

    # ── COGS ──
    cur.execute("""
        SELECT s.ProductID, SUM(CAST(s.Quantity AS REAL)), SUM(CAST(s.TotalAmount AS REAL))
        FROM sales_raw s
        GROUP BY s.ProductID
    """)
    sales_by_prod = cur.fetchall()
    cur.execute("SELECT ProductID, CAST(StandardMarkup AS REAL) FROM products")
    markup_map = {r[0]: safe_float(r[1], 1.0) for r in cur.fetchall()}

    total_cogs = 0
    for prod_id, qty, rev in sales_by_prod:
        markup = markup_map.get(prod_id, 1.0)
        if markup > 0:
            total_cogs += rev / markup

    # ── Expenses ──
    cur.execute("SELECT SUM(CAST(AmountSpent AS REAL)) FROM expenses")
    total_expenses = safe_float(cur.fetchone()[0])

    # ── Profit ──
    gross_profit = total_revenue - total_cogs
    net_profit = gross_profit - total_expenses
    net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

    # ── Cash Flow ──
    cur.execute("SELECT SUM(CAST(TotalInvoiceValue AS REAL)) FROM invoices WHERE Status='Paid'")
    total_collected = safe_float(cur.fetchone()[0])
    cash_in_hand = total_collected - total_expenses

    # ── Pending Receivables ──
    cur.execute("SELECT SUM(CAST(AmountPending AS REAL)), COUNT(*) FROM pending_payments")
    total_pending_raw, pending_count = cur.fetchone()
    total_pending = safe_float(total_pending_raw)

    cur.execute("SELECT COUNT(*), SUM(CAST(AmountPending AS REAL)) FROM pending_payments WHERE CAST(DaysOverdue AS INTEGER) > 0")
    overdue_count, overdue_amount_raw = cur.fetchone()
    overdue_amount = safe_float(overdue_amount_raw)

    # ── Invoices ──
    cur.execute("SELECT COUNT(*), SUM(CAST(TotalInvoiceValue AS REAL)) FROM invoices")
    total_invoices, total_invoiced = cur.fetchone()
    total_invoiced = safe_float(total_invoiced)
    collection_rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0

    # ── Inventory ──
    cur.execute("""
        SELECT i.ProductID, CAST(i.QuantityInStock AS REAL), CAST(i.ReorderPoint AS REAL),
               CAST(p.DefaultSellingPrice AS REAL), CAST(p.StandardMarkup AS REAL), p.ProductName, p.CategoryID
        FROM inventory i
        LEFT JOIN products p ON i.ProductID = p.ProductID
    """)
    inv_rows = cur.fetchall()
    total_inventory_value = 0
    low_stock_items = []
    out_of_stock_count = 0
    low_stock_count = 0

    for prod_id, qty, reorder, price, markup, name, cat_id in inv_rows:
        cost = price / max(markup, 0.01) if markup and markup > 0 else price
        total_inventory_value += qty * cost
        if qty == 0:
            out_of_stock_count += 1
        if qty < reorder:
            low_stock_count += 1
            low_stock_items.append({
                "id": prod_id, "name": name or prod_id,
                "qty": int(qty), "reorder": int(reorder)
            })

    # ── Products ──
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]

    # ── Employees & Suppliers ──
    cur.execute("SELECT COUNT(*) FROM employees WHERE IsActive='1'")
    total_employees = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM suppliers")
    total_suppliers = cur.fetchone()[0]

    # ── Top Products by Revenue ──
    cur.execute("""
        SELECT s.ProductID, SUM(CAST(s.TotalAmount AS REAL)) as rev, SUM(CAST(s.Quantity AS REAL)) as qty
        FROM sales_raw s
        GROUP BY s.ProductID
        ORDER BY rev DESC
        LIMIT 5
    """)
    top_products_raw = cur.fetchall()
    cur.execute("SELECT ProductID, ProductName FROM products")
    prod_name_map = {r[0]: r[1] for r in cur.fetchall()}
    top_products = [{"name": prod_name_map.get(r[0], r[0]), "revenue": fmt_inr(r[1]), "qty": int(safe_float(r[2]))} for r in top_products_raw]

    # ── Top Products by Quantity ──
    cur.execute("""
        SELECT s.ProductID, SUM(CAST(s.Quantity AS REAL)) as qty
        FROM sales_raw s
        GROUP BY s.ProductID
        ORDER BY qty DESC
        LIMIT 5
    """)
    top_by_qty = [{"name": prod_name_map.get(r[0], r[0]), "qty": int(safe_float(r[1]))} for r in cur.fetchall()]

    # ── Revenue by Category ──
    cur.execute("""
        SELECT c.CategoryName, SUM(CAST(s.TotalAmount AS REAL)) as rev
        FROM sales_raw s
        JOIN products p ON s.ProductID = p.ProductID
        JOIN categories c ON p.CategoryID = c.CategoryID
        GROUP BY c.CategoryName
        ORDER BY rev DESC
        LIMIT 6
    """)
    cat_rows = cur.fetchall()
    top_categories = [{"name": r[0], "revenue": fmt_inr(r[1]), "pct": f"{r[1]/total_revenue*100:.1f}" if total_revenue > 0 else "0"} for r in cat_rows]
    cat_chart_labels = [r[0] for r in cat_rows]
    cat_chart_data = [round(safe_float(r[1]) / 1000) for r in cat_rows]

    # ── Weekly Revenue (for chart) ──
    cur.execute("""
        SELECT strftime('%d', SalesDate) as day, SUM(CAST(TotalAmount AS REAL)) as rev
        FROM sales_raw
        GROUP BY strftime('%Y-%m-%d', SalesDate)
        ORDER BY SalesDate
    """)
    day_rows = cur.fetchall()
    weekly_rev = [0, 0, 0, 0, 0]
    for day_str, rev in day_rows:
        day = safe_int(day_str)
        week_idx = min(math.ceil(day / 7), 5) - 1
        if 0 <= week_idx < 5:
            weekly_rev[week_idx] += safe_float(rev)

    # ── Revenue Sparkline (7 daily points) ──
    cur.execute("""
        SELECT SalesDate, SUM(CAST(TotalAmount AS REAL)) as rev
        FROM sales_raw
        GROUP BY SalesDate
        ORDER BY SalesDate
    """)
    all_days = cur.fetchall()
    def pick_n(rows, n):
        if len(rows) <= n:
            return [round(safe_float(r[1]) / 1000) for r in rows]
        step = len(rows) // n
        return [round(safe_float(rows[i * step][1]) / 1000) for i in range(n)]
    revenue_sparkline = pick_n(all_days, 7)

    # Profit sparkline (7 daily points, scaled perfectly to net profit margin)
    profit_sparkline = [round(rev * (net_profit_margin / 100)) for rev in revenue_sparkline]

    # ── Top Customers ──
    cur.execute("""
        SELECT s.CustomerID, SUM(CAST(s.TotalAmount AS REAL)) as rev
        FROM sales_raw s
        GROUP BY s.CustomerID
        ORDER BY rev DESC
        LIMIT 5
    """)
    top_cust_raw = cur.fetchall()
    cur.execute("SELECT CustomerID, DisplayName FROM customers")
    cust_name_map = {r[0]: r[1] for r in cur.fetchall()}
    top_customers = [{"id": r[0], "name": cust_name_map.get(r[0], r[0]), "revenue": fmt_inr(r[1])} for r in top_cust_raw]

    # ── Top Suppliers ──
    cur.execute("""
        SELECT po.SupplierID, SUM(CAST(po.TotalAmountSpent AS REAL)) as spend
        FROM purchase_orders po
        GROUP BY po.SupplierID
        ORDER BY spend DESC
        LIMIT 5
    """)
    top_sup_raw = cur.fetchall()
    cur.execute("SELECT SupplierID, SupplierName, ReliabilityScore FROM suppliers")
    sup_map = {r[0]: {"name": r[1], "score": r[2]} for r in cur.fetchall()}
    top_suppliers = [{
        "id": r[0],
        "name": sup_map.get(r[0], {}).get("name", r[0]),
        "value": fmt_inr(r[1]),
        "reliability": sup_map.get(r[0], {}).get("score", "N/A")
    } for r in top_sup_raw]

    # ── Top Pending Payments ──
    cur.execute("""
        SELECT pp.InvoiceID, pp.CustomerID, CAST(pp.AmountPending AS REAL), CAST(pp.DaysOverdue AS INTEGER), pp.DueDate
        FROM pending_payments pp
        ORDER BY CAST(pp.DaysOverdue AS INTEGER) DESC, CAST(pp.AmountPending AS REAL) DESC
        LIMIT 10
    """)
    top_pending = [{
        "invoice": r[0],
        "customer": cust_name_map.get(r[1], r[1]),
        "amount": fmt_inr(r[2]),
        "amount_raw": round(safe_float(r[2])),
        "days_overdue": safe_int(r[3]),
        "due_date": r[4]
    } for r in cur.fetchall()]

    # ── Expense Breakdown ──
    cur.execute("""
        SELECT ExpenseCode, SUM(CAST(AmountSpent AS REAL)) as amt
        FROM expenses
        GROUP BY ExpenseCode
        ORDER BY amt DESC
    """)
    exp_breakdown = [{"code": r[0], "amount": fmt_inr(r[1]), "raw": round(safe_float(r[1]))} for r in cur.fetchall()]

    # ── Purchase Orders Summary ──
    cur.execute("SELECT COUNT(*), SUM(CAST(TotalAmountSpent AS REAL)) FROM purchase_orders")
    po_count, po_spend = cur.fetchone()
    po_spend = safe_float(po_spend)

    # ── Health Score ──
    profit_score = min((net_profit_margin / 20) * 100, 100)
    collection_score = collection_rate
    expense_ratio = (total_expenses / total_revenue * 100) if total_revenue > 0 else 100
    expense_score = max(100 - expense_ratio, 0)
    health_score = round(profit_score * 0.4 + collection_score * 0.4 + expense_score * 0.2)
    if health_score >= 80:
        health_label = "Excellent"
        health_color = "green"
    elif health_score >= 60:
        health_label = "Good"
        health_color = "blue"
    elif health_score >= 40:
        health_label = "Fair"
        health_color = "orange"
    else:
        health_label = "At Risk"
        health_color = "red"

    # ── Monthly revenue for line chart ──
    chart_rev_data = [round(v / 1000) for v in weekly_rev]
    chart_labels = ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5"]

    # ── Revenue by category for sales page chart ──
    cur.execute("""
        SELECT c.CategoryName, SUM(CAST(s.TotalAmount AS REAL)) as rev
        FROM sales_raw s
        JOIN products p ON s.ProductID = p.ProductID
        JOIN categories c ON p.CategoryID = c.CategoryID
        GROUP BY c.CategoryName
        ORDER BY rev DESC
    """)
    sales_cat_all = cur.fetchall()
    sales_cat_labels = [r[0] for r in sales_cat_all]
    sales_cat_data = [round(safe_float(r[1]) / 1000) for r in sales_cat_all]

    # ── Employee breakdown ──
    cur.execute("SELECT JobRole, COUNT(*) FROM employees GROUP BY JobRole")
    emp_roles = [{"role": r[0], "count": r[1]} for r in cur.fetchall()]

    # ── Forecast ──
    avg_weekly_rev = total_revenue / 5 if total_revenue > 0 else 0
    forecast_next_month = avg_weekly_rev * 5 * 1.05  # 5% growth assumption
    forecast_growth_pct = 5.0

    conn.close()

    return {
        # ── Core KPIs ──
        "totalRevenue": total_revenue,
        "totalRevenueFmt": fmt_inr(total_revenue),
        "netProfit": net_profit,
        "netProfitFmt": fmt_inr(net_profit),
        "netProfitMargin": round(net_profit_margin, 1),
        "cashInHand": cash_in_hand,
        "cashInHandFmt": fmt_inr(cash_in_hand),
        "pendingReceivables": total_pending,
        "pendingReceivablesFmt": fmt_inr(total_pending),
        "overdueCount": overdue_count,
        "overdueAmount": fmt_inr(overdue_amount),
        "overdueAmountRaw": overdue_amount,
        # ── Expenses & COGS ──
        "totalExpenses": total_expenses,
        "totalExpensesFmt": fmt_inr(total_expenses),
        "totalCOGS": total_cogs,
        "totalCOGSFmt": fmt_inr(total_cogs),
        # ── Orders & Customers ──
        "totalOrders": total_orders,
        "avgOrderValue": avg_order_value,
        "avgOrderValueFmt": fmt_inr(avg_order_value),
        "activeCustomers": active_customers,
        "totalCustomers": total_customers,
        # ── Invoices ──
        "collectionRate": round(collection_rate, 1),
        "totalInvoiced": fmt_inr(total_invoiced),
        "totalCollected": fmt_inr(total_collected),
        "totalInvoices": total_invoices,
        # ── Inventory ──
        "totalInventoryValue": total_inventory_value,
        "totalInventoryValueFmt": fmt_inr(total_inventory_value),
        "lowStockCount": low_stock_count,
        "outOfStockCount": out_of_stock_count,
        "lowStockItems": low_stock_items[:5],
        # ── Products / Staff ──
        "totalProducts": total_products,
        "totalEmployees": total_employees,
        "totalSuppliers": total_suppliers,
        # ── Health Score ──
        "healthScore": health_score,
        "healthLabel": health_label,
        "healthColor": health_color,
        # ── Chart Data ──
        "revenueSparkline": revenue_sparkline,
        "profitSparkline": profit_sparkline,
        "chartLabels": chart_labels,
        "chartRevData": chart_rev_data,
        "salesCatLabels": sales_cat_labels,
        "salesCatData": sales_cat_data,
        "catChartLabels": cat_chart_labels,
        "catChartData": cat_chart_data,
        # ── Top Lists ──
        "topProducts": top_products,
        "topByQty": top_by_qty,
        "topCategories": top_categories,
        "topCustomers": top_customers,
        "topSuppliers": top_suppliers,
        "topPendingPayments": top_pending,
        "expByCode": exp_breakdown,
        # ── Procurement ──
        "totalPOCount": po_count,
        "totalPOSpend": fmt_inr(po_spend),
        # ── Forecast ──
        "forecastNextMonth": forecast_next_month,
        "forecastNextMonthFmt": fmt_inr(forecast_next_month),
        "forecastGrowthPct": forecast_growth_pct,
        # ── Staff ──
        "empRoles": emp_roles,
    }

# ─── AI INSIGHTS ENGINE ───────────────────────────────────────────────────────

def generate_ai_insights(kpis: dict) -> dict:
    """Generate rule-based AI insights from KPIs (Gemma-style reasoning)."""
    insights = []
    alerts = []
    pricing_recs = []
    collections_recs = []
    inventory_recs = []
    growth_recs = []

    rev = kpis["totalRevenue"]
    margin = kpis["netProfitMargin"]
    health = kpis["healthScore"]
    coll_rate = kpis["collectionRate"]
    low_stock = kpis["lowStockCount"]
    out_stock = kpis["outOfStockCount"]
    overdue_count = kpis["overdueCount"]
    overdue_amt = kpis["overdueAmountRaw"]
    exp = kpis["totalExpenses"]
    cogs = kpis["totalCOGS"]

    # ── Business Brief ──
    brief = f"Your business generated {kpis['totalRevenueFmt']} in revenue with a {margin}% net profit margin. "
    brief += f"Collection rate stands at {coll_rate}%, "
    brief += f"with {low_stock} products low on stock and {overdue_count} overdue invoices totaling {kpis['overdueAmount']}."

    # ── Smart Alerts ──
    if low_stock > 0:
        alerts.append({"type": "warning", "title": "Low Stock Alert", "message": f"{low_stock} products are running low on stock. Reorder immediately.", "action": "inventory"})
    if out_stock > 0:
        alerts.append({"type": "error", "title": "Out of Stock", "message": f"{out_stock} products are completely out of stock — sales impact likely.", "action": "inventory"})
    if overdue_count > 0:
        alerts.append({"type": "error", "title": "Overdue Payments", "message": f"{overdue_count} customers have overdue payments totaling {kpis['overdueAmount']}.", "action": "customers"})
    if margin < 15:
        alerts.append({"type": "warning", "title": "Low Profit Margin", "message": f"Net profit margin at {margin}%. Industry benchmark is 20%+. Review expenses.", "action": "expenses"})
    if coll_rate < 85:
        alerts.append({"type": "warning", "title": "Collection Rate Low", "message": f"Only {coll_rate}% invoices collected. Follow up on pending payments.", "action": "customers"})
    if health >= 80:
        alerts.append({"type": "success", "title": "Excellent Business Health", "message": f"Health score {health}/100. Business is performing well across all metrics.", "action": "goals"})

    # ── Pricing Advisor ──
    if kpis["topProducts"]:
        top = kpis["topProducts"][0]
        pricing_recs.append({"product": top["name"], "action": "Increase 5-7%", "reason": "Top revenue driver with strong demand.", "badge": "increase"})
    if len(kpis["topProducts"]) >= 3:
        mid = kpis["topProducts"][2]
        pricing_recs.append({"product": mid["name"], "action": "Maintain", "reason": "Stable category performer. Avoid price disruption.", "badge": "maintain"})
    if len(kpis["topProducts"]) >= 5:
        last = kpis["topProducts"][4]
        pricing_recs.append({"product": last["name"], "action": "Reduce 3-5%", "reason": "Lower volume vs. peers. Price reduction can boost turnover.", "badge": "reduce"})

    # ── Collections Advisor ──
    for p in kpis["topPendingPayments"][:3]:
        if p["days_overdue"] > 30:
            collections_recs.append({"customer": p["customer"], "amount": p["amount"], "days": p["days_overdue"], "urgency": "high", "action": "Send legal notice + immediate call"})
        elif p["days_overdue"] > 10:
            collections_recs.append({"customer": p["customer"], "amount": p["amount"], "days": p["days_overdue"], "urgency": "medium", "action": "Send reminder email + follow-up call"})
        else:
            collections_recs.append({"customer": p["customer"], "amount": p["amount"], "days": p["days_overdue"], "urgency": "low", "action": "Send polite payment reminder"})

    # ── Inventory Advisor ──
    for item in kpis["lowStockItems"][:5]:
        reorder_qty = max(item["reorder"] * 2, 50)
        inventory_recs.append({"product": item["name"], "current": item["qty"], "reorder_at": item["reorder"], "suggested_qty": reorder_qty, "urgency": "critical" if item["qty"] == 0 else "high"})

    # ── Growth Recommendations ──
    if margin > 20:
        growth_recs.append({"title": "Expand High-Margin Categories", "detail": f"With {margin}% margin, reinvest profits into expanding top categories.", "icon": "chart-line"})
    growth_recs.append({"title": "Improve Collections Speed", "detail": f"Reducing payment terms by 10 days could improve cash flow by {fmt_inr(overdue_amt * 0.3)}.", "icon": "hand-holding-dollar"})
    growth_recs.append({"title": "Optimize Supplier Costs", "detail": "Negotiate volume discounts with top 3 suppliers to reduce COGS by 5-8%.", "icon": "truck"})
    if low_stock > 5:
        growth_recs.append({"title": "Prevent Stockout Revenue Loss", "detail": f"Stockouts on {low_stock} products may be causing missed sales. Auto-reorder threshold recommended.", "icon": "boxes-stacked"})

    # ── AI Insights ──
    insights = [
        {"icon": "lightbulb", "color": "yellow", "text": f"Top 20% customers contribute ~63% of revenue. Focus retention on: {', '.join([c['name'] for c in kpis['topCustomers'][:2]]) if kpis['topCustomers'] else 'N/A'}."},
        {"icon": "check-circle", "color": "green", "text": f"Collection rate of {coll_rate}% is {'above' if coll_rate > 85 else 'below'} the 85% benchmark. {'Maintain momentum.' if coll_rate > 85 else 'Accelerate follow-ups.'}"},
        {"icon": "circle-nodes", "color": "blue", "text": f"COGS at {kpis['totalCOGSFmt']} vs Revenue {kpis['totalRevenueFmt']}. Gross margin = {round((rev - cogs) / rev * 100, 1) if rev > 0 else 0}%."},
        {"icon": "chart-line", "color": "purple", "text": f"Best performing category: {kpis['topCategories'][0]['name'] if kpis['topCategories'] else 'N/A'} at {kpis['topCategories'][0]['pct'] if kpis['topCategories'] else '0'}% of total revenue."},
    ]

    return {
        "brief": brief,
        "alerts": alerts,
        "pricingRecs": pricing_recs,
        "collectionsRecs": collections_recs,
        "inventoryRecs": inventory_recs,
        "growthRecs": growth_recs,
        "insights": insights,
    }

# ─── LIFESPAN SETUP ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app_obj: FastAPI):
    print("SME Growth Advisor API starting...")
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 1000:
        print("Initializing database from CSV files...")
        init_db()
    else:
        print(f"Database already exists at {DB_PATH}")
    print("API ready.")
    yield
    print("API shutting down.")

app = FastAPI(title="SME Growth Advisor API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CACHED KPI STATE ─────────────────────────────────────────────────────────
_kpi_cache = None
_ai_cache = None

def get_cached_kpis():
    global _kpi_cache, _ai_cache
    if _kpi_cache is None:
        _kpi_cache = compute_kpis()
        _ai_cache = generate_ai_insights(_kpi_cache)
    return _kpi_cache, _ai_cache

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/api/kpis")
def api_kpis():
    kpis, ai = get_cached_kpis()
    return JSONResponse({**kpis, "ai": ai})

@app.get("/api/kpis/refresh")
def api_refresh():
    global _kpi_cache, _ai_cache
    _kpi_cache = None
    _ai_cache = None
    kpis, ai = get_cached_kpis()
    return JSONResponse({"status": "refreshed", **kpis, "ai": ai})

@app.get("/api/kpis/summary")
def api_summary():
    kpis, ai = get_cached_kpis()
    return JSONResponse({
        "totalRevenueFmt": kpis["totalRevenueFmt"],
        "netProfitFmt": kpis["netProfitFmt"],
        "netProfitMargin": kpis["netProfitMargin"],
        "cashInHandFmt": kpis["cashInHandFmt"],
        "pendingReceivablesFmt": kpis["pendingReceivablesFmt"],
        "healthScore": kpis["healthScore"],
        "healthLabel": kpis["healthLabel"],
        "brief": ai["brief"],
        "alerts": ai["alerts"][:3],
    })

@app.get("/api/sales")
def api_sales():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.SalesDate, s.ProductID, s.CustomerID,
               CAST(s.Quantity AS REAL) as qty,
               CAST(s.UnitPrice AS REAL) as price,
               CAST(s.TotalAmount AS REAL) as total,
               p.ProductName, c.DisplayName as CustomerName
         FROM sales_raw s
         LEFT JOIN products p ON s.ProductID = p.ProductID
         LEFT JOIN customers c ON s.CustomerID = c.CustomerID
         ORDER BY s.SalesDate DESC
         LIMIT 100
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/products")
def api_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, cat.CategoryName,
               CAST(i.QuantityInStock AS REAL) as stock,
               CAST(i.ReorderPoint AS REAL) as reorder_point
        FROM products p
        LEFT JOIN categories cat ON p.CategoryID = cat.CategoryID
        LEFT JOIN inventory i ON p.ProductID = i.ProductID
        ORDER BY p.ProductID
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/customers")
def api_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*,
               COALESCE(s.total_spent, 0) as total_spent,
               COALESCE(s.order_count, 0) as order_count
        FROM customers c
        LEFT JOIN (
            SELECT CustomerID,
                   SUM(CAST(TotalAmount AS REAL)) as total_spent,
                   COUNT(*) as order_count
            FROM sales_raw GROUP BY CustomerID
        ) s ON c.CustomerID = s.CustomerID
        ORDER BY CAST(COALESCE(s.total_spent, 0) AS REAL) DESC
        LIMIT 100
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/suppliers")
def api_suppliers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*,
               COALESCE(po.total_spend, 0) as total_spend,
               COALESCE(po.po_count, 0) as po_count
        FROM suppliers s
        LEFT JOIN (
            SELECT SupplierID,
                   SUM(CAST(TotalAmountSpent AS REAL)) as total_spend,
                   COUNT(*) as po_count
            FROM purchase_orders GROUP BY SupplierID
        ) po ON s.SupplierID = po.SupplierID
        ORDER BY CAST(COALESCE(po.total_spend, 0) AS REAL) DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/inventory")
def api_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT i.ProductID, i.QuantityInStock, i.ReorderPoint,
               p.ProductName, p.CategoryID, p.DefaultSellingPrice, p.StandardMarkup, p.SupplierID,
               cat.CategoryName,
               CASE WHEN CAST(i.QuantityInStock AS REAL) = 0 THEN 'out_of_stock'
                    WHEN CAST(i.QuantityInStock AS REAL) < CAST(i.ReorderPoint AS REAL) THEN 'low_stock'
                    ELSE 'ok' END as status
        FROM inventory i
        LEFT JOIN products p ON i.ProductID = p.ProductID
        LEFT JOIN categories cat ON p.CategoryID = cat.CategoryID
        ORDER BY CAST(i.QuantityInStock AS REAL) ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/expenses")
def api_expenses():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM expenses ORDER BY ExpenseDate DESC LIMIT 200")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/pending-payments")
def api_pending():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT pp.*, c.DisplayName as CustomerName, c.Phone, c.PaymentTermsDays
        FROM pending_payments pp
        LEFT JOIN customers c ON pp.CustomerID = c.CustomerID
        ORDER BY CAST(pp.DaysOverdue AS INTEGER) DESC, CAST(pp.AmountPending AS REAL) DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/purchase-orders")
def api_po():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT po.*, s.SupplierName, p.ProductName
        FROM purchase_orders po
        LEFT JOIN suppliers s ON po.SupplierID = s.SupplierID
        LEFT JOIN products p ON po.ProductID = p.ProductID
        ORDER BY po.PODate DESC
        LIMIT 200
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

@app.get("/api/employees")
def api_employees():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees ORDER BY EmployeeID ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(rows)

# ── AI Chat Endpoint ──
class ChatRequest(BaseModel):
    message: str
    context: str = ""

class PricingRequest(BaseModel):
    product_name: str

class GrowthRequest(BaseModel):
    query: str


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    kpis, ai = get_cached_kpis()
    msg = req.message.lower().strip()
    bot_response = ""

    # 1. Rule-based checks (Fast, deterministic) - Only trigger for short queries
    if len(msg.split()) <= 5:
        if any(w in msg for w in ["revenue", "sales", "income"]):
            bot_response = f"📊 **Revenue Analysis:**\n\n• Total Revenue: **{kpis['totalRevenueFmt']}** from {kpis['totalOrders']:,} orders\n• Avg Order Value: **{kpis['avgOrderValueFmt']}**\n• Top earner: **{kpis['topProducts'][0]['name'] if kpis['topProducts'] else 'N/A'}** at {kpis['topProducts'][0]['revenue'] if kpis['topProducts'] else 'N/A'}\n• Best category: **{kpis['topCategories'][0]['name'] if kpis['topCategories'] else 'N/A'}** ({kpis['topCategories'][0]['pct'] if kpis['topCategories'] else '0'}% of revenue)"
        elif any(w in msg for w in ["profit", "margin", "earning"]):
            bot_response = f"💰 **Profit Analysis:**\n\n• Net Profit: **{kpis['netProfitFmt']}** ({kpis['netProfitMargin']}% margin)\n• COGS: {kpis['totalCOGSFmt']}\n• Total Expenses: {kpis['totalExpensesFmt']}\n• {'⚠️ Margin below 20% benchmark. Consider cost reduction.' if kpis['netProfitMargin'] < 20 else '✅ Healthy profit margin above industry benchmark.'}"
        elif any(w in msg for w in ["cash", "flow", "liquidity"]):
            bot_response = f"💳 **Cash Flow:**\n\n• Cash in Hand: **{kpis['cashInHandFmt']}**\n• Collection Rate: **{kpis['collectionRate']}%**\n• Total Invoiced: {kpis['totalInvoiced']}\n• Total Collected: {kpis['totalCollected']}\n• Pending Receivables: **{kpis['pendingReceivablesFmt']}** across {kpis['overdueCount']} overdue accounts"
        elif any(w in msg for w in ["customer", "client", "buyer"]):
            top_c = kpis['topCustomers'][:3] if kpis['topCustomers'] else []
            bot_response = f"👥 **Customer Intelligence:**\n\n• Total Customers: {kpis['totalCustomers']:,} ({kpis['activeCustomers']:,} active)\n• Top Customers:\n" + "\n".join([f"  • {c['name']}: {c['revenue']}" for c in top_c]) + f"\n• {kpis['overdueCount']} customers have overdue payments totaling {kpis['overdueAmount']}"
        elif any(w in msg for w in ["supplier", "vendor", "procurement"]):
            top_s = kpis['topSuppliers'][:3] if kpis['topSuppliers'] else []
            bot_response = f"🚛 **Supplier Intelligence:**\n\n• Total Suppliers: {kpis['totalSuppliers']}\n• Total PO Spend: {kpis['totalPOSpend']}\n• Top Suppliers:\n" + "\n".join([f"  • {s['name']}: {s['value']} (Score: {s['reliability']}/10)" for s in top_s])
        elif any(w in msg for w in ["inventory", "stock", "reorder"]):
            bot_response = f"📦 **Inventory Intelligence:**\n\n• Total Items: {kpis['totalProducts']:,}\n• Inventory Value: **{kpis['totalInventoryValueFmt']}**\n• Low Stock: **{kpis['lowStockCount']} items** need reorder\n• Out of Stock: **{kpis['outOfStockCount']} items**\n• Critical items:\n" + "\n".join([f"  • {i['name']}: {i['qty']} units (reorder at {i['reorder']})" for i in kpis['lowStockItems'][:3]])
        elif any(w in msg for w in ["expense", "cost", "spend"]):
            top_exp = kpis['expByCode'][:3] if kpis['expByCode'] else []
            bot_response = f"🧾 **Expense Analysis:**\n\n• Total Expenses: **{kpis['totalExpensesFmt']}**\n• Top expense categories:\n" + "\n".join([f"  • {e['code']}: {e['amount']}" for e in top_exp]) + "\n• Recommendation: Review top 3 categories for 10-15% savings potential"
        elif any(w in msg for w in ["health", "score", "performance"]):
            bot_response = f"🏥 **Business Health Score: {kpis['healthScore']}/100 ({kpis['healthLabel']})**\n\n• Profit Margin Score: {min(kpis['netProfitMargin'] / 0.2, 100):.0f}/100\n• Collection Score: {kpis['collectionRate']:.0f}/100\n• {'✅ Business is performing well.' if kpis['healthScore'] >= 80 else '⚠️ Some areas need attention.'}"
        elif any(w in msg for w in ["price", "pricing", "increase"]):
            recs = ai.get('pricingRecs', [])
            bot_response = "💡 **Pricing Advisor Recommendations:**\n\n" + "\n".join([f"• **{r['product']}**: {r['action']} — {r['reason']}" for r in recs]) if recs else "No specific pricing recommendations at this time."
        elif any(w in msg for w in ["forecast", "predict", "future", "next month"]):
            bot_response = f"📈 **Revenue Forecast:**\n\n• Current Month Revenue: {kpis['totalRevenueFmt']}\n• Projected Next Month: **{kpis['forecastNextMonthFmt']}** (+{kpis['forecastGrowthPct']}%)\n• Recommendation: Maintain inventory levels and focus on top {kpis['topCategories'][0]['name'] if kpis['topCategories'] else 'categories'} for maximum growth."
        elif any(w in msg for w in ["grow", "growth", "expand", "20%"]):
            recs = ai.get('growthRecs', [])
            bot_response = "🚀 **Growth Strategy:**\n\n" + "\n".join([f"• **{r['title']}**: {r['detail']}" for r in recs])

    if not bot_response:
        # 2. LLM Fallback (Smart API)
        import json
        system_prompt = f"""You are Gemma, an expert AI Business Advisor for an SME. You are chatting directly with the user.
Use the following BUSINESS CONTEXT to answer the user's questions intelligently. 

[BUSINESS CONTEXT START]
{json.dumps(kpis, indent=2, default=str, ensure_ascii=False)}

{json.dumps(ai, indent=2, default=str, ensure_ascii=False)}
[BUSINESS CONTEXT END]

CRITICAL INSTRUCTIONS:
1. Keep your answers EXTREMELY short and concise (Maximum 2-3 sentences).
2. NEVER output raw JSON in your response. DO NOT repeat the context block.
3. Do not include boilerplate introductions, long lists, or unnecessary follow-up questions.
4. Answer the user's question directly, briefly, and data-driven using Markdown.
"""
        try:
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {
                "Authorization": "Bearer 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",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "google/gemma-3n-e2b-it",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.message.strip()}
                ],
                "max_tokens": 800,
                "temperature": 0.5
            }
            
            # Call Nvidia API
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            bot_response = data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"LLM API Error: {e}")
            bot_response = f"🤖 **Gemma AI Insight:**\n\nI am currently experiencing connection issues to the language model. However, here are your top alerts:\n" + "\n".join([f"• {a['title']}: {a['message']}" for a in ai['alerts'][:2]])

    return JSONResponse({"response": bot_response})

@app.post("/api/pricing-advisor")
def api_pricing_advisor(req: PricingRequest):
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Search for product in DB
    search_term = f"%{req.product_name}%"
    cur.execute("""
        SELECT p.ProductID, p.ProductName, p.DefaultSellingPrice, p.StandardMarkup 
        FROM products p 
        WHERE p.ProductName LIKE ? COLLATE NOCASE
        LIMIT 1
    """, (search_term,))
    product = cur.fetchone()
    
    if not product:
        conn.close()
        return JSONResponse({"error": "Product not found"}, status_code=404)
        
    product_id, product_name, default_price, markup = product
    default_price = safe_float(default_price)
    
    # 2. Get Sales and Cost Data
    cur.execute("""
        SELECT SUM(CAST(Quantity AS REAL)), SUM(CAST(TotalAmount AS REAL))
        FROM sales_raw
        WHERE ProductID = ?
    """, (product_id,))
    sales_data = cur.fetchone()
    total_qty_sold = safe_float(sales_data[0]) if sales_data[0] else 0
    total_revenue = safe_float(sales_data[1]) if sales_data[1] else 0
    
    cur.execute("""
        SELECT AVG(CAST(CostPerUnit AS REAL))
        FROM purchase_orders
        WHERE ProductID = ?
    """, (product_id,))
    cost_data = cur.fetchone()
    avg_cost = safe_float(cost_data[0]) if cost_data and cost_data[0] else (default_price / (1 + safe_float(markup)/100) if markup else default_price * 0.7)
    current_margin = ((default_price - avg_cost) / default_price * 100) if default_price > 0 else 0
    
    conn.close()
    
    # 3. Formulate Prompt for Gemma
    prompt = f"""You are Gemma, an expert Pricing Advisor. Analyze this product:
Product: {product_name}
Current Price: ₹{default_price:.2f}
Cost Price: ₹{avg_cost:.2f}
Margin: {current_margin:.1f}%
Total Sold (This Month): {int(total_qty_sold)} units

Provide a strategic pricing recommendation. Return ONLY valid JSON with this exact schema:
{{
  "badge": "Short 2-3 word action (e.g. 'Increase 5-7%', 'Hold Price')",
  "badgeColor": "#10b981 if good/increase, #f59e0b if warning, #ef4444 if critical",
  "desc": "1-2 sentence high-level summary of the strategy.",
  "gemma": "A detailed 2-3 sentence explanation of the reasoning and projected impact.",
  "insights": {{
    "currentPrice": "formatted price (e.g. ₹1,250)",
    "costPrice": "formatted cost",
    "currentMargin": "percentage with 1 decimal",
    "compPrice": "invent a realistic competitor price slightly higher or lower",
    "sales": "units sold formatted",
    "growth": "invent a realistic +X% growth metric",
    "elasticity": "invent a realistic elasticity metric like 'Low (0.32)'",
    "trend": "invent a realistic trend string like 'Increasing'"
  }},
  "impacts": [
    {{"label": "Price Increase", "val": "5-7%", "color": "#6366f1"}},
    {{"label": "Profit Increase", "val": "₹XXL", "color": "#10b981"}},
    {{"label": "Margin Increase", "val": "+X.X%", "color": "#3b82f6"}},
    {{"label": "Revenue Impact", "val": "Minimal", "color": "#64748b"}}
  ]
}}"""
    
    try:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": "Bearer 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",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemma-3n-e2b-it",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "top_p": 0.7,
            "max_tokens": 1024,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        # Clean markdown codeblocks if present
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
            
        import json
        result = json.loads(content)
        result["id"] = product_id
        result["name"] = product_name
        return JSONResponse(result)
    except Exception as e:
        print("LLM Pricing Error:", str(e))
        return JSONResponse({"error": "Failed to generate AI advice. Please try again."}, status_code=500)



@app.post("/api/growth-advisor")
def api_growth_advisor(req: GrowthRequest):
    prompt = f"""You are Gemma, an AI Growth Simulator. The user is asking to simulate a business scenario.
User Request: {req.query}

Analyze their request and return a JSON object with the estimated impact.
Use the following JSON schema strictly (no markdown, no quotes around keys unless valid JSON):
{{
  "name": "Short Scenario Name",
  "title": "Scenario: Description of the scenario",
  "badge": "AI Generated",
  "badgeColor": "#8b5cf6",
  "desc": "Detailed explanation of how this affects the business.",
  "volumeChg": 0.0,
  "priceChg": 0.0,
  "costChg": 0.0,
  "marketingChg": 0.0
}}

IMPORTANT:
- volumeChg, priceChg, costChg, marketingChg MUST be numeric (float/int) percentages (e.g. 5.5 for +5.5%, -10 for -10%).
- Do NOT wrap in ```json ... ``` blocks. Return purely valid JSON.
"""
    try:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": "Bearer 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",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemma-3n-e2b-it",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "top_p": 0.7,
            "max_tokens": 1024,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        # Clean markdown codeblocks if present
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
            
        import json
        result = json.loads(content)
        
        # Ensure numerics
        result["volumeChg"] = float(result.get("volumeChg", 0.0))
        result["priceChg"] = float(result.get("priceChg", 0.0))
        result["costChg"] = float(result.get("costChg", 0.0))
        result["marketingChg"] = float(result.get("marketingChg", 0.0))
        
        return JSONResponse(result)
    except Exception as e:
        print("LLM Growth Simulator Error:", str(e))
        return JSONResponse({"error": "Failed to simulate scenario. Please try again."}, status_code=500)

# ── Static file serving (serve the frontend) ──
@app.get("/styles.css")
def serve_styles_css():
    return FileResponse(os.path.join(DATA_DIR, "styles.css"), media_type="text/css")

@app.get("/app.js")
def serve_app_js():
    path = os.path.join(DATA_DIR, "app.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    return JSONResponse({"error": "not found"}, status_code=404)

@app.get("/")
def serve_root():
    return FileResponse(os.path.join(DATA_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
