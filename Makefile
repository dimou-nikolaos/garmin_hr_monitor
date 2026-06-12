# ─────────────────────────────────────────────────────────────────────────────
#  Garmin Fenix BLE HR Monitor – Makefile
#  Targets:
#    make            → create venv + install deps (same as: make install)
#    make install    → create venv + install deps
#    make run        → stream HR from the first auto-discovered device
#    make scan       → list nearby BLE devices
#    make run-addr   → connect to a specific MAC  (ADDR=XX:XX:XX:XX:XX:XX)
#    make dump       → connect + dump all GATT services once
#    make check-sys  → verify BlueZ and D-Bus are available on the host
#    make clean      → remove the virtual environment
# ─────────────────────────────────────────────────────────────────────────────

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
SCRIPT      := garmin_hr_monitor.py

# Device MAC – override on the command line:  make run-addr ADDR=C0:FF:EE:00:00:01
ADDR        ?=
TIMEOUT     ?= 0

.PHONY: all install run run-plot scan run-addr dump check-sys clean help

all: install

# ── Environment setup ─────────────────────────────────────────────────────────

$(VENV)/bin/activate:
	@echo "→ Creating virtual environment in $(VENV)/"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	@echo "→ Installing Python dependencies …"
	$(PIP) install bleak matplotlib
	@echo ""
	@echo "✓  Done. Run 'make check-sys' to verify system prerequisites."

# ── System prerequisites check ────────────────────────────────────────────────

check-sys:
	@echo "── System prerequisites ──────────────────────"
	@echo -n "  python3:     "; python3 --version 2>&1 || echo "MISSING – install python3"
	@echo -n "  bluetoothd:  "
	@systemctl is-active bluetooth 2>/dev/null && echo "running ✓" || \
	  (echo "not running – try: sudo systemctl start bluetooth")
	@echo -n "  BlueZ tools: "
	@which bluetoothctl >/dev/null 2>&1 && bluetoothctl --version 2>&1 || \
	  echo "MISSING – install bluez:  sudo apt install bluez"
	@echo -n "  D-Bus:       "
	@which dbus-daemon >/dev/null 2>&1 && echo "available ✓" || \
	  echo "MISSING – install dbus:  sudo apt install dbus"
	@echo -n "  hci device:  "
	@hciconfig 2>/dev/null | grep -q "hci" && hciconfig 2>/dev/null | grep "hci" | head -3 || \
	  echo "no hci device found – is the dongle plugged in? (sudo apt install bluez)"
	@echo "──────────────────────────────────────────────"
	@echo ""
	@echo "If the script fails with 'org.bluez.Error.NotReady', run:"
	@echo "  sudo systemctl start bluetooth"
	@echo "  sudo hciconfig hci0 up"

# ── Run targets ───────────────────────────────────────────────────────────────

run: install
	$(PYTHON) $(SCRIPT) monitor --timeout $(TIMEOUT)

run-plot: install
	$(PYTHON) $(SCRIPT) monitor --plot --timeout $(TIMEOUT)

scan: install
	$(PYTHON) $(SCRIPT) scan

run-addr: install
	@if [ -z "$(ADDR)" ]; then \
	  echo "Usage:  make run-addr ADDR=XX:XX:XX:XX:XX:XX"; exit 1; fi
	$(PYTHON) $(SCRIPT) monitor --addr $(ADDR) --timeout $(TIMEOUT)

dump: install
	$(PYTHON) $(SCRIPT) monitor --dump-services \
	  $(if $(ADDR),--addr $(ADDR),)

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	@echo "→ Removing $(VENV)/"
	rm -rf $(VENV)

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  make              install dependencies"
	@echo "  make run          auto-discover and stream HR"
	@echo "  make run-plot     stream HR + open live chart window"
	@echo "  make scan         list nearby BLE devices"
	@echo "  make run-addr ADDR=<MAC>   connect to specific device"
	@echo "  make dump [ADDR=<MAC>]     dump all GATT services"
	@echo "  make check-sys    verify BlueZ / D-Bus prerequisites"
	@echo "  make clean        remove .venv"
	@echo ""
