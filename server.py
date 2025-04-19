from flask import Flask, request, jsonify
import pyodbc
from datetime import datetime, timedelta
import traceback
from zeroconf import Zeroconf, ServiceInfo
import socket
import unicodedata

app = Flask(__name__)
# ========== Cấu hình mDNS ========== #
def get_local_ip():
    try:
        # Tạo socket test kết nối đến Google DNS
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def register_mdns():
    zeroconf = Zeroconf()
    ip_address = socket.inet_aton(get_local_ip())
    
    service_info = ServiceInfo(
        "_http._tcp.local.",
        "myserver._http._tcp.local.",
        addresses=[ip_address],
        port=5000,
        properties={'path': '/'},
        server="myserver.local."
    )
    
    zeroconf.register_service(service_info)
    print(f"✅ Đã đăng ký mDNS với IP: {get_local_ip()}")
    return zeroconf

# ========== Khởi tạo mDNS ========== #
zeroconf = register_mdns()
viet_map = {
    'đ': 'd', 'Đ': 'D',
    'ă': 'a', 'Ă': 'A',
    'â': 'a', 'Â': 'A',
    'ê': 'e', 'Ê': 'E',
    'ô': 'o', 'Ô': 'O',
    'ơ': 'o', 'Ơ': 'O',
    'ư': 'u', 'Ư': 'U',
}

def remove_accents(text):
    # Bước 1: Normalize để tách dấu khỏi ký tự (cho á -> a)
    nfkd = unicodedata.normalize('NFKD', text)
    no_accent = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    
    # Bước 2: Thay các ký tự như đ, ă, â,... thủ công
    final_result = ''.join([viet_map.get(c, c) for c in no_accent])
    return final_result

# Kết nối SQL Server
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=localhost\\SQLEXPRESS;'
    'DATABASE=quanlithuvien;'
    'Trusted_Connection=yes;'
)
@app.route('/ten', methods=['POST'])
def get_ten():
    data = request.get_json(force=True)
    rfid = data.get('rfid', '')
     
    cursor = conn.cursor()
    cursor.execute("SELECT ten, id FROM nguoidung WHERE rfid_code = ?", (rfid,))
    row = cursor.fetchone()
    
    if row:
        return jsonify({
            'status': 'success',
            'ten': remove_accents(row[0]),
            'id': row[1]
        })
    else:
        return jsonify({
            'status': 'fail',
            'message': 'Không tìm thấy người dùng'
        })
@app.route('/thongtin', methods=['POST'])
def get_user_info():
    data = request.get_json(force=True)
    rfid = data.get('rfid', '')
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, ten, sdt, email FROM nguoidung WHERE rfid_code = ?", (rfid,))
    row = cursor.fetchone()
    
    if row:
        return jsonify({
            'status': 'success',
            'id': row[0],
            'ten': remove_accents(row[1]),
            'sdt': row[2],
            'email': row[3]
        })
    else:
        return jsonify({
            'status': 'fail', 
            'message': 'Không tìm thấy người dùng'
        })

@app.route('/thongtinsach', methods=['POST'])
def get_book_info():
    data = request.get_json(force=True)
    book_id = data.get('book_id', '')
    
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, ten, tacgia, nam, soluong FROM sach WHERE id = ?", (book_id,))
    row = cursor.fetchone()
    if row:
        return jsonify({'status': 'success', 'id': row[0],'ten': remove_accents(row[1]),  # Bỏ dấu tên sách
            'tacgia': remove_accents(row[2]), 'nam': row[3], 'soluong': row[4] })
    else:
        return jsonify({'status': 'fail', 'message': 'Không tìm thấy sách'})
@app.route('/danhsachsach', methods=['GET', 'POST'])
def get_all_books():
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ten FROM sach ORDER BY id")  # Chỉ lấy 2 trường
        books = []
        for row in cursor:
            books.append({
                'id': row[0],
                'ten': remove_accents(row[1])
            })
        
        return jsonify(books)  # Trả thẳng về mảng JSON
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    



@app.route('/previewmuon', methods=['POST'])
def borrow_preview():
    conn = None
    try:
        # 1. Validate input đơn giản
        data = request.get_json()
        if not data or 'book_id' not in data:
            return jsonify({"status": "error", "message": "Thieu ma sach"}), 400

        book_id = data['book_id']

        # 2. Kết nối database
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost\\SQLEXPRESS;'
            'DATABASE=quanlithuvien;'
            'Trusted_Connection=yes;'
        )
        cursor = conn.cursor()

        # 3. Truy vấn cơ bản
        cursor.execute("SELECT ten, soluong FROM sach WHERE id = ?", book_id)
        book = cursor.fetchone()
        
        if not book:
            return jsonify({"status": "error"}), 200

        # 4. Tính toán ngày
        today = datetime.now().strftime("%d/%m/%Y")
        due_date = (datetime.now() + timedelta(days=14)).strftime("%d/%m/%Y")

        # 5. Trả về response
        return jsonify({
            "status": "success",
            "ten": remove_accents(book.ten),
            "ngaymuon": today,
            "hantra": due_date,
            "soluong": book.soluong
        })

    except Exception as e:
        return jsonify({"status": "error"}), 500
    finally:
        if conn:
            conn.close()

           
