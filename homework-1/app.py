"""
Lakebase-powered AI Support App.
Five operations: view all tickets, view a ticket's messages,
create a ticket, add a message, update a ticket's status.
Bonuses: priority, status filtering, input validation, statistics.
"""
from flask import Flask, request, redirect, url_for, render_template, flash
from psycopg.rows import dict_row

from db import get_conn

app = Flask(__name__)
app.secret_key = "dev-only-flash-key"  # only signs flash() messages, not auth

VALID_STATUSES = ("open", "in_progress", "resolved")
VALID_PRIORITIES = ("low", "medium", "high")


@app.route("/")
def index():
    status_filter = request.args.get("status", "")
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        if status_filter in VALID_STATUSES:
            cur.execute(
                "SELECT * FROM tickets WHERE status = %s ORDER BY created_at DESC",
                (status_filter,),
            )
        else:
            cur.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        tickets = cur.fetchall()

        cur.execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")
        stats = {r["status"]: r["n"] for r in cur.fetchall()}

    return render_template(
        "index.html",
        tickets=tickets,
        stats=stats,
        status_filter=status_filter,
        statuses=VALID_STATUSES,
        priorities=VALID_PRIORITIES,
    )


@app.route("/ticket/<int:ticket_id>")
def ticket_detail(ticket_id):
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id,))
        ticket = cur.fetchone()
        if ticket is None:
            flash("That ticket no longer exists.", "error")
            return redirect(url_for("index"))
        cur.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at",
            (ticket_id,),
        )
        messages = cur.fetchall()
    return render_template(
        "detail.html", ticket=ticket, messages=messages, statuses=VALID_STATUSES
    )


@app.route("/ticket/create", methods=["POST"])
def create_ticket():
    title = (request.form.get("title") or "").strip()
    created_by = (request.form.get("created_by") or "").strip()
    priority = request.form.get("priority", "medium")

    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("index"))
    if not created_by:
        flash("Please say who is creating the ticket.", "error")
        return redirect(url_for("index"))
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tickets (title, created_by, priority) VALUES (%s, %s, %s)",
            (title, created_by, priority),
        )
    flash("Ticket created.", "ok")
    return redirect(url_for("index"))


@app.route("/ticket/<int:ticket_id>/message", methods=["POST"])
def add_message(ticket_id):
    text = (request.form.get("message_text") or "").strip()
    author = (request.form.get("author") or "").strip()
    if not text or not author:
        flash("Both a message and an author are required.", "error")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ticket_messages (ticket_id, message_text, author) "
            "VALUES (%s, %s, %s)",
            (ticket_id, text, author),
        )
    flash("Message added.", "ok")
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/ticket/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    status = request.form.get("status")
    if status not in VALID_STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE tickets SET status = %s WHERE ticket_id = %s",
            (status, ticket_id),
        )
    flash("Status updated.", "ok")
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)