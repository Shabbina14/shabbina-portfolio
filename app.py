# app.py
from flask import Flask, render_template, request, redirect, url_for, session
import pymysql

app = Flask(__name__)
app.secret_key = 'rahasia'

def get_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='',
        db='db_destinasiwisata',
        cursorclass=pymysql.cursors.DictCursor
    )

@app.template_filter('format_price')
def format_price(value):
    try:
        return f"{int(value):,}".replace(",", ".")
    except:
        return value

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        if user:
            session['username'] = user['username']
            session['fullname'] = user['fullname']
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (fullname, username, password) VALUES (%s, %s, %s)", (fullname, username, password))
        db.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return render_template('logout.html')

@app.route('/')
def index():
    if 'username' in session:
        db = get_db()
        cursor = db.cursor()

        # Rekomendasi tetap
        cursor.execute("""
        SELECT d.*
        FROM rekomendasi r
        JOIN destinasi d ON r.Place_Id = d.Place_Id
        ORDER BY r.Place_Id ASC
        LIMIT 25 """)
        rekomendasi = cursor.fetchall()
        for row in rekomendasi:
            row['is_favorit'] = True

        # Destinasi acak
        cursor.execute("SELECT Place_Id FROM rekomendasi")
        rekom_ids = set(row['Place_Id'] for row in cursor.fetchall())
        cursor.execute("SELECT * FROM destinasi ORDER BY RAND() LIMIT 15")
        destinasi_acak = cursor.fetchall()
        for d in destinasi_acak:
            d['is_favorit'] = d['Place_Id'] in rekom_ids

        cursor.execute("SELECT DISTINCT Category FROM destinasi WHERE Category IS NOT NULL AND Category != ''")
        kategori_list = [row['Category'] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT City FROM destinasi WHERE City IS NOT NULL AND City != ''")
        kota_list = [row['City'] for row in cursor.fetchall()]

        return render_template(
            'home.html',
            username=session['username'],
            rekomendasi=rekomendasi,
            destinasi_acak=destinasi_acak,
            kategori_list=kategori_list,
            kota_list=kota_list
        )
    else:
        return render_template('homepage.html')


@app.route('/filter')
def filter():
    kategori = request.args.get('kategori')
    kota = request.args.get('kota')
    harga_max = request.args.get('harga_max')
    query = "SELECT * FROM destinasi WHERE 1=1"
    values = []

    if kategori:
        query += " AND Category = %s"
        values.append(kategori)
    if kota:
        query += " AND City = %s"
        values.append(kota)
    if harga_max:
        query += " AND Price <= %s"
        values.append(harga_max)

    query += " LIMIT 10"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, values)
    hasil = cursor.fetchall()

    cursor.execute("SELECT Place_Id FROM rekomendasi")
    rekom_ids = set(str(row['Place_Id']) for row in cursor.fetchall())

    for row in hasil:
        row['is_favorit'] = str(row['Place_Id']) in rekom_ids

    filter_keterangan = ""
    if kategori or kota or harga_max:
        bagian = []
        if kategori:
            bagian.append(f"kategori <b style='color:maroon'>{kategori}</b>")
        if kota:
            bagian.append(f"kota <b style='color:maroon'>{kota}</b>")
        if harga_max:
            bagian.append(f"harga maksimal <b style='color:maroon'>Rp{harga_max}</b>")
        gabung = " di ".join(bagian[:2]) if len(bagian) >= 2 else bagian[0]
        if len(bagian) == 3:
            gabung += " dengan " + bagian[2]
        filter_keterangan = f"Menampilkan destinasi {gabung}"

    return render_template('filtered_results.html', hasil=hasil, rekomendasi_ids=rekom_ids, keterangan=filter_keterangan)

@app.route('/search')
def search():
    query = request.args.get('query', '').lower()
    if not query:
        return redirect(url_for('index'))

    db = get_db()
    cursor = db.cursor()
    sql = """
        SELECT * FROM destinasi 
        WHERE LOWER(Place_Name) LIKE %s 
           OR LOWER(City) LIKE %s 
           OR LOWER(Category) LIKE %s 
           OR LOWER(Description) LIKE %s
    """
    like_query = f"%{query}%"
    cursor.execute(sql, (like_query, like_query, like_query, like_query))
    results = cursor.fetchall()

    cursor.execute("SELECT Place_Id FROM rekomendasi")
    rekom_ids = set(str(row['Place_Id']) for row in cursor.fetchall())

    for row in results:
        row['is_favorit'] = str(row['Place_Id']) in rekom_ids

    return render_template("hasil_pencarian.html", hasil=results, query=query, rekomendasi_ids=rekom_ids)

