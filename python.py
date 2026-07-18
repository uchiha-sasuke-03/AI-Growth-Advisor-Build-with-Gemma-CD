import pandas as pd
import random

# Define the retail categories
categories = [
    ('CAT001', 'Fresh Groceries'),
    ('CAT002', 'Packaged Foods'),
    ('CAT003', 'Large Appliances'),
    ('CAT004', 'Small Electronics'),
    ('CAT005', 'Men\'s Apparel'),
    ('CAT006', 'Women\'s Apparel'),
    ('CAT007', 'Cookware & Pots'),
    ('CAT008', 'Kitchen Gadgets')
]

# 1. Core Retail Products to match your Dashboard Alerts (Image 1)
# Format: (ProductID, Name, CategoryName, CostPrice, CurrentStock, ReorderPoint)
critical_retail_products = [
    ('PROD001', 'Organic Avocados (Pack of 3)', 'Fresh Groceries', 120.00, 45, 50),     # High volume seller
    ('PROD002', 'Premium Green Tea Bags (100s)', 'Packaged Foods', 220.00, 12, 30),     # LOW STOCK (Dashboard Alert)
    ('PROD003', '4-Burner Gas Stove Cooktop', 'Large Appliances', 4500.00, 2, 5),      # VERY LOW STOCK (Dashboard Alert)
    ('PROD004', 'Stainless Steel Knife Set (5pc)', 'Kitchen Gadgets', 850.00, 0, 15),  # OUT OF STOCK (Dashboard Alert)
]

# 2. Sample pools to dynamically generate the rest of the 400 items
item_pools = {
    'Fresh Groceries': ['Alfonso Mangoes', 'Organic Tomatoes', 'Greek Yogurt', 'Whole Wheat Bread', 'Fresh Milk 1L'],
    'Packaged Foods': ['Basmati Rice 5kg', 'Olive Oil 1L', 'Dark Chocolate Bar', 'Oatmeal Oats', 'Spaghetti Pasta'],
    'Large Appliances': ['Double Door Refrigerator', 'Front Load Washing Machine', 'Microwave Oven 20L', 'Dishwasher'],
    'Small Electronics': ['Electric Kettle 1.5L', 'Blender & Juicer', 'Pop-up Toaster', 'Hand Blender'],
    'Men\'s Apparel': ['Slim Fit Denim', 'Casual Linen Shirt', 'Polo T-Shirt', 'Athletic Shorts', 'Formal Blazer'],
    'Women\'s Apparel': ['Summer Cotton Dress', 'High Rise Jeans', 'Formal Trousers', 'Athletic Leggings', 'Ethnic Kurti'],
    'Cookware & Pots': ['Non-Stick Frying Pan', 'Pressure Cooker 5L', 'Ceramic Casserole', 'Cast Iron Skillet'],
    'Kitchen Gadgets': ['Digital Kitchen Scale', 'Garlic Press', 'Vegetable Chopper', 'Silicone Spatula Set']
}

product_list = []
inventory_list = []

# First, inject the critical dashboard alert products
for p_id, name, cat_name, cost, stock, reorder in critical_retail_products:
    cat_id = [c[0] for c in categories if c[1] == cat_name][0]
    markup = 1.25 if 'Groceries' in cat_name else 1.40
    selling_price = round(cost * markup, 2)
    
    product_list.append([p_id, name, cat_id, 'SUP001', markup, selling_price, f"Premium quality {name}", "Unit"])
    inventory_list.append([p_id, stock, reorder])

# Next, fill out the rest of the 400 products pulling from retail pools
for i in range(4, 400):
    p_id = f"PROD{i+1:03}"
    cat_id, cat_name = random.choice(categories)
    
    # Pick a base name and add a random identifier to keep it unique
    base_name = random.choice(item_pools[cat_name])
    name = f"{base_name} (Batch #{random.randint(10, 99)})"
    
    # Set realistic cost constraints by retail category
    if cat_name in ['Fresh Groceries', 'Packaged Foods']:
        cost = round(random.uniform(30.00, 500.00), 2)
        markup = round(random.uniform(1.10, 1.25), 2) # Lower grocery margins
        reorder = 40
        stock = random.randint(10, 200)
    elif cat_name in ['Large Appliances', 'Small Electronics']:
        cost = round(random.uniform(1200.00, 25000.00), 2)
        markup = round(random.uniform(1.25, 1.45), 2) # Higher electronics margins
        reorder = 5
        stock = random.randint(2, 20)
    else: # Apparel & Kitchenware
        cost = round(random.uniform(200.00, 2000.00), 2)
        markup = round(random.uniform(1.40, 1.80), 2) # Very high fashion margins
        reorder = 15
        stock = random.randint(5, 80)
        
    selling_price = round(cost * markup, 2)
    
    product_list.append([p_id, name, cat_id, f"SUP{random.randint(1,40):03}", markup, selling_price, f"Retail item under {cat_name}.", "Unit"])
    inventory_list.append([p_id, stock, reorder])

# Convert to DataFrames
df_products = pd.DataFrame(product_list, columns=['ProductID', 'ProductName', 'CategoryID', 'SupplierID', 'StandardMarkup', 'DefaultSellingPrice', 'Description', 'UnitOfMeasurement'])
df_inventory = pd.DataFrame(inventory_list, columns=['ProductID', 'QuantityInStock', 'ReorderPoint'])

print(f"Successfully configured {len(df_products)} retail products across 8 categories!")
# --- Your original code is above this line ---

# Convert to DataFrames
df_products = pd.DataFrame(product_list, columns=['ProductID', 'ProductName', 'CategoryID', 'SupplierID', 'StandardMarkup', 'DefaultSellingPrice', 'Description', 'UnitOfMeasurement'])
df_inventory = pd.DataFrame(inventory_list, columns=['ProductID', 'QuantityInStock', 'ReorderPoint'])

print(f"Successfully configured {len(df_products)} retail products across 8 categories!")

# --- ADD THESE TWO LINES TO THE VERY END ---
df_products.to_csv('products.csv', index=False)
df_inventory.to_csv('inventory.csv', index=False)
print("Files products.csv and inventory.csv generated!")