# Iskra AM550 Smartmeter Reader für Home Assistant

Dieses Projekt liest die Verbrauchsdaten eines Iskraemeco AM550 Smartmeters (wie er von den Wiener Netzen verwendet wird) aus und sendet sie via MQTT an Home Assistant.

## Funktionsweise

Das Python-Skript `decode_smartmeter_mqtt.py`:
1.  Liest die verschlüsselten Rohdaten vom seriellen USB-Port des IR-Lesekopfes.
2.  Entschlüsselt die Datenpakete mit dem bereitgestellten Sicherheitsschlüssel.
3.  Verifiziert die Datenintegrität mittels CRC16-Prüfsumme.
4.  Veröffentlicht die Verbrauchsdaten (Energie und Leistung) auf einem MQTT-Broker.
5.  Sendet MQTT-Discovery-Nachrichten, damit Home Assistant die Sensoren automatisch erkennt und anlegt.
6.  Kann optional die Messwerte in eine lokale CSV-Datei loggen.

## Setup

### Hardware
*   Ein Raspberry Pi (z.B. Zero, 3, 4)
*   Ein optischer IR-Lesekopf mit USB-Anschluss (z.B. von Weidmann Elektronik)

### Software
*   Raspberry Pi OS (Lite oder Desktop)
*   Python 3 mit einem eingerichteten `venv` (empfohlen)
*   Ein laufender MQTT-Broker (z.B. Mosquitto)
*   Eine laufende Homeassistant Instanz mit MQTT-Support

## Wichtige Bemerkungen
*   Der Iskra AM550 Zähler sendet seine Daten **automatisch im Sekundentakt**, ohne dass eine Anfrage gesendet werden muss.
*   Das Skript ist für die Installation als `systemd`-Dienst ausgelegt, um einen zuverlässigen Dauerbetrieb zu gewährleisten.
*   Das Verhalten dieses Zählers unterscheidet sich von anderen Modellen (z.B. L&G E350, Iskra MT174), die oft aktiv abgefragt werden müssen.

## Danksagung

Ein besonderer Dank geht an:
*   **pocki80**: Für die Pionierarbeit in Python 3 zur Dekodierung und CRC-Prüfung der AM550-Daten. Ohne seine Gists wäre dieses Projekt nicht möglich gewesen.
    *   CRC16 Implementierung
    *   Daten auslesen
*   **Gemini-Pro**: Für die Unterstützung bei der Integration der automatischen MQTT-Discovery-Funktion für Home Assistant.


## Vorbereitung & Installation

Bevor das Skript als Dienst eingerichtet werden kann, müssen die Projektdateien vorhanden und die Python-Umgebung korrekt konfiguriert sein.

### Schritt 1: System-Pakete für Python sicherstellen

Stellen Sie sicher, dass `pip` (Pythons Paket-Manager) und `venv` (für virtuelle Umgebungen) auf Ihrem System installiert sind.

```bash
sudo apt update
sudo apt install python3-pip python3-venv -y
```

### Schritt 2: Projektdateien abrufen (Empfohlen)

Der einfachste Weg, die Projektdateien zu erhalten, ist das Klonen des Git-Repositorys.

```bash
# Wechseln Sie in das Home-Verzeichnis
cd ~ 

# Klonen Sie das Repository (ersetzen Sie die URL falls nötig)
git clone https://github.com/schoko123/wn_iskra_am550_smartmeter_to_Homeassistant.git

# Wechseln Sie in das neue Projektverzeichnis
cd wn_iskra_am550_smartmeter_to_Homeassistant
```

### Schritt 3: Virtuelle Python-Umgebung (venv) einrichten

Es wird dringend empfohlen, eine virtuelle Umgebung zu verwenden, um die Projekt-Abhängigkeiten von den System-Paketen zu isolieren.

1.  Erstellen Sie die `venv` im Projektverzeichnis:
    ```bash
    python3 -m venv venv
    ```

