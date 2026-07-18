const fs = require('fs');
const path = require('path');

function readCSV(filename) {
  const content = fs.readFileSync(path.join(__dirname, filename), 'utf8');
  const lines = content.trim().split('\n').map(l => l.replace(/\r$/, ''));
  const headers = parseCSVLine(lines[0]);
  return lines.slice(1).filter(l => l.trim()).map(line => {
    const values = parseCSVLine(line);
    const obj = {};
    headers.forEach((h, i) => obj[h] = values[i] || '');
    return obj;
  });
}

function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

// Load all data
const sales = readCSV('sales_raw.csv');
const products = readCSV('products.csv');
const expenses = readCSV('expenses.csv');
const invoices = readCSV('invoices.csv');
const pendingPayments = readCSV('pending_payments.csv');
const inventory = readCSV('inventory.csv');
const customers = readCSV('customers.csv');
const suppliers = readCSV('suppliers.csv');
const employees = readCSV('employees.csv');
const categories = readCSV('categories.csv');
const purchaseOrders = readCSV('purchase_orders.csv');

// Build product map for cost lookup
const productMap = {};
products.forEach(p => { productMap[p.ProductID] = p; });

// Build category map
const categoryMap = {};
categories.forEach(c => { categoryMap[c.CategoryID] = c; });

// --- TOTAL REVENUE ---
const totalRevenue = sales.reduce((s, r) => s + parseFloat(r.TotalAmount || 0), 0);

// --- TOTAL COGS (cost = UnitPrice / StandardMarkup) ---
let totalCOGS = 0;
sales.forEach(r => {
  const prod = productMap[r.ProductID];
  if (prod) {
    const markup = parseFloat(prod.StandardMarkup) || 1;
    const unitCost = parseFloat(r.UnitPrice) / markup;
    totalCOGS += unitCost * parseFloat(r.Quantity || 1);
  }
});

// --- TOTAL EXPENSES ---
const totalExpenses = expenses.reduce((s, e) => s + parseFloat(e.AmountSpent || 0), 0);

// --- NET PROFIT ---
const grossProfit = totalRevenue - totalCOGS;
const netProfit = grossProfit - totalExpenses;
const netProfitMargin = (netProfit / totalRevenue) * 100;

// --- CASH IN HAND (Revenue collected - expenses) ---
const paidInvoices = invoices.filter(i => i.Status === 'Paid');
const totalCollected = paidInvoices.reduce((s, i) => s + parseFloat(i.TotalInvoiceValue || 0), 0);
const cashInHand = totalCollected - totalExpenses;

// --- PENDING RECEIVABLES ---
const totalPending = pendingPayments.reduce((s, p) => s + parseFloat(p.AmountPending || 0), 0);
const overdueCount = pendingPayments.filter(p => parseInt(p.DaysOverdue || 0) > 0).length;
const overdueAmount = pendingPayments.filter(p => parseInt(p.DaysOverdue || 0) > 0)
  .reduce((s, p) => s + parseFloat(p.AmountPending || 0), 0);

// --- REVENUE BY WEEK (sparkline - 7 data points by day of month grouped into weeks) ---
const dailyRevenue = {};
sales.forEach(r => {
  const d = new Date(r.SalesDate);
  const week = Math.ceil(d.getDate() / 7); // week 1-5
  const key = `W${week}`;
  dailyRevenue[key] = (dailyRevenue[key] || 0) + parseFloat(r.TotalAmount || 0);
});

// Monthly revenue (daily totals aggregated)
const dayRevenue = {};
sales.forEach(r => {
  const day = r.SalesDate;
  dayRevenue[day] = (dayRevenue[day] || 0) + parseFloat(r.TotalAmount || 0);
});
const sortedDays = Object.keys(dayRevenue).sort();

// Revenue sparkline - pick 7 evenly spaced points
function pickNPoints(obj, n) {
  const keys = Object.keys(obj).sort();
  if (keys.length <= n) return keys.map(k => obj[k]);
  const step = Math.floor(keys.length / n);
  return Array.from({length: n}, (_, i) => obj[keys[i * step]] || 0);
}

