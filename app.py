from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import sqlite3
from datetime import datetime
from reportlab.pdfgen import canvas
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from openpyxl import Workbook
from flask import send_file
import io

app = Flask(__name__)
app.secret_key = "vbet"

DB = "books.db"


def db():
    return sqlite3.connect(DB)

@app.route("/reports/vbet", methods=["GET", "POST"])

def report_vbet():

    conn = db()

    c = conn.cursor()

    data = []

    if request.method == "POST":

        start = request.form["start"]
        end = request.form["end"]

        data = c.execute("""
        SELECT books.name, purchases.vendor, purchases.qty,
               purchases.price, purchases.date
        FROM purchases
        JOIN books ON books.id = purchases.book_id
        WHERE date BETWEEN ? AND ?
        """, (start, end)).fetchall()

    return render_template("report_vbet.html", data=data)
@app.route("/reports/school", methods=["GET", "POST"])
def report_school():

    conn = db()
    c = conn.cursor()

    schools = c.execute("SELECT * FROM schools").fetchall()

    rows = []
    total = 0

    if request.method == "POST":

        school = request.form["school"]
        start = request.form["start"]
        end = request.form["end"]

        rows = c.execute("""
        SELECT books.name,
               SUM(sale_items.qty),
               sale_items.price,
               SUM(sale_items.qty * sale_items.price)

        FROM sale_items
        JOIN sales ON sales.id = sale_items.sale_id
        JOIN books ON books.id = sale_items.book_id

        WHERE sales.school_id=?
        AND date(sales.date) BETWEEN date(?) AND date(?)

        GROUP BY books.id, sale_items.price
        """, (school, start, end)).fetchall()

        total = sum([r[3] for r in rows])

    return render_template(
        "report_school.html",
        rows=rows,
        schools=schools,
        total=total
    )
@app.route("/reports/stock")
def report_stock():

    conn = db()
    c = conn.cursor()

    data = c.execute("""

    SELECT books.name,

    IFNULL(SUM(purchases.qty),0) as purchased,

    IFNULL((
        SELECT SUM(qty) FROM orders
        WHERE orders.book_id = books.id AND status='Approved'
    ),0) as distributed,

    IFNULL((
        SELECT SUM(qty) FROM sale_items
        WHERE sale_items.book_id = books.id
    ),0) as sold

    FROM books

    LEFT JOIN purchases ON purchases.book_id = books.id

    GROUP BY books.id

    """).fetchall()

    return render_template("report_stock.html", data=data)


@app.route("/reports")
def reports():
    return render_template("reports.html")

@app.route("/reject/<id>")
def reject(id):

    conn = db()
    c = conn.cursor()

    c.execute(
        "UPDATE orders SET status='Rejected' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/orders")

@app.route("/distribution")
def distribution():

    conn = db()
    c = conn.cursor()

    data = c.execute("""
    SELECT schools.name, books.name, orders.qty
    FROM orders
    JOIN schools ON schools.id = orders.school_id
    JOIN books ON books.id = orders.book_id
    WHERE orders.status = 'Approved'
    """).fetchall()

    conn.close()

    return render_template("distribution.html", data=data)# ---------------- DATABASE ----------------

