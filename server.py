"""
============================================================
  DRONE SIM - Python Bridge Server
  Číta dáta z Arduino (Serial) → posiela do prehliadača (WebSocket)
  Spúšťa HTTP server pre drone_game.html

  Inštalácia:
    pip install flask flask-socketio pyserial eventlet

  Spustenie:
    python server.py

  Potom otvor: http://localhost:5000
============================================================
"""

import os
import sys
import time
import threading
from typing import Optional  # BUG FIX: 'dict | None' syntax vyžaduje Python 3.10+
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("\n  ❌  CHYBA: Modul 'pyserial' nie je nainštalovaný!")
    print("  Spusti:  pip uninstall serial  &&  pip install pyserial\n")
    sys.exit(1)
from flask import Flask, send_from_directory
from flask_socketio import SocketIO

# ─── Konfigurácia ────────────────────────────────────────────
BAUD_RATE    = 115200
PORT_HINT    = None   # Nastav na 'COM3' alebo '/dev/ttyUSB0' ak auto-detect nefunguje
SEND_RATE_HZ = 50     # Max. frekvencia odosielania do prehliadača
GAME_FILE    = "drone_game.html"  # Musí byť v rovnakom priečinku ako server.py

# ─── Flask + SocketIO setup ──────────────────────────────────
app = Flask(__name__, static_folder=".")
app.config["SECRET_KEY"] = "drone_fpv_2024"
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# ─── Globálny stav ───────────────────────────────────────────
latest_ctrl: Optional[dict] = None
arduino_connected = False
connected_clients = 0
state_lock = threading.Lock()
last_known_port: Optional[str] = None   # Posledný úspešný port — pri reconnecte sa skúša ako prvý


# ─── Pomocné funkcie ─────────────────────────────────────────

# CH340 klony majú pevný USB VID:PID = 1A86:7523
CH340_VID = 0x1A86
CH340_PID = 0x7523

ARDUINO_KEYWORDS = [
    "ch340", "ch341", "cp210", "arduino", "usb serial",
    "uart", "ttyusb", "ttyacm", "usbmodem", "usbserial",
]

def is_arduino_port(port) -> bool:
    """Vráti True ak port vyzerá ako Arduino / CH340 klon."""
    # Primárne: porovnaj VID/PID (spoľahlivé aj bez popisného drivera)
    if port.vid == CH340_VID and port.pid == CH340_PID:
        return True
    # Záložné: hľadaj kľúčové slová v popise / výrobcovi
    desc = ((port.description or "") + (port.manufacturer or "")).lower()
    return any(kw in desc for kw in ARDUINO_KEYWORDS)

def find_arduino_port() -> Optional[str]:
    """
    Nájde port Arduino/CH340.
    - Nikdy nespadne na náhodný port (napr. COM1 = systémový).
    - Pri reconnecte skúsi posledný známy port ako prvý.
    - Ak nenájde nič s Arduino signaturou, vráti None a čaká.
    """
    if PORT_HINT:
        return PORT_HINT

    ports = serial.tools.list_ports.comports()

    # 1. Skús posledný known port ak ešte existuje v zozname
    if last_known_port:
        for port in ports:
            if port.device == last_known_port and is_arduino_port(port):
                print(f"  🔄  Reconnect na posledný port: {port.device}")
                return port.device

    # 2. Hľadaj akýkoľvek Arduino/CH340 port
    for port in ports:
        if is_arduino_port(port):
            desc = (port.description or "").strip()
            print(f"  ✅  Nájdený Arduino port: {port.device}  [{desc}]")
            return port.device

    # 3. ŽIADNY fallback na prvý port — COM1 atď. nie sú Arduino
    return None


def parse_line(line: str) -> Optional[dict]:   # BUG FIX: bolo `dict | None`
    """Parsuje riadok formátu  LX:512,LY:512,..."""
    try:
        parts = line.strip().split(",")
        if len(parts) < 10:
            return None
        data = {}
        for part in parts:
            if ":" not in part:
                return None
            k, v = part.split(":", 1)
            data[k.strip()] = int(v.strip())
        return data
    except Exception:
        return None


