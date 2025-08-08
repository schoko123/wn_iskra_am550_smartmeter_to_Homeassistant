import serial
import os
import time
import json
from datetime import datetime
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# --------------------------------------------------------------------------
# --- Configuration ---
# --------------------------------------------------------------------------

# --- Smart Meter Configuration ---
KEY = bytes.fromhex('yourWienerNetzeKey')
TERMINAL_DEVICE = '/dev/ttyUSB0'

# --- MQTT Configuration ---
MQTT_BROKER_ADDRESS = "X.X.X.X"  # <-- IMPORTANT: Set your MQTT broker address
MQTT_PORT = 1883
MQTT_USERNAME = "mqtt-user"      # <-- Set your MQTT username
MQTT_PASSWORD = "your_password"  # <-- Set your MQTT password
MQTT_BASE_TOPIC = "homeassistant/sensor/smartmeter"

# --- Optional: File Logging ---
ENABLE_FILE_LOGGING = False # Set to False to disable CSV logging
LOG_BASE_PATH = '/vourFileLogDir/AM550/'
LOG_FILE_NAME = "energy.csv"

# --------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------

def byte_mirror(c):
    """Mirrors the bits of a byte."""
    a1, a2, a3, a4, a5, a6 = 0xF0, 0x0F, 0xCC, 0x33, 0xAA, 0x55
    c = ((c & a1) >> 4) | ((c & a2) << 4)
    c = ((c & a3) >> 2) | ((c & a4) << 2)
    c = ((c & a5) >> 1) | ((c & a6) << 1)
    return c

def calc_crc16(data):
    """Calculates CRC16 checksum."""
    crc, polynominal = 0xFFFF, 0x1021
    for byte in data:
        c = byte_mirror(byte) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ polynominal if (crc ^ c) & 0x8000 else crc << 1) & 0xFFFF
            c = (c << 1) & 0xFFFF
    crc = (0xFFFF - crc) & 0xFFFF
    return (byte_mirror(crc >> 8) << 8) | byte_mirror(crc & 0xFF)

# --------------------------------------------------------------------------
# MQTT Functions
# --------------------------------------------------------------------------

def setup_mqtt_client():
    """Sets up and connects the MQTT client."""
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    try:
        client.connect(MQTT_BROKER_ADDRESS, MQTT_PORT, 60)
        client.loop_start() # Start a background thread for networking
        print("Successfully connected to MQTT broker.")
        return client
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return None

def publish_mqtt_discovery(client):
    """Publishes MQTT discovery messages for Home Assistant."""
    sensors = {
        "positive_active_energy": {"name": "Positive Active Energy", "unit": "kWh", "icon": "mdi:flash"},
        "negative_active_energy": {"name": "Negative Active Energy", "unit": "kWh", "icon": "mdi:flash-off"},
        "positive_reactive_energy": {"name": "Positive Reactive Energy", "unit": "kvarh", "icon": "mdi:flash"},
        "negative_reactive_energy": {"name": "Negative Reactive Energy", "unit": "kvarh", "icon": "mdi:flash-off"},
        "positive_active_power": {"name": "Positive Active Power", "unit": "W", "icon": "mdi:power-plug"},
        "negative_active_power": {"name": "Negative Active Power", "unit": "W", "icon": "mdi:power-plug-off"},
        "positive_reactive_power": {"name": "Positive Reactive Power", "unit": "var", "icon": "mdi:power-plug"},
        "negative_reactive_power": {"name": "Negative Reactive Power", "unit": "var", "icon": "mdi:power-plug-off"},
    }

    for key, sensor_info in sensors.items():
        topic = f"{MQTT_BASE_TOPIC}/{key}/config"
        payload = {
            "name": f"Smartmeter {sensor_info['name']}",
            "state_topic": f"{MQTT_BASE_TOPIC}/state",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unit_of_measurement": sensor_info["unit"],
            "icon": sensor_info["icon"],
            "unique_id": f"smartmeter_{key}",
            "device": {
                "identifiers": ["smartmeter_iskra_am550"],
                "name": "Iskra AM550 Smartmeter",
                "model": "AM550",
                "manufacturer": "Iskraemeco"
            }
        }
        client.publish(topic, json.dumps(payload), retain=True)
    print("Published MQTT discovery messages for all sensors.")