def init_db():

    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        class TEXT,
        mrp INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS purchases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        vendor TEXT,
        price INTEGER,
        qty INTEGER,
        date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS vbet_inventory(
        book_id INTEGER PRIMARY KEY,
        stock INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS schools(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id INTEGER,
        book_id INTEGER,
        qty INTEGER,
        status TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS school_inventory(
        school_id INTEGER,
        book_id INTEGER,
        stock INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student TEXT,
        class TEXT,
        school_id INTEGER,
        category TEXT,
        total INTEGER,
        date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sale_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        book_id INTEGER,
        qty INTEGER,
        price INTEGER
    )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- LOGIN ----------------

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        if request.form["username"] == "admin" and request.form["password"] == "admin":

            session["user"] = "admin"
            return redirect("/dashboard")

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    conn = db()
    c = conn.cursor()

    revenue = c.execute("""
    SELECT SUM(total) FROM sales
    """).fetchone()[0]

    if revenue is None:
        revenue = 0

    low_stock = c.execute("""
    SELECT schools.name, books.name, school_inventory.stock
    FROM school_inventory
    JOIN books ON books.id = school_inventory.book_id
    JOIN schools ON schools.id = school_inventory.school_id
    WHERE stock < 10
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        revenue=revenue,
        low_stock=low_stock
    )


# ---------------- BOOKS ----------------

@app.route("/add_book", methods=["GET", "POST"])
def add_book():

    conn = db()
    c = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        cls = request.form["class"]
        mrp = request.form["mrp"]

        c.execute(
            "INSERT INTO books(name,class,mrp) VALUES(?,?,?)",
            (name, cls, mrp)
        )

        conn.commit()

        return redirect("/dashboard")

    return render_template("add_book.html")


# ---------------- PURCHASE ----------------
@app.route("/purchase", methods=["GET", "POST"])
def purchase():

    conn = db()
    c = conn.cursor()

    books = c.execute("SELECT * FROM books").fetchall()

    if request.method == "POST":

        print("FORM DATA:", request.form)

        bill_no = request.form.get("bill_no", "")
        narration = request.form.get("narration", "")

        book = int(request.form["book"])
        vendor = request.form["vendor"]
        price = int(request.form["price"])
        qty = int(request.form["qty"])

        date = datetime.now().strftime("%Y-%m-%d")

        # Save purchase
        c.execute("""
        INSERT INTO purchases(book_id,vendor,price,qty,date,bill_no,narration)
        VALUES(?,?,?,?,?,?,?)
        """, (book, vendor, price, qty, date, bill_no, narration))

        # Update inventory
        c.execute("""
        INSERT INTO vbet_inventory(book_id,stock)
        VALUES(?,?)
        ON CONFLICT(book_id)
        DO UPDATE SET stock = stock + ?
        """, (book, qty, qty))

        conn.commit()

        # redirect after save
        return redirect("/purchase")

    # 🔥 ALWAYS fetch purchases for display
    purchases = c.execute("""
    SELECT purchases.id, books.name, vendor, qty, price, bill_no, date, narration
    FROM purchases
    JOIN books ON books.id = purchases.book_id
    ORDER BY purchases.id DESC
    """).fetchall()
    vendors = c.execute("""
    SELECT DISTINCT vendor FROM purchases
    ORDER BY vendor
    """).fetchall()

    conn.close()
    

    return render_template(
        "purchase.html",
        books=books,
        purchases=purchases,
        vendors=vendors
    )
# ---------------- VBET INVENTORY ----------------

@app.route("/vbet_inventory")
def vbet_inventory():

    conn = db()
    c = conn.cursor()

    data = c.execute("""
    SELECT books.name, books.class, vbet_inventory.stock
    FROM vbet_inventory
    JOIN books ON books.id = vbet_inventory.book_id
    """).fetchall()

    pending_orders = c.execute("""
    SELECT orders.id, schools.name, books.name, orders.qty
    FROM orders
    JOIN schools ON schools.id = orders.school_id
    JOIN books ON books.id = orders.book_id
    WHERE orders.status = 'Pending'
    """).fetchall()

    challans = c.execute("""
    SELECT challan_no, school_name, qty, total, status, order_id
    FROM challans ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "vbet_inventory.html",
        data=data,
        pending_orders=pending_orders,
        challans=challans
    )
# ---------------- SCHOOLS ----------------
@app.route("/schools", methods=["GET", "POST"])
def schools():

    conn = db()
    c = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        address = request.form["address"]
        contact = request.form["contact_person"]
        phone = request.form["phone"]

        # ✅ validation
        if not name or not address or not contact or not phone:
            conn.close()
            return "❌ All fields are required"

        c.execute("""
        INSERT INTO schools(name,address,contact_person,phone)
        VALUES(?,?,?,?)
        """, (name, address, contact, phone))

        conn.commit()

        # ✅ redirect after insert (VERY IMPORTANT)
        conn.close()
        return redirect("/schools")

    # ✅ GET request
    schools = c.execute("""
    SELECT * FROM schools ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("schools.html", schools=schools)

##########partial order###########

@app.route("/approve_order", methods=["POST"])
def approve_order():

    conn = db()
    c = conn.cursor()

    order_id = request.form["order_id"]
    approve_qty = int(request.form["qty"])

    order = c.execute("""
    SELECT school_id, book_id, qty, approved_qty
    FROM orders WHERE id=?
    """, (order_id,)).fetchone()

    if not order:
        conn.close()
        return "❌ Order not found"

    school, book, req_qty, prev_approved = order
    prev_approved = prev_approved or 0

    if approve_qty <= 0:
        return "❌ Invalid qty"

    if approve_qty + prev_approved > req_qty:
        return "❌ Cannot exceed order qty"

    stock = c.execute("""
    SELECT stock FROM vbet_inventory WHERE book_id=?
    """, (book,)).fetchone()

    if not stock or stock[0] < approve_qty:
        return "❌ Not enough stock"

    # 🔥 reduce stock
    c.execute("UPDATE vbet_inventory SET stock=stock-? WHERE book_id=?", (approve_qty, book))

    # 🔥 add school stock
    school_stock = c.execute("""
    SELECT stock FROM school_inventory
    WHERE school_id=? AND book_id=?
    """, (school, book)).fetchone()

    if school_stock:
        c.execute("""
        UPDATE school_inventory
        SET stock=stock+?
        WHERE school_id=? AND book_id=?
        """, (approve_qty, school, book))
    else:
        c.execute("""
        INSERT INTO school_inventory VALUES(?,?,?)
        """, (school, book, approve_qty))

    # 🔥 update order
    new_approved = prev_approved + approve_qty

    status = "Approved" if new_approved == req_qty else "Partially Approved"

    c.execute("""
    UPDATE orders SET status=?, approved_qty=?
    WHERE id=?
    """, (status, new_approved, order_id))

    # 🔥 GET PURCHASE PRICE → SELLING RATE
    purchase_price = c.execute("""
    SELECT price FROM purchases
    WHERE book_id=?
    ORDER BY id DESC LIMIT 1
    """, (book,)).fetchone()

    purchase_price = purchase_price[0] if purchase_price else 0
    rate = int(purchase_price * 0.9)

    total = rate * approve_qty

    # 🔥 challan number
    last = c.execute("SELECT COUNT(*) FROM challans").fetchone()[0]
    challan_no = f"CH-{last+1:04d}"

    # 🔥 school info
    school_data = c.execute("""
    SELECT name, address FROM schools WHERE id=?
    """, (school,)).fetchone()

    school_name, address = school_data

    # 🔥 insert challan
    c.execute("""
    INSERT INTO challans(
        order_id, school_id, school_name, address,
        book_id, qty, rate, total, date, challan_no, status
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (
        order_id,
        school,
        school_name,
        address,
        book,
        approve_qty,
        rate,
        total,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        challan_no,
        "Dispatched"
    ))

    conn.commit()
    conn.close()

    return redirect("/orders")

##challan #######
@app.route("/challan/<int:order_id>")
def challan(order_id):

    conn = db()
    c = conn.cursor()

    data = c.execute("""
    SELECT challans.challan_no,
           schools.name,
           schools.address,
           books.name,
           challans.qty,
           challans.rate,
           challans.total,
           challans.date

    FROM challans
    JOIN schools ON schools.id = challans.school_id
    JOIN books ON books.id = challans.book_id

    WHERE challans.order_id=?
    """, (order_id,)).fetchall()

    conn.close()

    file = f"challan_{order_id}.pdf"
    doc = SimpleDocTemplate(file, pagesize=A4)

    styles = getSampleStyleSheet()
    styles = getSampleStyleSheet()
    elements = []

    # ===== HEADER =====
    elements.append(Paragraph("<b>VBET EDUCATION TRUST</b>", styles['Title']))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("<b>DELIVERY CHALLAN</b>", styles['Heading2']))
    elements.append(Spacer(1, 20))

    # ===== META INFO =====
    info_data = [
        ["Challan No:", data[0][0], "Date:", data[0][7]],
        ["School:", data[0][1], "", ""],
        ["Address:", data[0][2], "", ""]
    ]

    info_table = Table(info_data, colWidths=[100, 200, 80, 150])
    elements.append(info_table)
    elements.append(Spacer(1, 25))

    # ===== TABLE =====
    table_data = [["Book", "Qty", "Rate (₹)", "Amount (₹)"]]

    grand_total = 0

    for row in data:
        table_data.append([
            row[3],
            row[4],
            row[5],
            row[6]
        ])
        grand_total += row[6]

    table_data.append(["", "", "Total", grand_total])

    table = Table(table_data, colWidths=[200, 80, 100, 120])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 30))

    # ===== TOTAL =====
    elements.append(Paragraph(f"<b>Total Amount:</b> ₹{grand_total}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # ===== SIGN =====
    elements.append(Paragraph("Authorized Signatory", styles['Normal']))



    doc.build(elements)

    return send_file(file, as_attachment=True)

# ---------------- ORDERS ----------------
@app.route("/orders", methods=["GET", "POST"])
def orders():

    conn = db()
    c = conn.cursor()

    # ---------------- CREATE ORDER ----------------
    if request.method == "POST":

        school = request.form["school"]
        book = request.form["book"]
        qty = int(request.form["qty"])

        c.execute("""
        INSERT INTO orders(school_id, book_id, qty, status, approved_qty)
        VALUES(?,?,?,'Pending',0)
        """, (school, book, qty))

        conn.commit()
        conn.close()

        return redirect("/orders")   # 🔥 MUST

    # ---------------- FETCH ----------------
    schools = c.execute("SELECT * FROM schools").fetchall()
    books = c.execute("SELECT * FROM books").fetchall()

    orders = c.execute("""
    SELECT 
        orders.id,
        schools.name,
        books.name,
        orders.qty,
        orders.status,
        IFNULL(orders.approved_qty, 0),
        IFNULL((
            SELECT received_qty 
            FROM challans 
            WHERE challans.order_id = orders.id 
            ORDER BY id DESC LIMIT 1
        ), 0)
    FROM orders
    JOIN schools ON schools.id = orders.school_id
    JOIN books ON books.id = orders.book_id
    ORDER BY orders.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "orders.html",
        orders=orders,
        schools=schools,
        books=books
    )

@app.route("/receive/<int:order_id>", methods=["GET","POST"])
def receive(order_id):

    conn = db()
    c = conn.cursor()

    challan = c.execute("""
    SELECT id, school_name, qty
    FROM challans
    WHERE order_id=?
    ORDER BY id DESC LIMIT 1
    """, (order_id,)).fetchone()

    if not challan:
        return "❌ No challan found"

    challan_id = challan[0]

    if request.method == "POST":

        qty = int(request.form["received_qty"])
        person = request.form["received_by"]

        c.execute("""
        UPDATE challans
        SET received_qty=?, received_by=?, received_date=?, status='Received'
        WHERE id=?
        """, (
            qty,
            person,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            challan_id
        ))

        conn.commit()
        conn.close()

        return redirect("/orders")

    conn.close()

    return render_template(
        "receive.html",
        challan=challan,
        id=challan_id
    )

# ---------------- LIVE SEARCH ----------------

@app.route("/search_books")
def search_books():

    school = request.args.get("school")
    term = request.args.get("term")

    conn = db()
    c = conn.cursor()

    books = c.execute("""
    SELECT books.id,books.name,books.mrp,school_inventory.stock
    FROM school_inventory
    JOIN books ON books.id=school_inventory.book_id
    WHERE school_inventory.school_id=?
    AND books.name LIKE ?
    """, (school, f"%{term}%")).fetchall()

    conn.close()

    return jsonify(books)


# ---------------- BILLING ----------------

@app.route("/billing", methods=["GET", "POST"])
def billing():

    conn = db()
    c = conn.cursor()

    schools = c.execute("SELECT * FROM schools").fetchall()

    school = request.args.get("school")

    books = []

    if school:
        books = c.execute("""
        SELECT books.id, books.name, books.mrp, school_inventory.stock
        FROM school_inventory
        JOIN books ON books.id = school_inventory.book_id
        WHERE school_inventory.school_id=?
        """, (school,)).fetchall()

    if request.method == "POST":

        student = request.form["student"]
        cls = request.form["class"]
        school = request.form["school"]
        category = request.form["category"]
        discount = int(request.form.get("discount", 0))

        total = 0

        c.execute("""
        INSERT INTO sales(student,class,school_id,category,total,date)
        VALUES(?,?,?,?,?,?)
        """, (student, cls, school, category, 0, datetime.now().strftime("%Y-%m-%d")))

        sale_id = c.lastrowid

        for key in request.form:

            if "qty_" in key:

                book_id = key.split("_")[1]
                qty = int(request.form[key])

                if qty > 0:

                    price = c.execute(
                        "SELECT mrp FROM books WHERE id=?",
                        (book_id,)
                    ).fetchone()[0]

                    total += qty * price

                    c.execute("""
                    INSERT INTO sale_items(sale_id,book_id,qty,price)
                    VALUES(?,?,?,?)
                    """, (sale_id, book_id, qty, price))

                    # reduce school stock
                    c.execute("""
                    UPDATE school_inventory
                    SET stock = stock - ?
                    WHERE school_id=? AND book_id=?
                    """, (qty, school, book_id))

        # apply discount
        total -= discount

        # EWS logic
        if category == "EWS":
            final = 0
        else:
            final = total

        c.execute(
            "UPDATE sales SET total=? WHERE id=?",
            (final, sale_id)
        )

        conn.commit()

        return redirect(f"/receipt/{sale_id}")

    return render_template(
        "billing.html",
        schools=schools,
        books=books
    )
# ---------------- RECEIPT ----------------



@app.route("/receipt/<int:sale_id>")
def receipt(sale_id):

    conn = db()
    c = conn.cursor()

    sale = c.execute("""
    SELECT student, class, total, date, school_id, category
    FROM sales WHERE id=?
    """, (sale_id,)).fetchone()

    school = c.execute(
        "SELECT name FROM schools WHERE id=?",
        (sale[4],)
    ).fetchone()[0]

    items = c.execute("""
    SELECT books.name, qty, price
    FROM sale_items
    JOIN books ON books.id = sale_items.book_id
    WHERE sale_id=?
    """, (sale_id,)).fetchall()

    conn.close()

    category = sale[5]  # ✅ get directly

    file = f"invoice_{sale_id}.pdf"
    doc = SimpleDocTemplate(file, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    # ---------------- HEADER ----------------
    elements.append(Paragraph("<b>VBET EDUCATION TRUST</b>", styles['Title']))
    elements.append(Paragraph("Tax Invoice / Bill", styles['Normal']))
    elements.append(Spacer(1, 10))

    # ---------------- INFO ----------------
    info = [
        ["Receipt No:", sale_id, "Date:", sale[3]],
        ["Student:", sale[0], "Class:", sale[1]],
        ["School:", school, "", ""]
    ]

    elements.append(Table(info, colWidths=[100, 150, 80, 150]))
    elements.append(Spacer(1, 20))

    # ---------------- ITEMS TABLE ----------------
    data = [["Description", "Qty", "Rate", "Amount"]]

    total = 0

    for item in items:
        amt = item[1] * item[2]
        total += amt

        data.append([
            item[0],
            item[1],
            f"₹{item[2]}",
            f"₹{amt}"
        ])

    data.append(["", "", "TOTAL", f"₹{total}"])

    table = Table(data, colWidths=[220, 80, 80, 100])

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ---------------- FOOTER ----------------
    if category == "EWS":
        elements.append(Paragraph("<b>EWS Category - Paid by School</b>", styles['Normal']))
        elements.append(Paragraph("<b>Total Amount: ₹0</b>", styles['Normal']))
    else:
        elements.append(Paragraph(f"<b>Total Amount: ₹{total}</b>", styles['Normal']))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Amount in Words:", styles['Normal']))
    elements.append(Paragraph("Rupees Only", styles['Normal']))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Authorized Signatory", styles['Normal']))

    doc.build(elements)

    return send_file(file, as_attachment=True)



@app.route("/export/school_report", methods=["POST"])
def export_school_report():

    conn = db()
    c = conn.cursor()

    school = request.form["school"]
    start = request.form["start"]
    end = request.form["end"]

    rows = c.execute("""
    SELECT books.name,
           SUM(sale_items.qty),
           sale_items.price,
           SUM(sale_items.qty * sale_items.price)

    FROM sale_items
    JOIN sales ON sales.id = sale_items.sale_id
    JOIN books ON books.id = sale_items.book_id

    WHERE sales.school_id=?
    AND date(sales.date) BETWEEN date(?) AND date(?)

    GROUP BY books.id, sale_items.price
    """, (school, start, end)).fetchall()

    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "School Report"

    # headers
    ws.append(["Book", "Quantity", "Price", "Total"])

    total = 0

    for r in rows:
        ws.append([r[0], r[1], r[2], r[3]])
        total += r[3]

    # grand total row
    ws.append([])
    ws.append(["", "", "Grand Total", total])

    # save to memory
    file = io.BytesIO()
    wb.save(file)
    file.seek(0)

    return send_file(
        file,
        as_attachment=True,
        download_name="school_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)