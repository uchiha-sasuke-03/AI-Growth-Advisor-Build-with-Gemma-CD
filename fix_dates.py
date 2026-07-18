import sqlite3
import random
from datetime import datetime, timedelta

conn = sqlite3.connect('d:/gemma/sme_data.db')
cur = conn.cursor()

def random_may_date():
    day = random.randint(1, 31)
    return f"2025-05-{day:02d}"

# Update sales_raw
print("Updating sales_raw...")
cur.execute("SELECT rowid FROM sales_raw")
for row in cur.fetchall():
    d = random_may_date()
    cur.execute("UPDATE sales_raw SET SalesDate = ? WHERE rowid = ?", (d, row[0]))

# Update invoices
print("Updating invoices...")
cur.execute("SELECT rowid FROM invoices")
for row in cur.fetchall():
    d = random_may_date()
    cur.execute("UPDATE invoices SET InvoiceDate = ? WHERE rowid = ?", (d, row[0]))

# Update expenses
print("Updating expenses...")
cur.execute("SELECT rowid FROM expenses")
for row in cur.fetchall():
    d = random_may_date()
    cur.execute("UPDATE expenses SET ExpenseDate = ? WHERE rowid = ?", (d, row[0]))

# Update pending_payments
print("Updating pending_payments...")
cur.execute("SELECT rowid FROM pending_payments")
for row in cur.fetchall():
    d = random_may_date()
    d_dt = datetime.strptime(d, "%Y-%m-%d")
    due = (d_dt + timedelta(days=30)).strftime("%Y-%m-%d")
    cur.execute("UPDATE pending_payments SET InvoiceDate = ?, DueDate = ? WHERE rowid = ?", (d, due, row[0]))

# Update purchase_orders
print("Updating purchase_orders...")
cur.execute("SELECT rowid FROM purchase_orders")
for row in cur.fetchall():
    d = random_may_date()
    cur.execute("UPDATE purchase_orders SET PODate = ? WHERE rowid = ?", (d, row[0]))

conn.commit()
conn.close()
print("Dates successfully redistributed across May 2025.")