def publish_mqtt_data(client, data):
    """Publishes sensor data to the MQTT state topic."""
    topic = f"{MQTT_BASE_TOPIC}/state"
    client.publish(topic, json.dumps(data))

# --------------------------------------------------------------------------
# Main Application Logic
# --------------------------------------------------------------------------

def main():
    """Main function to read, decode, and publish smart meter data."""
    mqtt_client = setup_mqtt_client()
    if not mqtt_client:
        # If MQTT fails, we could either exit or continue with file logging only
        print("Exiting due to MQTT connection failure.")
        return

    # Publish discovery messages so Home Assistant can create the entities
    publish_mqtt_discovery(mqtt_client)

    while True:
        try:
            with serial.Serial(TERMINAL_DEVICE, 9600, bytesize=8, parity='N', stopbits=1, timeout=10) as ser:
                packet = b''
                while not packet.endswith(b'\x7e\xa0\x67'):
                    read_byte = ser.read(1)
                    if not read_byte:
                        print("Timeout waiting for start byte. Retrying...")
                        break
                    packet = read_byte if read_byte == b'\x7e' else (packet + read_byte if packet.startswith(b'\x7e') else b'')
                
                if not packet.endswith(b'\x7e\xa0\x67'): continue

                packet += ser.read(102)
                if len(packet) != 105 or not packet.endswith(b'\x7e'):
                    print(f"Incomplete packet (len: {len(packet)}). Discarding.")
                    continue

            data_hex = packet.hex()
            crc2_hex = data_hex[204:208]
            crc4_calc = calc_crc16(packet[1:102])
            crc4_hex = f'{crc4_calc:04x}'

            if crc2_hex != crc4_hex:
                print(f"CRC mismatch: got {crc2_hex}, calculated {crc4_hex}. Packet corrupt.")
                continue
            
            print("CRC OK. Processing packet.")

            st = bytes.fromhex(data_hex[28:44])
            ic = bytes.fromhex(data_hex[48:56])
            iv = st + ic + b'\x00\x00\x00\x02'
            encrypted_data = bytes.fromhex(data_hex[56:204])

            cipher = Cipher(algorithms.AES(KEY), modes.CTR(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            dec_hex = (decryptor.update(encrypted_data) + decryptor.finalize()).hex()

            sensor_data = {
                "positive_active_energy": int(dec_hex[70:78], 16) / 1000,
                "negative_active_energy": int(dec_hex[80:88], 16) / 1000,
                "positive_reactive_energy": int(dec_hex[90:98], 16) / 1000,
                "negative_reactive_energy": int(dec_hex[100:108], 16) / 1000,
                "positive_active_power": int(dec_hex[110:118], 16),
                "negative_active_power": int(dec_hex[120:128], 16),
                "positive_reactive_power": int(dec_hex[130:138], 16),
                "negative_reactive_power": int(dec_hex[140:148], 16),
            }

            print("--- Sensor Data ---")
            for key, value in sensor_data.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
            
            publish_mqtt_data(mqtt_client, sensor_data)
            print("Successfully published data to MQTT.")

            if ENABLE_FILE_LOGGING:
                now = datetime.now()
                save_dir = os.path.join(LOG_BASE_PATH, now.strftime('%Y'), now.strftime('%m'))
                os.makedirs(save_dir, exist_ok=True)
                log_path = os.path.join(save_dir, f"{now.strftime('%Y-%m-%d_')}{LOG_FILE_NAME}")
                log_line = f"{now.strftime('%Y-%m-%d %H:%M:%S')};{';'.join(map(str, sensor_data.values()))} \n"
                with open(log_path, "a") as handler:
                    handler.write(log_line)
                print(f"Data also written to {log_path}")

        except serial.SerialException as e:
            print(f"Serial Error: {e}. Retrying in 10 seconds...")
            time.sleep(10)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            mqtt_client.loop_stop()
            time.sleep(10)
            mqtt_client = setup_mqtt_client() # Try to reconnect

if __name__ == "__main__":
    main()