# ─── Sériový vlákno ──────────────────────────────────────────
def serial_thread():
    global latest_ctrl, arduino_connected, connected_clients, last_known_port
    min_interval = 1.0 / SEND_RATE_HZ
    last_emit    = 0

    while True:
        port = find_arduino_port()
        if not port:
            print("  🔴  Arduino (CH340) nenájdené. Retry o 3 s...  (hra funguje len s klávesnicou)")
            time.sleep(3)
            continue

        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=2.0)
            time.sleep(2.0)          # Čakaj na reset Arduina po otvorení portu
            ser.reset_input_buffer()

            # ── Overenie: počkaj na DRONE_CTRL_READY (max 5 s) ──────
            # Ak to nepríde, port je síce otvorený ale nejde o náš controller.
            print(f"  ⏳  Čakám na handshake z {port}...")
            deadline = time.monotonic() + 5.0
            confirmed = False
            while time.monotonic() < deadline:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore")
                if "DRONE_CTRL_READY" in line:
                    confirmed = True
                    break

            if not confirmed:
                print(f"  ⚠️  {port}: žiadny handshake — nie je to náš controller, preskakujem.")
                ser.close()
                time.sleep(2)
                continue

            # ── Port potvrdený — ulož ho pre prípadný reconnect ──────
            with state_lock:
                last_known_port   = port
                arduino_connected = True
            socketio.emit("arduino_status", {"connected": True})
            print(f"  🟢  Arduino pripojené na {port}")
            print(f"  🎮  Controller inicializovaný!")

            # ── Hlavná slučka čítania ────────────────────────────────
            consecutive_empty = 0
            while True:
                try:
                    raw = ser.readline()
                    if not raw:
                        consecutive_empty += 1
                        # Ak dlho nič nechodí, Arduino asi vypadlo
                        if consecutive_empty > 30:
                            print(f"  ⚠️  {port}: timeout — Arduino pravdepodobne odpojené.")
                            break
                        continue
                    consecutive_empty = 0

                    line = raw.decode("utf-8", errors="ignore")
                    if "DRONE_CTRL_READY" in line:
                        continue   # Reboot Arduina za behu — normálne pokračuj

                    data = parse_line(line)
                    if data is None:
                        continue

                    with state_lock:
                        latest_ctrl = data

                    now = time.monotonic()
                    with state_lock:
                        clients = connected_clients
                    if now - last_emit >= min_interval and clients > 0:
                        socketio.emit("controller", data)
                        last_emit = now

                except serial.SerialException as e:
                    print(f"  ⚠️  Serial chyba: {e}")
                    break

        except serial.SerialException as e:
            print(f"  🔴  Nemôžem otvoriť {port}: {e}")

        with state_lock:
            arduino_connected = False
        socketio.emit("arduino_status", {"connected": False})
        print(f"  🔴  Odpojené. Hľadám Arduino znova...")
        time.sleep(3)


# ─── Flask routes ─────────────────────────────────────────────
@app.route("/")
def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), GAME_FILE)
    if not os.path.exists(html_path):
        return (
            f"<h2>Chyba: '{GAME_FILE}' nenájdený!</h2>"
            f"<p>Uisti sa, že {GAME_FILE} je v rovnakom priečinku ako server.py</p>",
            404,
        )
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), GAME_FILE)


@app.route("/status")
def status():
    with state_lock:
        return {
            "arduino": arduino_connected,
            "clients": connected_clients,
            "last_data": latest_ctrl,
        }


# ─── SocketIO udalosti ────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    global connected_clients
    with state_lock:
        connected_clients += 1
        clients = connected_clients
        is_connected = arduino_connected
    print(f"  🌐  Prehliadač pripojený  (celkom: {clients})")
    socketio.emit("arduino_status", {"connected": is_connected})


@socketio.on("disconnect")
def on_disconnect():
    global connected_clients
    with state_lock:
        connected_clients = max(0, connected_clients - 1)
        clients = connected_clients
    print(f"  🌐  Prehliadač odpojený  (celkom: {clients})")


# ─── Hlavný vstup ─────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 56)
    print("  🚁  DRONE FPV SIM - Bridge Server")
    print("=" * 56)
    print(f"  Hra dostupná na:  http://localhost:5000")
    print(f"  Status API:       http://localhost:5000/status")
    print("=" * 56)

    # Spusti sériové vlákno
    t = threading.Thread(target=serial_thread, daemon=True)
    t.start()

    # Spusti web server
    try:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n  👋  Server ukončený")
        sys.exit(0)