@app.route('/muonsach', methods=['POST'])
def borrow_book():
    conn = None
    try:
        data = request.get_json()
        
        # Kiểm tra tồn tại các trường
        if not data or 'book_id' not in data or 'user_id' not in data or 'soluong_muon' not in data:
            return jsonify({"status": "error", "message": "Thiếu thông tin bắt buộc"}), 400
        
        # Chuyển đổi kiểu dữ liệu
        try:
            book_id = str(data['book_id'])
            user_id = str(data['user_id'])
            quantity = int(data['soluong_muon'])
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Dữ liệu không đúng định dạng"}), 400
        
        # Kiểm tra giá trị
        if quantity <= 0:
            return jsonify({"status": "error", "message": "Số lượng phải lớn hơn 0"}), 400

        # 2. Kết nối database
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost\\SQLEXPRESS;'
            'DATABASE=quanlithuvien;'
            'Trusted_Connection=yes;'
        )
        conn.autocommit = False
        cursor = conn.cursor()

        # 3. Kiểm tra số lượng sách trong cơ sở dữ liệu
        cursor.execute("SELECT soluong FROM sach WHERE id = ?", book_id)
        book = cursor.fetchone()

        if not book or book.soluong < quantity:
            return jsonify({"status": "error"}), 600

        # 4. Tính toán ngày (từ preview)
        today = datetime.now().strftime("%Y-%m-%d")
        due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

        # 5. Tạo phiếu mượn (từ borrow)
        cursor.execute(
            "INSERT INTO muontra (id_nguoidung, id_sach, soluong_muon, ngaymuon, hantra) VALUES (?, ?, ?, ?, ?)",
            user_id, book_id, quantity, today, due_date
        )

        # 6. Cập nhật số lượng sách trong cơ sở dữ liệu
        cursor.execute("UPDATE sach SET soluong = soluong - ? WHERE id = ?", quantity, book_id)
        conn.commit()

        # 7. Trả về response
        return jsonify({
            "status": "success",
            "hantra": due_date,
            "message": "Mượn sách thành công!"
        })
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error"}), 500

    finally:
        if conn:
            conn.close()

