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
    # `email` is the canonical (trusted) identifier — matches the verified sender
    # `task.requester_email`. Lookups still key on employee_name for now; switching
    # to email-keyed, own-data-only lookups is Phase-4 authorization work (P1-4b).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hr_leave_balances (
            employee_name       TEXT NOT NULL,
            email               TEXT NOT NULL,
            leave_type          TEXT NOT NULL,
            total_entitlement   INTEGER NOT NULL,
            used_days           INTEGER NOT NULL DEFAULT 0,
            remaining_days      INTEGER NOT NULL,
            policy_note         TEXT,
            PRIMARY KEY (employee_name, leave_type)
        )
    """)
    for row in [
        ("Ahmed Samer",     "ahmedsamersayed22@gmail.com",  "annual", 21,  5, 16, "Unused days above 5 cannot be carried to next year"),
        ("Ahmed Samer",     "ahmedsamersayed22@gmail.com",  "sick",   10,  2,  8, "Requires medical certificate after 3 consecutive days"),
        ("Ali Abdallah",    "aliabdalla2110@gmail.com",     "annual", 21,  8, 13, "Unused days above 5 cannot be carried to next year"),
        ("Ali Abdallah",    "aliabdalla2110@gmail.com",     "sick",   10,  1,  9, "Requires medical certificate after 3 consecutive days"),
        ("Hassan Mohammed", "ahmed2208211@miuegypt.edu.eg", "annual", 21, 12,  9, "Unused days above 5 cannot be carried to next year"),
        ("Hassan Mohammed", "ahmed2208211@miuegypt.edu.eg", "sick",   10,  3,  7, "Requires medical certificate after 3 consecutive days"),
        ("Ismail Hesham",   "simomemo123@hotmail.com",      "annual", 21,  6, 15, "Unused days above 5 cannot be carried to next year"),
        ("Ismail Hesham",   "simomemo123@hotmail.com",      "sick",   10,  0, 10, "Requires medical certificate after 3 consecutive days"),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO hr_leave_balances "
            "(employee_name, email, leave_type, total_entitlement, used_days, remaining_days, policy_note) "
            "VALUES (?,?,?,?,?,?,?)", row
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
    # All escalations route to the current reviewer (the demo owner). Cover every
    # department/priority combo so a reviewer is always found.
    for _dept in ("IT", "HR", "Finance", "cross-dept", "Other"):
        for _prio in ("low", "medium", "high", "critical"):
            cur.execute(
                "INSERT OR IGNORE INTO routing_table VALUES (?,?,?,?)",
                (_dept, _prio, "Ismail Hesham", "simomemo123@hotmail.com"),
            )

    # ── finance_expense_reports ──────────────────────────────────────────────
    # Schema carries the fields the Expense Tracker's AnomalyChecker needs:
    #   employee_id + submitted_at  → duplicate-submission check
    #   has_receipt                 → missing-receipt check
    #   line_items (JSON text)      → line-item policy check
    # Seed data deliberately exercises each anomaly type (see notes per row).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_expense_reports (
            report_id       TEXT PRIMARY KEY,
            employee_id     TEXT NOT NULL,
            employee_name   TEXT NOT NULL,
            email           TEXT NOT NULL,
            date            TEXT NOT NULL,
            submitted_at    TEXT NOT NULL,
            amount_egp      REAL NOT NULL,
            category        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            has_receipt     INTEGER NOT NULL DEFAULT 1,
            line_items      TEXT NOT NULL DEFAULT '[]',
            approval_date   TEXT,
            payment_eta     TEXT,
            description     TEXT
        )
    """)
    _EXP_COLS = ("report_id, employee_id, employee_name, email, date, submitted_at, amount_egp, "
                 "category, status, has_receipt, line_items, approval_date, payment_eta, description")
    for row in [
        # clean / approved
        ("EXP-001", "EMP-004", "Ismail Hesham", "simomemo123@hotmail.com", "2026-05-10", "2026-05-10T09:00:00", 1200.0, "travel", "approved", 1,
         '[{"description":"Train ticket Cairo-Alex","category":"travel","amount_egp":1200}]',
         "2026-05-12", "2026-05-20", "Cairo to Alexandria — client visit"),
        ("EXP-002", "EMP-002", "Ali Abdallah", "aliabdalla2110@gmail.com", "2026-05-15", "2026-05-15T10:30:00", 450.0, "supplies", "pending", 1,
         '[{"description":"Office supplies","category":"supplies","amount_egp":450}]',
         None, None, "Office supplies for the finance desk"),
        # missing-receipt anomaly: amount > 500 EGP and has_receipt = 0
        ("EXP-003", "EMP-004", "Ismail Hesham", "simomemo123@hotmail.com", "2026-05-20", "2026-05-20T14:00:00", 8750.0, "equipment", "pending", 0,
         '[{"description":"External monitor","category":"equipment","amount_egp":8750}]',
         None, None, "External monitor for WFH setup"),
        ("EXP-004", "EMP-003", "Hassan Mohammed", "ahmed2208211@miuegypt.edu.eg", "2026-05-01", "2026-05-01T13:00:00", 320.0, "meals", "approved", 1,
         '[{"description":"Team lunch","category":"meals","amount_egp":320}]',
         "2026-05-02", "2026-05-10", "Team lunch — project kickoff"),
        # policy-violation anomaly: an 'entertainment' line item (non-reimbursable)
        ("EXP-005", "EMP-004", "Ismail Hesham", "simomemo123@hotmail.com", "2026-05-03", "2026-05-03T11:00:00", 2100.0, "travel", "pending", 1,
         '[{"description":"Conference registration","category":"travel","amount_egp":1500},'
         '{"description":"Client dinner","category":"entertainment","amount_egp":600}]',
         None, None, "Conference registration + travel"),
        # duplicate-submission anomaly: same employee + amount as EXP-001, within 30 days
        ("EXP-006", "EMP-004", "Ismail Hesham", "simomemo123@hotmail.com", "2026-05-25", "2026-05-25T09:30:00", 1200.0, "travel", "pending", 1,
         '[{"description":"Train ticket Cairo-Alex","category":"travel","amount_egp":1200}]',
         None, None, "Cairo to Alexandria — follow-up visit"),
    ]:
        cur.execute(
            f"INSERT OR IGNORE INTO finance_expense_reports ({_EXP_COLS}) "
            f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row
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

    # ── task_queue ───────────────────────────────────────────────────────────
    # Async hand-off table the Onboarding Coordinator's QueueInjector writes to
    # (one access-provisioning task per tool). NOTE: nothing consumes this yet —
    # the downstream `account_manager` agent does not exist (tracked as P2-14).
    # The table exists so injection succeeds and onboarding completes instead of
    # escalating; wiring a consumer is Phase-2 work.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            task_id         TEXT PRIMARY KEY,
            envelope_id     TEXT,
            target_agent    TEXT,
            envelope_json   TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TEXT,
            priority_score  INTEGER
        )
    """)

    # ── operational_metrics ──────────────────────────────────────────────────
    # Source figures for the Report Generator, so produced reports contain data.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operational_metrics (
            department  TEXT NOT NULL,
            period      TEXT NOT NULL,
            metric      TEXT NOT NULL,
            value       TEXT NOT NULL,
            PRIMARY KEY (department, period, metric)
        )
    """)
    for row in [
        ("Finance",    "Q2 2026", "Total revenue (EGP)",     "4,200,000"),
        ("Finance",    "Q2 2026", "Total expenses (EGP)",    "1,250,000"),
        ("Finance",    "Q2 2026", "Net profit (EGP)",        "2,950,000"),
        ("Finance",    "Q2 2026", "Outstanding invoices",    "18"),
        ("IT",         "Q2 2026", "Tickets resolved",        "342"),
        ("IT",         "Q2 2026", "Avg resolution time (h)", "6.4"),
        ("IT",         "Q2 2026", "System uptime (%)",       "99.7"),
        ("HR",         "Q2 2026", "Headcount",               "48"),
        ("HR",         "Q2 2026", "New hires",               "6"),
        ("HR",         "Q2 2026", "Attrition (%)",           "4.2"),
        ("cross-dept", "Q2 2026", "Active projects",         "12"),
        ("cross-dept", "Q2 2026", "On-time delivery (%)",    "88"),
    ]:
        cur.execute("INSERT OR IGNORE INTO operational_metrics VALUES (?,?,?,?)", row)

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