2.  Aktivieren Sie die `venv`. Ihr Kommandozeilen-Prompt sollte sich danach ändern:
    ```bash
    source venv/bin/activate
    ```

### Schritt 4: Python-Abhängigkeiten installieren

Installieren Sie mit `pip` alle für das Skript benötigten Python-Bibliotheken aus der `requirements.txt`-Datei.

```bash
pip install -r requirements.txt
```

## Installation als Systemd Service (unter Raspberry Pi OS Lite)

Diese Anleitung erklärt, wie das Python-Skript als Hintergrunddienst eingerichtet wird, der beim Systemstart automatisch ausgeführt wird. Dies ist ideal für den Betrieb auf einem Raspberry Pi.

### Schritt 1: systemd-Service-Datei erstellen

1.  Erstellen Sie die Service-Datei mit einem Texteditor und `sudo`-Rechten. `nano` ist ein einfacher Editor, falls Sie unsicher sind.

    ```bash
    sudo nano /etc/systemd/system/smartmeter.service
    ```

2.  Fügen Sie den folgenden Inhalt in die Datei ein. **Sie müssen die Pfade an Ihre Umgebung anpassen!**

    ```ini
    [Unit]
    Description=Smartmeter MQTT Script
    After=network-online.target
    
    [Service]
    # Ändern Sie Benutzer und Gruppe, falls Sie nicht den 'pi'-Benutzer verwenden
    User=pi
    Group=pi
    
    # WICHTIG: Dies sollte der Pfad zum geklonten Projektverzeichnis sein
    WorkingDirectory=/home/pi/wn_iskra_am550_smartmeter_to_Homeassistant
    
    # WICHTIG: Dieser Pfad nutzt die Python-Version aus der venv, die im Projektordner liegt
    ExecStart=/home/pi/wn_iskra_am550_smartmeter_to_Homeassistant/venv/bin/python /home/pi/wn_iskra_am550_smartmeter_to_Homeassistant/decode_smartmeter_mqtt.py
    
    Restart=always
    
    [Install]
    WantedBy=multi-user.target
    ```

    > **Wichtige Hinweise zur Anpassung:**
    >
    > -   `User=pi` und `Group=pi`: Ersetzen Sie `pi`, falls Sie das Skript unter einem anderen Benutzer ausführen.
    > -   `WorkingDirectory`: Geben Sie den absoluten Pfad zu dem Ordner an, in dem Ihr `decode_smartmeter_mqtt.py`-Skript liegt.
    > -   `ExecStart`: Dies ist die wichtigste Zeile.
    >     -   Der erste Teil des Pfades zeigt auf die Python-Executable in Ihrer `venv`.
    >     -   Der zweite Teil ist der absolute Pfad zu Ihrem `decode_smartmeter_mqtt.py`-Skript.

    Speichern Sie die Datei und schließen Sie den Editor (in `nano`: `Strg+X`, dann `J`, dann `Enter`).

### Schritt 2: Den neuen Dienst aktivieren und starten

1.  Laden Sie den systemd-Daemon neu, damit er die neue `smartmeter.service`-Datei erkennt:
    ```bash
    sudo systemctl daemon-reload
    ```
2.  Aktivieren Sie den Dienst, damit er bei jedem Systemstart automatisch ausgeführt wird:
    ```bash
    sudo systemctl enable smartmeter.service
    ```
3.  Starten Sie den Dienst sofort:
    ```bash
    sudo systemctl start smartmeter.service
    ```

### Schritt 3: Den Status des Dienstes überprüfen

1.  Überprüfen Sie den Status, um zu sehen, ob alles korrekt läuft:
    ```bash
    sudo systemctl status smartmeter.service
    ```
    Hier sehen Sie, ob der Dienst `active (running)` ist und die letzten Log-Ausgaben.

2.  Um die Ausgaben Ihres Skripts live zu verfolgen (z.B. zur Fehlersuche), verwenden Sie diesen Befehl:
    ```bash
    journalctl -u smartmeter.service -f
    ```
    (Beenden mit `Strg+C`)
