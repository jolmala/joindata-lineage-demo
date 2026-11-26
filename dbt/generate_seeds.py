"""Write the synthetic seed CSVs for the dbt demo (a fictional tool wholesaler).

Deterministic: the same files every run. One problem is planted on purpose: four order lines
refer to product 999, which does not exist. The relationships test reports it as a warning.

Run from the repository root:  python dbt/generate_seeds.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEEDS = Path(__file__).resolve().parent / "seeds"
START, END = date(2026, 1, 1), date(2026, 10, 31)

COUNTRIES = [
    ("FI", "Finland", "Nordics", "EUR"),
    ("SE", "Sweden", "Nordics", "SEK"),
    ("EE", "Estonia", "Baltics", "EUR"),
    ("DE", "Germany", "Western Europe", "EUR"),
    ("NL", "Netherlands", "Western Europe", "EUR"),
    ("US", "United States", "North America", "USD"),
]
GROUPS = [("POR", "Drills"), ("SAH", "Saws"), ("HIO", "Grinders")]
PRODUCTS = [
    (101, "Cordless drill 18V", "POR", "pcs", 129.0),
    (102, "Hammer drill 800W", "POR", "pcs", 159.0),
    (103, "Impact driver 18V", "POR", "pcs", 119.0),
    (104, "Drill press 550W", "POR", "pcs", 349.0),
    (201, "Circular saw 1400W", "SAH", "pcs", 179.0),
    (202, "Jigsaw 650W", "SAH", "pcs", 99.0),
    (203, "Mitre saw 1800W", "SAH", "pcs", 389.0),
    (301, "Angle grinder 125mm", "HIO", "pcs", 89.0),
    (302, "Orbital sander", "HIO", "pcs", 79.0),
    (303, "Sanding discs, 50", "HIO", "box", 19.0),
]
# EUR per one unit of the currency, around which daily rates move.
FX_BASE = {"EUR": 1.0, "SEK": 0.088, "USD": 0.92}
STATUSES = ["T"] * 8 + ["A", "P"]  # T = delivered, A = open, P = cancelled


def write(name: str, header: list[str], rows: list[tuple]) -> None:
    """Write one seed file."""
    SEEDS.mkdir(exist_ok=True)
    with open(SEEDS / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh, lineterminator="\n")
        out.writerow(header)
        out.writerows(rows)


def main() -> None:
    """Generate every seed file."""
    rnd = random.Random(42)
    days = [START + timedelta(n) for n in range((END - START).days + 1)]

    write("raw_countries", ["country_code", "country_name", "region"], [c[:3] for c in COUNTRIES])
    write("raw_product_groups", ["group_code", "group_name"], GROUPS)
    write("raw_products", ["product_id", "product_name", "group_code", "unit"], [p[:4] for p in PRODUCTS])

    currency_of = {c[0]: c[3] for c in COUNTRIES}
    customers = []
    for cid in range(1, 61):
        country = rnd.choices([c[0] for c in COUNTRIES], weights=[30, 15, 8, 20, 12, 15])[0]
        updated = START + timedelta(rnd.randrange(0, 300))
        customers.append(
            (cid, f"Customer {cid:03d}", country, f"buyer{cid:03d}@example.com", f"{updated} 08:00:00")
        )
    write("raw_customers", ["customer_id", "customer_name", "country_code", "email", "updated_at"], customers)

    fx = []
    for day in days:
        for cur, base in FX_BASE.items():
            rate = base if cur == "EUR" else round(base * (1 + rnd.uniform(-0.03, 0.03)), 6)
            fx.append((cur, day.isoformat(), rate))
    write("raw_fx_rates", ["currency", "rate_date", "eur_per_unit"], fx)

    price_of = {p[0]: p[4] for p in PRODUCTS}
    orders, lines, line_id = [], [], 1
    for oid in range(1, 601):
        customer = rnd.choice(customers)
        day = rnd.choice(days)
        currency = currency_of[customer[2]]
        orders.append((oid, customer[0], day.isoformat(), currency, rnd.choice(STATUSES)))
        for product in rnd.sample(list(price_of), rnd.randint(1, 4)):
            qty = rnd.randint(1, 20)
            # Price list is in EUR; convert to the order currency at the base rate.
            unit_price = round(price_of[product] / FX_BASE[currency], 2)
            lines.append((line_id, oid, product, qty, unit_price))
            line_id += 1
    # Planted problem: lines for a product that is not in the product table.
    for n in range(4):
        lines.append((line_id, 10 + n * 50, 999, 1, 50.0))
        line_id += 1
    write("raw_orders", ["order_id", "customer_id", "order_date", "currency", "status"], orders)
    write("raw_order_lines", ["line_id", "order_id", "product_id", "quantity", "unit_price"], lines)


if __name__ == "__main__":
    main()