@app.route('/danhsachmuon', methods=['POST'])
def danh_sach_muon():
    conn = None
    try:
        # 1. Nhận và validate dữ liệu
        data = request.get_json()
        if not data or 'user_id' not in data:
            return jsonify({"status": "error", "message": "Thiếu user_id"}), 400

        user_id = data['user_id']

        # 2. Kết nối database
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost\\SQLEXPRESS;'
            'DATABASE=quanlithuvien;'
            'Trusted_Connection=yes;'
        )
        cursor = conn.cursor()

        # 3. Truy vấn dữ liệu
        cursor.execute('''
            SELECT s.id, s.ten, SUM(m.soluong_muon) as tong_soluong
            FROM muontra m
            JOIN sach s ON m.id_sach = s.id
            WHERE m.id_nguoidung = ? AND m.trang_thai = 'dang_muon'
            GROUP BY s.id, s.ten
        ''', user_id)

        # 4. Đóng gói kết quả
        books = [{
            "id": row.id,
            "ten": remove_accents(row.ten),
            "tong_soluong": row.tong_soluong  # Key phải khớp với ESP32
        } for row in cursor]

        return jsonify({
            "status": "success",
            "data": books  # Đúng cấu trúc ESP32 cần
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/previewtra', methods=['POST'])
def preview_tra_sach():
    conn = None
    try:
        data = request.get_json()
        # ... [phần validate input] ...

        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost\\SQLEXPRESS;'
            'DATABASE=quanlithuvien;'
            'Trusted_Connection=yes;'
        )
        cursor = conn.cursor()

        # 1. Lấy thông tin sách (thêm check tồn tại)
        cursor.execute("SELECT ten FROM sach WHERE id = ?", data['book_id'])
        sach = cursor.fetchone()
        if not sach:
            return jsonify({"status": "error", "message": "Không tìm thấy sách"}), 404

        # 2. Sửa đoạn tính phạt - CÁCH SỬA CHÍNH
        cursor.execute('''
            SELECT 
                CASE WHEN hantra < GETDATE() 
                     THEN DATEDIFF(day, hantra, GETDATE()) 
                     ELSE 0 
                END as ngay_qua_han,
                soluong_muon
            FROM muontra
            WHERE id_nguoidung = ? 
              AND id_sach = ? 
              AND trang_thai = 'dang_muon'
              AND hantra IS NOT NULL  
            ORDER BY ngaymuon ASC
        ''', (data['user_id'], data['book_id']))
        
        records = cursor.fetchall()  # Dùng fetchall thay vì fetchone
        tong_phat = 0
        so_luong_con_lai = int(data['so_luong_tra'])
        
        for record in records:
            if so_luong_con_lai <= 0:
                break
                
            ngay_qua_han = record.ngay_qua_han or 0  # Phòng trường hợp NULL
            so_luong_muon = record.soluong_muon or 0
            
            so_luong_ap_dung = min(so_luong_muon, so_luong_con_lai)
            phat_trong_record = ngay_qua_han * 2000 * so_luong_ap_dung
            tong_phat += phat_trong_record
            
            so_luong_con_lai -= so_luong_ap_dung

        return jsonify({
            "status": "success",
            "ten_sach": remove_accents(sach.ten),
            "so_luong_tra": data['so_luong_tra'],
            "ngay_tra": datetime.now().strftime("%d/%m/%Y"),
            "phat": tong_phat
        })

    except Exception as e:
        error_msg = {
            "error": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }
        
        # Log lỗi ra console (tuỳ chọn)
        print(f"ERROR: {error_msg}")
        
        return jsonify({
            "status": "error",
            "error": error_msg
        }), 500
    finally:
        if conn:
            conn.close()

@app.route('/trasach', methods=['POST'])
def tra_sach():
    conn = None
    try:
        # 1. VALIDATE INPUT
        data = request.get_json()
        if not data or 'user_id' not in data or 'book_id' not in data or 'so_luong_tra' not in data:
            return jsonify({"status": "error", "message": "Thiếu user_id/book_id/so_luong_tra"}), 400

        # 2. KẾT NỐI DATABASE (TRỰC TIẾP TRONG ENDPOINT)
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost\\SQLEXPRESS;'
            'DATABASE=quanlithuvien;'
            'Trusted_Connection=yes;'
        )
        cursor = conn.cursor()
        conn.autocommit = False

        # 3. KIỂM TRA SÁCH ĐANG MƯỢN
        cursor.execute('''
            SELECT id, soluong_muon 
            FROM muontra 
            WHERE id_nguoidung = ? 
              AND id_sach = ? 
              AND trang_thai = 'dang_muon'
        ''', (data['user_id'], data['book_id']))
        
        records = cursor.fetchall()
        if not records:
            return jsonify({"status": "error", "message": "Không có sách đang mượn"}), 404

        # 4. THỰC HIỆN TRẢ SÁCH
        so_luong_con_lai = int(data['so_luong_tra'])
        for record in records:
            if so_luong_con_lai <= 0:
                break
            
            sl_tra = min(record.soluong_muon, so_luong_con_lai)
            cursor.execute('''
                UPDATE muontra 
                SET soluong_muon = soluong_muon - ?,
                    trang_thai = CASE WHEN (soluong_muon - ?) <= 0 THEN 'da_tra' ELSE 'dang_muon' END,
                    ngaytra = CASE WHEN (soluong_muon - ?) <= 0 THEN GETDATE() ELSE NULL END
                WHERE id = ?
            ''', (sl_tra, sl_tra, sl_tra, record.id))
            
            so_luong_con_lai -= sl_tra

        # 5. CẬP NHẬT KHO SÁCH
        so_luong_da_tra = int(data['so_luong_tra']) - so_luong_con_lai
        cursor.execute('UPDATE sach SET soluong = soluong + ? WHERE id = ?', 
                      (so_luong_da_tra, data['book_id']))

        conn.commit()
        return jsonify({
            "status": "success",
            "so_luong_da_tra": so_luong_da_tra
        })

    except pyodbc.Error as e:
        if conn: conn.rollback()
        return jsonify({
            "status": "error",
            "message": "Lỗi database",
            "detail": str(e)
        }), 500
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({
            "status": "error",
            "message": "Lỗi hệ thống",
            "detail": str(e)
        }), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    try:
        print("🔄 Đang khởi động server...")
        app.run(host='0.0.0.0', port=5000, debug=True)
    finally:
        print("🛑 Đang dừng server...")
        zeroconf.unregister_all_services()
        zeroconf.close()
        print("✅ Đã hủy đăng ký mDNS")
