import os, sqlite3, uuid, hmac, secrets
from functools import wraps
from flask import Flask, g, jsonify, request, session, redirect, render_template, send_from_directory, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
DB = "shop.db"
UPLOADS = os.path.join("static", "uploads")
os.makedirs(UPLOADS, exist_ok=True)
CATEGORIES = ("Perfumes", "Jewellery", "Gift Sets")

SCHEMA = """
create table if not exists products(id integer primary key, name text, category text, brand text,
  gender text, price integer, options text, image text, in_stock integer default 1, description text default '');
create table if not exists consults(id integer primary key, name text, phone text, message text,
  created text default current_timestamp);
create table if not exists orders(id integer primary key, product_id integer, product_name text,
  option text, qty integer, created text default current_timestamp);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()

with sqlite3.connect(DB) as c:
    c.executescript(SCHEMA)
    if "description" not in [r[1] for r in c.execute("pragma table_info(products)")]:
        c.execute("alter table products add column description text default ''")
    c.execute("update products set category='Jewellery' where category='Jewelry'")

if ADMIN_PASSWORD == "change-me" or app.secret_key == "change-me":
    print("WARNING: default admin password or secret key in use. Set ADMIN_PASSWORD and SECRET_KEY before going online.")

# ---------- public ----------
@app.route("/")
def home():
    return send_from_directory("static", "index.html")

@app.route("/api/products")
def products():
    rows = db().execute("select * from products where in_stock=1 order by id desc").fetchall()
    return jsonify([{"id": r["id"], "n": r["name"], "c": r["category"], "b": r["brand"], "g": r["gender"],
                     "p": r["price"], "d": r["description"] or "",
                     "o": [o.strip() for o in (r["options"] or "").split(",") if o.strip()] or ["Standard"],
                     "img": ("/static/uploads/" + r["image"]) if r["image"] else ""} for r in rows])

@app.route("/api/consult", methods=["POST"])
def consult():
    d = request.get_json(silent=True) or {}
    name, phone = str(d.get("name", ""))[:80].strip(), str(d.get("phone", ""))[:30].strip()
    if not name or not phone:
        abort(400)
    db().execute("insert into consults(name,phone,message) values(?,?,?)", (name, phone, str(d.get("message", ""))[:500]))
    db().commit()
    return jsonify(ok=True)

@app.route("/api/order", methods=["POST"])
def order():
    d = request.get_json(silent=True) or {}
    p = db().execute("select * from products where id=?", (d.get("product_id"),)).fetchone()
    if not p:
        abort(400)
    try:
        qty = max(1, min(int(d.get("qty", 1)), 50))
    except (TypeError, ValueError):
        qty = 1
    db().execute("insert into orders(product_id,product_name,option,qty) values(?,?,?,?)",
                 (p["id"], p["name"], str(d.get("option", ""))[:40], qty))
    db().commit()
    return jsonify(ok=True)

# ---------- admin ----------
def admin_only(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*a, **k)
    return w

def check_csrf():
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
        abort(403)

def save_image():
    for file in request.files.getlist("image"):
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in {"jpg", "jpeg", "png", "webp"}:
                abort(400)
            name = uuid.uuid4().hex + "." + ext
            file.save(os.path.join(UPLOADS, name))
            return name
    return ""

def remove_image(name):
    if name:
        try:
            os.remove(os.path.join(UPLOADS, name))
        except OSError:
            pass

def fields():
    f = request.form
    try:
        price = max(0, int(float(f["price"])))
    except ValueError:
        abort(400)
    return (f["name"][:100].strip(), f["category"] if f["category"] in CATEGORIES else CATEGORIES[0],
            f["brand"][:50].strip(), f["gender"] if f["gender"] in ("Women", "Men", "Unisex") else "Unisex",
            price, f.get("options", "")[:200], f.get("description", "")[:1000])

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect("/admin")
        err = "Wrong password."
    return render_template("login.html", err=err)

@app.route("/admin/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/admin/login")

@app.route("/admin")
@admin_only
def admin():
    q = db()
    return render_template("admin.html", csrf=session["csrf"],
        products=q.execute("select * from products order by id desc").fetchall(),
        orders=q.execute("select * from orders order by id desc limit 50").fetchall(),
        consults=q.execute("select * from consults order by id desc limit 50").fetchall())

@app.route("/admin/add", methods=["POST"])
@admin_only
def add():
    check_csrf()
    n, c, b, g_, p, o, d = fields()
    db().execute("insert into products(name,category,brand,gender,price,options,description,image) values(?,?,?,?,?,?,?,?)",
                 (n, c, b, g_, p, o, d, save_image()))
    db().commit()
    return redirect("/admin")

@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_only
def edit(pid):
    p = db().execute("select * from products where id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    if request.method == "POST":
        check_csrf()
        n, c, b, g_, pr, o, d = fields()
        new = save_image()
        if new:
            remove_image(p["image"])
        db().execute("update products set name=?,category=?,brand=?,gender=?,price=?,options=?,description=?,image=? where id=?",
                     (n, c, b, g_, pr, o, d, new or p["image"], pid))
        db().commit()
        return redirect("/admin")
    return render_template("edit.html", p=p, csrf=session["csrf"])

@app.route("/admin/stock/<int:pid>", methods=["POST"])
@admin_only
def stock(pid):
    check_csrf()
    db().execute("update products set in_stock = 1 - in_stock where id=?", (pid,))
    db().commit()
    return redirect("/admin")

@app.route("/admin/delete/<int:pid>", methods=["POST"])
@admin_only
def delete(pid):
    check_csrf()
    p = db().execute("select image from products where id=?", (pid,)).fetchone()
    if p:
        remove_image(p["image"])
    db().execute("delete from products where id=?", (pid,))
    db().commit()
    return redirect("/admin")

if __name__ == "__main__":
    app.run(debug=False, port=5000)