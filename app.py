from flask import Flask, request, send_file, render_template, jsonify
from flask_socketio import SocketIO, emit
import os
import webbrowser
import threading
import socket
import ssl
import json
import time
from werkzeug.utils import secure_filename
import mimetypes
import qrcode
from PIL import Image
import io
import base64
import hashlib
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# 在线设备管理
online_devices = {}
device_connections = {}

class DeviceInfo:
    def __init__(self, device_id, ip, user_agent):
        self.device_id = device_id
        self.ip = ip
        self.user_agent = user_agent
        self.last_seen = time.time()
        self.session_id = request.sid if hasattr(request, 'sid') else None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def generate_qr_code(url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 将图片转换为base64编码
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return img_str

def generate_device_id():
    return hashlib.md5(f"{socket.gethostname()}{time.time()}".encode()).hexdigest()[:8]

@socketio.on('connect')
def handle_connect():
    device_id = generate_device_id()
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    device = DeviceInfo(device_id, ip, user_agent)
    device.session_id = request.sid
    online_devices[device_id] = device
    device_connections[request.sid] = device_id
    
    emit('device_registered', {'device_id': device_id})
    emit('devices_updated', get_devices_list(), broadcast=True)
    print(f"设备连接: {device_id} from {ip}")

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in device_connections:
        device_id = device_connections[request.sid]
        if device_id in online_devices:
            del online_devices[device_id]
        del device_connections[request.sid]
        emit('devices_updated', get_devices_list(), broadcast=True)
        print(f"设备断开: {device_id}")

def get_devices_list():
    devices = []
    current_time = time.time()
    for device_id, device in list(online_devices.items()):
        if current_time - device.last_seen < 30:  # 30秒超时
            devices.append({
                'device_id': device_id,
                'ip': device.ip,
                'user_agent': device.user_agent,
                'is_current': device.session_id == request.sid if hasattr(request, 'sid') else False
            })
    return devices

@socketio.on('heartbeat')
def handle_heartbeat():
    if request.sid in device_connections:
        device_id = device_connections[request.sid]
        if device_id in online_devices:
            online_devices[device_id].last_seen = time.time()

@socketio.on('transfer_file')
def handle_file_transfer(data):
    target_device_id = data.get('target_device')
    filename = data.get('filename')
    file_size = data.get('file_size')
    
    if target_device_id in online_devices:
        target_device = online_devices[target_device_id]
        emit('file_transfer_request', {
            'from_device': device_connections.get(request.sid, 'unknown'),
            'filename': filename,
            'file_size': file_size
        }, room=target_device.session_id)

def open_browser():
    import time
    time.sleep(1.5)  # 等待服务器启动
    webbrowser.open('http://127.0.0.1:5000')

@app.route('/')
def index():
    local_ip = get_local_ip()
    url = f'http://{local_ip}:5000'
    qr_code = generate_qr_code(url)
    return render_template('index.html', server_url=url, qr_code=qr_code)

@app.route('/api/files', methods=['GET'])
def list_files():
    files = []
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(filepath):
            file_size = os.path.getsize(filepath)
            files.append({
                'name': filename,
                'size': file_size,
                'type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            })
    return jsonify(files)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # 获取文件大小用于进度跟踪
    file.seek(0, 2)  # 移动到文件末尾
    file_size = file.tell()
    file.seek(0)  # 重置到文件开头
    
    # 分块读取文件并保存，同时发送进度更新
    chunk_size = 8192  # 8KB chunks
    uploaded_size = 0
    
    with open(filepath, 'wb') as f:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            uploaded_size += len(chunk)
            
            # 发送进度更新
            progress = (uploaded_size / file_size) * 100
            socketio.emit('upload_progress', {
                'filename': filename,
                'uploaded': uploaded_size,
                'total': file_size,
                'progress': progress
            })
    
    return jsonify({'message': '文件上传成功', 'filename': filename, 'size': file_size})

@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify(get_devices_list())

@app.route('/api/direct-transfer', methods=['POST'])
def direct_transfer():
    data = request.get_json()
    target_device = data.get('target_device')
    filename = data.get('filename')
    
    if target_device not in online_devices:
        return jsonify({'error': '目标设备不在线'}), 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    
    file_size = os.path.getsize(filepath)
    
    # 通知目标设备有文件传输请求
    target_device_info = online_devices[target_device]
    socketio.emit('direct_transfer_request', {
        'from_device': request.remote_addr,
        'filename': filename,
        'file_size': file_size
    }, room=target_device_info.session_id)
    
    return jsonify({'message': '传输请求已发送'})

@app.route('/api/download/<filename>')
def download_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(filepath, as_attachment=True)

@app.route('/api/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    os.remove(filepath)
    return jsonify({'message': '文件删除成功'})

if __name__ == '__main__':
    # 在后台线程中打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 获取本地IP并显示
    local_ip = get_local_ip()
    print(f"\n🚀 服务器已启动!")
    print(f"📱 本地访问: http://127.0.0.1:5000")
    print(f"🌐 局域网访问: http://{local_ip}:5000")
    print(f"🔒 HTTPS访问: https://127.0.0.1:5000")
    print(f"🌐 HTTPS局域网: https://{local_ip}:5000")
    print(f"📱 扫描二维码在手机上访问\n")
    
    # 尝试使用HTTPS，如果失败则回退到HTTP
    try:
        # 检查OpenSSL是否可用
        import subprocess
        subprocess.run(['openssl', 'version'], check=True, capture_output=True)
        
        # 创建自签名证书
        cert_dir = os.path.join(os.path.dirname(__file__), 'certs')
        if not os.path.exists(cert_dir):
            os.makedirs(cert_dir)
        
        cert_file = os.path.join(cert_dir, 'cert.pem')
        key_file = os.path.join(cert_dir, 'key.pem')
        
        # 如果证书不存在，创建自签名证书
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            print("📋 生成自签名SSL证书...")
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', 
                '-keyout', key_file, '-out', cert_file, 
                '-days', '365', '-nodes', 
                '-subj', f'/CN={local_ip}'
            ], check=True)
        
        # 启动HTTPS服务器
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(cert_file, key_file)
        
        print("🔒 启动HTTPS服务器...")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, ssl_context=ssl_context, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"⚠️  HTTPS启动失败，回退到HTTP: {e}")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)