@app.route('/detail/<place_id>', methods=['GET', 'POST'])
def detail(place_id):
    db = get_db()
    cursor = db.cursor()

    # Ambil detail destinasi
    cursor.execute("SELECT * FROM destinasi WHERE Place_Id = %s", (place_id,))
    detail = cursor.fetchone()

    if not detail:
        return "Destinasi tidak ditemukan", 404

    # Ambil komentar, maksimal 3 kecuali jika 'all=true'
    show_all = request.args.get('all') == 'true'
    if show_all:
        cursor.execute("SELECT * FROM komentar WHERE Place_Id = %s ORDER BY created_at DESC", (place_id,))
    else:
        cursor.execute("SELECT * FROM komentar WHERE Place_Id = %s ORDER BY created_at DESC LIMIT 3", (place_id,))
    komentar_list = cursor.fetchall()

    # Jika user mengirim komentar
    if request.method == 'POST' and 'username' in session:
        komentar = request.form['komentar']
        rating = request.form['rating']
        username = session['username']
        cursor.execute("""
            INSERT INTO komentar (Place_Id, username, isi, rating, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (place_id, username, komentar, rating))
        db.commit()
        return redirect(url_for('detail', place_id=place_id, all='true' if show_all else None))

    return render_template('detail.html', detail=detail, komentar_list=komentar_list, show_all=show_all)

@app.route('/semua_destinasi')
def semua_destinasi():
    if 'username' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM destinasi")
    semua = cursor.fetchall()

    cursor.execute("SELECT Place_Id FROM rekomendasi")
    rekom_ids = set(str(row['Place_Id']) for row in cursor.fetchall())

    for d in semua:
        d['is_favorit'] = str(d['Place_Id']) in rekom_ids

    return render_template("semua_destinasi.html", semua=semua, rekomendasi_ids=rekom_ids)

@app.route('/wishlist')
def wishlist():
    if 'username' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM wishlist w JOIN destinasi d ON w.Place_Id = d.Place_Id WHERE w.username = %s", (session['username'],))
    items = cursor.fetchall()
    return render_template('wishlist.html', items=items)

@app.route('/add_wishlist/<int:place_id>')
def add_wishlist(place_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT IGNORE INTO wishlist (username, Place_Id) VALUES (%s, %s)", (session['username'], place_id))
    db.commit()
    return redirect(url_for('wishlist'))

@app.route('/remove_wishlist/<int:place_id>')
def remove_wishlist(place_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM wishlist WHERE username = %s AND Place_Id = %s", (session['username'], place_id))
    db.commit()
    return redirect(url_for('wishlist'))

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM wishlist WHERE username=%s", (session['username'],))
    total_wishlist = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM komentar WHERE username=%s", (session['username'],))
    total_komentar = cursor.fetchone()['total']
    return render_template('profile.html', fullname=session['fullname'], username=session['username'], total_wishlist=total_wishlist, total_komentar=total_komentar)

@app.route('/cek_rekomendasi')
def cek_rekomendasi():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT r.Place_Id, d.Place_Name, d.Rating
        FROM rekomendasi r
        JOIN destinasi d ON r.Place_Id = d.Place_Id
        ORDER BY d.Rating DESC, r.Place_Id ASC
    """)
    data = cursor.fetchall()
    return render_template('cek_rekomendasi.html', data=data)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'username' not in session:
        return redirect(url_for('login'))

    message = ''
    success = False

    if request.method == 'POST':
        old = request.form['old_password']
        new = request.form['new_password']

        db = get_db()
        cursor = db.cursor(pymysql.cursors.DictCursor)  # pakai DictCursor
        cursor.execute("SELECT password FROM users WHERE username=%s", (session['username'],))
        current = cursor.fetchone()

        if current and current['password'] == old:
            cursor.execute("UPDATE users SET password=%s WHERE username=%s", (new, session['username']))
            db.commit()
            message = 'Password berhasil diubah.'
            success = True
        else:
            message = 'Password lama salah.'

    return render_template('change_password.html', message=message, success=success)

@app.route('/generate_dummy_komentar')
def generate_dummy_komentar():
    import random
    db = get_db()
    cursor = db.cursor()

    # Ambil semua Place_Id dari tabel rekomendasi
    cursor.execute("SELECT Place_Id FROM rekomendasi")
    rekom_ids = [row['Place_Id'] for row in cursor.fetchall()]

    komentar_list = [
        "Tempat yang sangat menarik untuk dikunjungi.",
        "Pelayanan sangat memuaskan dan pemandangan indah.",
        "Saya sangat merekomendasikan tempat ini!",
        "Pengalaman yang luar biasa!",
        "Cocok untuk liburan keluarga.",
        "Pemandangan luar biasa dan fasilitas lengkap.",
        "Tempat bersih dan nyaman.",
        "Tiket masuk terjangkau dengan pengalaman maksimal.",
        "Destinasi terbaik di kota ini.",
        "Saya pasti akan kembali lagi ke sini!"
    ]

    usernames = ['user01', 'user02', 'user03', 'user04', 'user05']

    inserted = 0
    for place_id in rekom_ids:
        # Cek apakah destinasi sudah punya komentar
        cursor.execute("SELECT COUNT(*) AS total FROM komentar WHERE Place_Id = %s", (place_id,))
        if cursor.fetchone()['total'] == 0:
            for _ in range(3):  # Tambahkan 3 komentar
                isi = random.choice(komentar_list)
                user = random.choice(usernames)
                rating = random.randint(4, 5)
                cursor.execute("""
                    INSERT INTO komentar (Place_Id, username, isi, rating, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (place_id, user, isi, rating))
                inserted += 1

    db.commit()
    return f"✅ Berhasil menambahkan {inserted} komentar dummy untuk destinasi rekomendasi yang kosong."

if __name__ == '__main__':
    app.run(debug=True)
