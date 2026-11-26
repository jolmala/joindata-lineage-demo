"""Writes the synthetic HR seeds for the migration example. Deterministic: same output every run.

Three files:
- raw_hr_employees.csv, raw_hr_departments.csv: the HR system tables the PowerCenter mapping reads
  (samples/powercenter/HR_DEMO_export.xml, mapping m_LOAD_DIM_EMPLOYEE).
- legacy_dim_employee.csv: the legacy target table DIM_EMPLOYEE as it stands after the nightly run
  for the reporting date. In a real migration this file is an unload of the old warehouse table;
  here legacy_run() stands in for it by applying the mapping's rules as they read in the export.

Planted in the data, each one tied to a decision in migration/m_LOAD_DIM_EMPLOYEE.md:
- two employees with no employment type (the filter drops them),
- three employees in department QAX, which the department table does not have,
- two active rows for department OPS after a reorganisation (the lookup returns one of them),
- three employees with no FTE,
- names and department codes with stray spaces and lower case.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEEDS = Path(__file__).parent / "seeds"
AS_OF = date(2026, 10, 31)  # $$AS_OF_DATE in the parameter file; var as_of_date in dbt_project.yml
LOAD_TS = "2026-10-31 02:15:00"

DEPARTMENTS = [
    # dept_code, dept_name, cost_center, active_flag, valid_from
    ("FIN", "Finance", "1100", "Y", "2019-01-01"),
    ("HRM", "Human Resources", "1200", "Y", "2019-01-01"),
    ("ITD", "IT", "1300", "Y", "2019-01-01"),
    ("SAL", "Sales and Marketing", "2100", "N", "2019-01-01"),
    ("SAL", "Sales", "2100", "Y", "2023-03-01"),
    ("MKT", "Marketing", "2200", "Y", "2023-03-01"),
    ("OPS", "Operations", "3100", "Y", "2019-01-01"),
    ("OPS", "Operations and Quality", "3150", "Y", "2026-09-01"),  # old row left active
    ("LOG", "Logistics", "3200", "Y", "2019-01-01"),
    ("RND", "Research and Development", "4100", "Y", "2021-06-01"),
]

FIRST = [
    "Aino",
    "Eero",
    "Helmi",
    "Juho",
    "Kaisa",
    "Lauri",
    "Maija",
    "Niko",
    "Oona",
    "Pekka",
    "Riikka",
    "Sami",
    "Tiina",
    "Ville",
    "Anna",
    "Mikko",
    "Sara",
    "Tuomas",
    "Elina",
    "Jari",
]
LAST = [
    "Aalto",
    "Heikkinen",
    "Hiltunen",
    "Karjalainen",
    "Koskinen",
    "Laine",
    "Lehtonen",
    "Mäkelä",
    "Niemi",
    "Ojala",
    "Peltola",
    "Rantanen",
    "Salo",
    "Tuominen",
    "Väisänen",
    "Virtanen",
]
JOBS = ["J110", "J120", "J210", "J220", "J310", "J400"]


def employees(rng: random.Random) -> list[dict]:
    """150 employees with the planted problems listed in the module docstring."""
    codes = ["FIN", "HRM", "ITD", "SAL", "MKT", "OPS", "OPS", "LOG", "LOG", "RND"]  # repeats weight the draw
    rows = []
    for i in range(150):
        emp_id = 10001 + i
        hire = date(2005, 1, 1) + timedelta(days=rng.randrange(0, 7900))
        term = None
        if rng.random() < 0.2:
            term = min(hire + timedelta(days=rng.randrange(200, 4000)), date(2026, 10, 15))
        etype = rng.choices(["P", "F", "X"], weights=[77, 15, 8])[0]
        fte = rng.choices([1.0, 0.8, 0.6, 0.5, 0.4], weights=[70, 10, 8, 7, 5])[0]
        dept = rng.choice(codes)
        first, last = rng.choice(FIRST), rng.choice(LAST)
        rows.append(
            {
                "emp_id": emp_id,
                "first_name": first,
                "last_name": last,
                "birth_date": (date(1960, 1, 1) + timedelta(days=rng.randrange(0, 14000))).isoformat(),
                "email": f"emp{emp_id}@example.com",
                "dept_code": dept,
                "job_code": rng.choice(JOBS),
                "employment_type": etype,
                "hire_date": hire.isoformat(),
                "term_date": term.isoformat() if term else "",
                "fte": f"{fte:.2f}",
            }
        )
    # Planted problems, on fixed rows so the counts in the docs stay true.
    for i in (17, 88):
        rows[i]["employment_type"] = ""
    for i in (23, 61, 140):
        rows[i]["dept_code"] = "QAX"
        rows[i]["employment_type"] = "P"
    for i in (35, 72, 119):
        rows[i]["fte"] = ""
        rows[i]["employment_type"] = "P"
    for i in (5, 50, 95):  # notice given, leaves after the reporting date: still active
        rows[i]["term_date"] = "2026-12-31"
        rows[i]["employment_type"] = "P"
    for i in (9, 44, 130):
        rows[i]["first_name"] += " "
        rows[i]["dept_code"] = " " + rows[i]["dept_code"].lower()
    return rows


def legacy_run(emps: list[dict]) -> list[dict]:
    """Stands in for the nightly PowerCenter run of m_LOAD_DIM_EMPLOYEE on an empty target.

    FIL_EMPLOYEES keeps EMPLOYMENT_TYPE <> 'X'; a missing type is NULL there, so the row is dropped.
    LKP_DEPARTMENT returns, of several active rows, the one with the latest VALID_FROM.
    SEQ_EMP_KEY numbers rows in the order the source returns them.
    """
    depts: dict[str, tuple[str, str]] = {}
    for code, name, cc, active, _valid_from in sorted(DEPARTMENTS, key=lambda d: (d[0], d[4])):
        if active == "Y":
            depts[code] = (name, cc)  # last value wins
    out = []
    for e in emps:
        if e["employment_type"] in ("", "X"):
            continue
        code = e["dept_code"].strip().upper()
        name, cc = depts.get(code, ("UNKNOWN", "9999"))
        term = e["term_date"]
        fte = float(e["fte"]) if e["fte"] else None
        band = (
            "FULL" if fte is not None and fte >= 1 else "PART" if fte is not None and fte >= 0.5 else "SMALL"
        )
        out.append(
            {
                "emp_key": len(out) + 1,
                "emp_id": e["emp_id"],
                "full_name": f"{e['last_name'].strip()}, {e['first_name'].strip()}",
                "dept_code": code,
                "dept_name": name,
                "cost_center": cc,
                "job_code": e["job_code"],
                "employment_type": e["employment_type"],
                "hire_date": e["hire_date"],
                "term_date": term,
                "is_active": "Y" if not term or date.fromisoformat(term) > AS_OF else "N",
                "fte_band": band,
                "load_ts": LOAD_TS,
            }
        )
    return out


def write(name: str, rows: list[dict]) -> None:
    """Write rows as CSV with Unix line endings, so the files are byte-identical on every platform."""
    with open(SEEDS / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    """Write the three HR seed files and print how many rows the legacy target holds."""
    rng = random.Random(2027)
    emps = employees(rng)
    cols = ["dept_code", "dept_name", "cost_center", "active_flag", "valid_from"]
    write("raw_hr_departments.csv", [dict(zip(cols, d, strict=True)) for d in DEPARTMENTS])
    write("raw_hr_employees.csv", emps)
    legacy = legacy_run(emps)
    write("legacy_dim_employee.csv", legacy)
    print(f"{len(emps)} employees, {len(legacy)} rows in the legacy target")


if __name__ == "__main__":
    main()
