import time
from multiprocess import Queue
from logging import getLogger
import datetime as dt

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import Advertisement

from ppgview.sensor import TEGSenseSensor


class TEGSenseBLE:
    def __init__(self):
        self.log = getLogger("TEGSenseBLE")
        self.sensor = None
        self.data = None
        self.dt = None

    def connect(self):
        qin = Queue()
        qout = Queue()
        pq = Queue()

        # Find sensors.
        self.log.info("Scanning for TEGSense sensor...")
        ble = BLERadio()
        device_adv = None
        for adv in ble.start_scan(Advertisement, timeout=None):
            if adv.complete_name is None:
                continue
            cn = adv.complete_name.lower()
            if "tegsense" in cn:
                name = adv.complete_name
                self.log.info(f"Found tegsense {name} (Address: {adv.address.string})")
                device_adv = adv
                ble.stop_scan()
                break

        if device_adv is None:
            self.log.error("Device not found!")
            raise RuntimeError("Could not find tegsense sensor!")

        device_name = device_adv.complete_name

        self.dt = dt.datetime.now()
        self.dtnow = self.dt.strftime("%Y%m%d_%H%M%S")
        nowstamp = f"tegsense-{self.dtnow}"
        self.log.info(f"Connecting to {device_adv.complete_name}.")
        self.sensor = TEGSenseSensor(
            device_name, ble, device_adv, qout, qin, pq, nowstamp
        )
        self.log.info(f"Connecting to device {self.sensor}")
        if self.sensor.connect():
            self.log.info(" - Connected.")
        else:
            self.sensor = None
            self.log.error(" - Failed to connect to BLE device.")
            raise RuntimeError("Could not connect to tegsense sensor!")

        self.bi = 0
        self.bend = 0

    def disconnect(self):
        self.log.info("Disconnecting sensor...")
        if self.sensor is not None:
            self.sensor.disconnect()
            self.sensor.hil.close()
            self.sensor = None
        else:
            self.log.warning("Tried to disconnect sensor, but it was not connected!")

    def wait_for_data(self):
        # self.log.info("Waiting for more data...")
        if self.sensor is None:
            raise RuntimeError("Sensor not connected!")
        disconnected = 0
        while True:
            # Connected?
            if not self.sensor.connected:
                disconnected += 1
                if disconnected == 1:
                    self.log.warning(
                        f"Sensor {self.sensor.name} disconnected. Waiting for more data..."
                    )
                if disconnected > 5:
                    raise RuntimeError("Sensor disconnected!")
                time.sleep(1)

            # Collect data.
            data = self.sensor.hil.process_uart()
            if data is not None and len(data) > 0:
                self.data = data
                return data
            time.sleep(0.1)

    def send(self, cmd):
        if self.sensor is None:
            raise RuntimeError("Sensor not connected!")
        self.sensor.hil.send(cmd)
