import traceback
import logging
import os

from typing import Optional
from multiprocess import Queue


class TEGSenseHIL:
    def __init__(
        self,
        name: str,
        qin: Queue,
        qout: Queue,
        pq: Queue,
        adv,
        connection,
        service,
        output_raw: Optional[str] = None,
    ):
        self.log = logging.getLogger(f"tegsense.{name}")
        self.last_ping = 0

        self.adv = adv
        self.uart_conn = connection
        self.uart_service = service

        self.qin = qin
        self.qout = qout
        self.pq = pq

        self.name = name
        if output_raw is not None:
            self.output_raw = output_raw

            self.raw_serial_in_fn = f"{self.output_raw}.in.bin"
            self.raw_serial_in = open(self.raw_serial_in_fn, "wb")

            self.raw_serial_out_fn = f"{self.output_raw}.out.bin"
            self.raw_serial_out = open(self.raw_serial_out_fn, "wb")
        else:
            self.raw_serial_in = None
            self.raw_serial_out = None

    def flush(self):
        pass

    def send(self, cmd):
        try:
            if hasattr(cmd, "buffer"):
                tx = cmd.buffer.buffer.tobytes()
            else:
                tx = cmd

            if self.raw_serial_out is not None:
                self.raw_serial_out.write(tx)

            if self.uart_conn.connected:
                self.uart_service.write(tx)

            return True
        except:
            self.log.error("Sending failed")
            self.log.error(traceback.format_exc())
            return False

    def close(self):
        if self.raw_serial_in is not None:
            self.raw_serial_in.close()
            self.raw_serial_in = None
            if os.path.getsize(self.raw_serial_in_fn) == 0:
                self.log.warning(
                    f"Input file {self.raw_serial_in_fn} is empty, removing..."
                )
                os.remove(self.raw_serial_in_fn)
        if self.raw_serial_out is not None:
            self.raw_serial_out.close()
            self.raw_serial_out = None
            if os.path.getsize(self.raw_serial_out_fn) == 0:
                self.log.warning(
                    f"Output file {self.raw_serial_out_fn} is empty, removing..."
                )
                os.remove(self.raw_serial_out_fn)

    def read_uart(self, size: int = -1):
        if size < 0:
            size = self.uart_service.in_waiting
        data = self.uart_service.read(size)
        if data is not None:
            data = bytes(data)
        return data

    def process_uart(self):
        to_read = 0
        data = None
        if self.uart_conn and self.uart_conn.connected:
            to_read = self.uart_service.in_waiting
            if to_read > 0:
                data = self.read_uart(to_read)
                if (data is not None) and (self.raw_serial_in is not None):
                    self.raw_serial_in.write(data)

        return data
