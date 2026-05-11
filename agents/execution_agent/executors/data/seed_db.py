"""
seed_db.py — creates / migrates office.db with all tables the execution agents need.
Safe to re-run: uses CREATE TABLE IF NOT EXISTS and INSERT OR IGNORE.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "office.db"


def seed():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # ── hr_leave_balances ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hr_leave_balances (
            employee_name       TEXT NOT NULL,
            leave_type          TEXT NOT NULL,
            total_entitlement   INTEGER NOT NULL,
            used_days           INTEGER NOT NULL DEFAULT 0,
            remaining_days      INTEGER NOT NULL,
            policy_note         TEXT,
            PRIMARY KEY (employee_name, leave_type)
        )
    """)
    for row in [
        ("Ali Abdallah",  "annual", 21, 7,  14, "Unused days above 5 cannot be carried to next year"),
        ("Sara Hassan",   "annual", 21, 3,  18, "Unused days above 5 cannot be carried to next year"),
        ("Ali Abdallah",  "sick",   10, 2,   8, "Requires medical certificate after 3 consecutive days"),
        ("Sara Hassan",   "sick",   10, 0,  10, "Requires medical certificate after 3 consecutive days"),
        ("Omar Youssef",  "annual", 21, 10, 11, "Unused days above 5 cannot be carried to next year"),
        ("Omar Youssef",  "sick",   10, 1,   9, "Requires medical certificate after 3 consecutive days"),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO hr_leave_balances VALUES (?,?,?,?,?,?)", row
        )

    # ── routing_table ────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routing_table (
            department      TEXT NOT NULL,
            priority_label  TEXT NOT NULL,
            reviewer_name   TEXT NOT NULL,
            reviewer_email  TEXT NOT NULL,
            PRIMARY KEY (department, priority_label)
        )
    """)
    for row in [
        ("HR",      "medium",   "Dr. Mona Khalil",  "mona.khalil@company.com"),
        ("HR",      "high",     "Dr. Mona Khalil",  "mona.khalil@company.com"),
        ("HR",      "critical", "Dr. Mona Khalil",  "mona.khalil@company.com"),
        ("IT",      "medium",   "Ismail Hesham",    "ismail.hesham@company.com"),
        ("IT",      "high",     "Ismail Hesham",    "ismail.hesham@company.com"),
        ("IT",      "critical", "Ismail Hesham",    "ismail.hesham@company.com"),
        ("Finance", "medium",   "Karim Mostafa",    "karim.mostafa@company.com"),
        ("Finance", "high",     "Karim Mostafa",    "karim.mostafa@company.com"),
        ("Finance", "critical", "Karim Mostafa",    "karim.mostafa@company.com"),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO routing_table VALUES (?,?,?,?)", row
        )

    # ── finance_expense_reports ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_expense_reports (
            report_id       TEXT PRIMARY KEY,
            employee_name   TEXT NOT NULL,
            date            TEXT NOT NULL,
            amount_egp      REAL NOT NULL,
            category        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            description     TEXT
        )
    """)
    for row in [
        ("EXP-001", "Ali Abdallah",  "2026-04-10", 1200.0,  "travel",   "approved",  "Cairo to Alexandria — client visit"),
        ("EXP-002", "Sara Hassan",   "2026-04-15", 450.0,   "supplies", "pending",   "Office supplies for HR dept"),
        ("EXP-003", "Omar Youssef",  "2026-04-20", 8750.0,  "equipment","pending",   "External monitor for WFH setup"),
        ("EXP-004", "Ali Abdallah",  "2026-05-01", 320.0,   "meals",    "approved",  "Team lunch — project kickoff"),
        ("EXP-005", "Sara Hassan",   "2026-05-03", 2100.0,  "travel",   "pending",   "Conference registration + travel"),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO finance_expense_reports VALUES (?,?,?,?,?,?,?)", row
        )

    # ── tooling_list ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tooling_list (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            department          TEXT NOT NULL,
            tool_name           TEXT NOT NULL,
            tool_category       TEXT NOT NULL,
            required            INTEGER NOT NULL DEFAULT 1,
            provisioning_owner  TEXT NOT NULL
        )
    """)
    for row in [
        ("IT",        "GitHub Enterprise",  "software", 1, "IT Admin"),
        ("IT",        "Jira",               "software", 1, "IT Admin"),
        ("IT",        "Slack",              "software", 1, "IT Admin"),
        ("IT",        "MacBook Pro 14\"",   "hardware", 1, "IT Admin"),
        ("IT",        "YubiKey",            "hardware", 1, "IT Admin"),
        ("HR",        "BambooHR",           "software", 1, "HR Admin"),
        ("HR",        "Slack",              "software", 1, "IT Admin"),
        ("HR",        "Zoom",               "software", 1, "IT Admin"),
        ("Finance",   "QuickBooks Online",  "software", 1, "Finance Admin"),
        ("Finance",   "Slack",              "software", 1, "IT Admin"),
        ("Finance",   "Zoom",               "software", 1, "IT Admin"),
        ("cross-dept","Slack",              "software", 1, "IT Admin"),
        ("cross-dept","Zoom",               "software", 1, "IT Admin"),
        ("cross-dept","Google Workspace",   "software", 1, "IT Admin"),
    ]:
        # Only insert if (department, tool_name) not already present
        cur.execute(
            "INSERT OR IGNORE INTO tooling_list (department, tool_name, tool_category, required, provisioning_owner) "
            "SELECT ?,?,?,?,? WHERE NOT EXISTS "
            "(SELECT 1 FROM tooling_list WHERE department=? AND tool_name=?)",
            (row[0], row[1], row[2], row[3], row[4], row[0], row[1])
        )

    conn.commit()
    conn.close()

    # Summary
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"office.db ready at: {DB_PATH}")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]} rows")
    conn.close()


if __name__ == "__main__":
    seed()
