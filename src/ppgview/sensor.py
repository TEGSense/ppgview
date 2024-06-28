# ATW: We need a patched UARTService class with a larger buffer. The default
# is tiny and does not work when trying to send large packets.
# from adafruit_ble.services.nordic import UARTService
from ppgview.nordic import UARTService
from ppgview import hil


class TEGSenseSensor:
    def __init__(self, name, ble, advertisement, qout, qin, pq, nowstamp):
        self.name = name
        self.ble = ble
        self.advertisement = advertisement
        self.connection = None
        self.service = None
        self.hil = hil.TEGSenseHIL(
            name, qout, qin, pq, advertisement, None, None, nowstamp
        )

    def disconnect(self):
        if (self.connection is not None) and (self.connection.connected):
            self.connection.disconnect()
        self.connection = None
        self.service = None
        self.hil.uart_conn = None
        self.hil.uart_service = None

    def connect(self, timeout=10):
        self.disconnect()
        self.connection = self.ble.connect(self.advertisement, timeout=timeout)
        if self.connection.connected:
            self.service = self.connection[UARTService]
            self.hil.uart_conn = self.connection
            self.hil.uart_service = self.service
            return True
        else:
            self.connection = None
            return False

    @property
    def connected(self):
        return self.connection and self.connection.connected

    def __str__(self) -> str:
        return f"{self.name} <{self.advertisement.address.string}>"

    def __repr__(self) -> str:
        return self.__str__(self)