const revenueSparkline = pickNPoints(dayRevenue, 7).map(v => Math.round(v / 1000));

// --- PROFIT SPARKLINE (weekly) ---
// approximate: group sales by week, subtract proportional expenses
const weeklyRevenue = {W1:0, W2:0, W3:0, W4:0, W5:0};
const weeklyQty = {W1:0, W2:0, W3:0, W4:0, W5:0};
sales.forEach(r => {
  const d = new Date(r.SalesDate);
  const week = `W${Math.ceil(d.getDate() / 7)}`;
  if (weeklyRevenue[week] !== undefined) {
    weeklyRevenue[week] += parseFloat(r.TotalAmount || 0);
    weeklyQty[week]++;
  }
});
const expPerWeek = totalExpenses / 5;
const profitSparkline = Object.values(weeklyRevenue).map(rev => {
  const cogs = rev * (totalCOGS / totalRevenue);
  return Math.round((rev - cogs - expPerWeek) / 1000);
});

// --- TOP PRODUCTS by revenue ---
const productRevenue = {};
const productQty = {};
sales.forEach(r => {
  const prod = productMap[r.ProductID];
  const name = prod ? prod.ProductName : r.ProductID;
  productRevenue[name] = (productRevenue[name] || 0) + parseFloat(r.TotalAmount || 0);
  productQty[name] = (productQty[name] || 0) + parseInt(r.Quantity || 1);
});
const topProducts = Object.entries(productRevenue)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5);

// --- TOP PRODUCTS by quantity ---
const topByQty = Object.entries(productQty)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5);

// --- REVENUE BY CATEGORY ---
const catRevenue = {};
sales.forEach(r => {
  const prod = productMap[r.ProductID];
  if (prod) {
    const cat = categoryMap[prod.CategoryID];
    const catName = cat ? cat.CategoryName : prod.CategoryID;
    catRevenue[catName] = (catRevenue[catName] || 0) + parseFloat(r.TotalAmount || 0);
  }
});
const topCategories = Object.entries(catRevenue).sort((a,b) => b[1]-a[1]).slice(0,5);

// --- MONTHLY REVENUE CHART (by day) ---
const chartRevByDay = {};
sales.forEach(r => {
  const day = parseInt(r.SalesDate.split('-')[2]);
  chartRevByDay[day] = (chartRevByDay[day] || 0) + parseFloat(r.TotalAmount || 0);
});
// Group into weeks
const chartLabels = ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5'];
const chartRevData = [0,0,0,0,0];
Object.entries(chartRevByDay).forEach(([day, rev]) => {
  const week = Math.min(Math.ceil(parseInt(day)/7), 5) - 1;
  chartRevData[week] += rev;
});
const chartRevDataM = chartRevData.map(v => Math.round(v/1000));

// Expense breakdown by category for chart
const expByCode = {};
expenses.forEach(e => {
  expByCode[e.ExpenseCode] = (expByCode[e.ExpenseCode] || 0) + parseFloat(e.AmountSpent || 0);
});

// --- LOW STOCK ITEMS ---
const lowStock = inventory.filter(i => parseInt(i.QuantityInStock) < parseInt(i.ReorderPoint))
  .map(i => ({ id: i.ProductID, qty: i.QuantityInStock, reorder: i.ReorderPoint, name: productMap[i.ProductID]?.ProductName || i.ProductID }));

// --- COLLECTIONS SUMMARY ---
const totalInvoicedAmount = invoices.reduce((s, i) => s + parseFloat(i.TotalInvoiceValue || 0), 0);
const totalCollectedAmount = paidInvoices.reduce((s, i) => s + parseFloat(i.TotalInvoiceValue || 0), 0);

// --- TOP CUSTOMERS ---
const custRevenue = {};
sales.forEach(r => {
  custRevenue[r.CustomerID] = (custRevenue[r.CustomerID] || 0) + parseFloat(r.TotalAmount || 0);
});
const topCustomers = Object.entries(custRevenue).sort((a,b) => b[1]-a[1]).slice(0,5);
const custMap = {};
customers.forEach(c => { custMap[c.CustomerID] = c; });

// --- HEALTH SCORE CALCULATION ---
// Based on: profit margin, collection rate, expense ratio
const profitMarginScore = Math.min((netProfitMargin / 20) * 100, 100);
const collectionRate = (totalCollectedAmount / totalInvoicedAmount) * 100;
const collectionScore = collectionRate;
const expenseRatio = (totalExpenses / totalRevenue) * 100;
const expenseScore = Math.max(100 - expenseRatio, 0);
const healthScore = Math.round((profitMarginScore * 0.4 + collectionScore * 0.4 + expenseScore * 0.2));

// --- SUPPLIER STATS ---
const supPOValue = {};
purchaseOrders.forEach(po => {
  supPOValue[po.SupplierID] = (supPOValue[po.SupplierID] || 0) + parseFloat(po.TotalAmountSpent || 0);
});
const topSuppliers = Object.entries(supPOValue).sort((a,b) => b[1]-a[1]).slice(0,5);
const supMap = {};
suppliers.forEach(s => { supMap[s.SupplierID] = s; });

// Format numbers
const fmt = (n) => Math.abs(n) >= 10000000 ? `₹${(n/10000000).toFixed(2)}Cr` :
             Math.abs(n) >= 100000 ? `₹${(n/100000).toFixed(2)}L` :
             `₹${Math.round(n).toLocaleString('en-IN')}`;

// Output all computed KPIs
const kpis = {
  totalRevenue: totalRevenue,
  totalRevenueFmt: fmt(totalRevenue),
  netProfit: netProfit,
  netProfitFmt: fmt(netProfit),
  netProfitMargin: netProfitMargin.toFixed(1),
  cashInHand: cashInHand,
  cashInHandFmt: fmt(cashInHand),
  pendingReceivables: totalPending,
  pendingReceivablesFmt: fmt(totalPending),
  overdueCount,
  overdueAmount: fmt(overdueAmount),
  totalExpenses: fmt(totalExpenses),
  totalCOGS: fmt(totalCOGS),
  healthScore,
  collectionRate: collectionRate.toFixed(1),
  totalInvoiced: fmt(totalInvoicedAmount),
  totalCollected: fmt(totalCollectedAmount),
  totalOverdue: fmt(overdueAmount),
  revenueSparkline,
  profitSparkline,
  chartLabels,
  chartRevData: chartRevDataM,
  topProducts: topProducts.map(([name, rev]) => ({ name, revenue: fmt(rev), qty: productQty[name] })),
  topByQty: topByQty.map(([name, qty]) => ({ name, qty })),
  topCategories: topCategories.map(([name, rev]) => ({ name, revenue: fmt(rev), pct: ((rev/totalRevenue)*100).toFixed(1) })),
  catChartData: topCategories.map(([,rev]) => Math.round(rev/1000)),
  catChartLabels: topCategories.map(([name]) => name),
  topCustomers: topCustomers.map(([id, rev]) => ({ id, name: custMap[id]?.DisplayName || id, revenue: fmt(rev) })),
  topSuppliers: topSuppliers.map(([id, val]) => ({ id, name: supMap[id]?.SupplierName || id, value: fmt(val), reliability: supMap[id]?.ReliabilityScore })),
  lowStockCount: lowStock.length,
  lowStockItems: lowStock.slice(0, 5),
  totalProducts: products.length,
  totalCustomers: customers.length,
  totalEmployees: employees.length,
  totalSuppliers: suppliers.length,
  expByCode: Object.entries(expByCode).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([code, amt]) => ({ code, amount: fmt(amt) })),
};

console.log(JSON.stringify(kpis, null, 2));
