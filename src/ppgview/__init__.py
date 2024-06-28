import time
import traceback
from queue import Queue, Empty

from tornado.ioloop import IOLoop
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.plotting import figure, ColumnDataSource
from bokeh.layouts import column, row, gridplot
from bokeh.models import Select, Slider, Button, DatetimeTickFormatter
from threading import Thread

import logging
import datetime as dt

import numpy as np

from ppgview.ble import TEGSenseBLE
from ppgview import packet, command


class BokehApp:
    MaxRate = 1000  # Hz
    MaxDuration = 10 * 60 * 60  # 10 hours

    rollover = 300
    clear_plot = False

    time_buffer = np.empty(MaxRate * MaxDuration, dtype="datetime64[ms]")
    ir_ppg_buffer = np.empty(MaxRate * MaxDuration)
    red_ppg_buffer = np.empty(MaxRate * MaxDuration)

    control_updates = None
    last_collection_mode = command.encode_CollectionMode(3000, 30)

    write_index = 0
    read_index = 0
    sps = 100
    outgoing = Queue()

    def __init__(self):
        thread = Thread(target=self.ble_thread, daemon=True)
        thread.start()

        io_loop = IOLoop.current()
        server = Server(
            applications={"/myapp": Application(FunctionHandler(self.make_document))},
            io_loop=io_loop,
            port=5001,
        )
        server.start()
        server.show("/myapp")

        try:
            io_loop.start()
        except KeyboardInterrupt:
            print("Keyboard interrupt, stopping.")
            io_loop.stop()

    def ble_thread(self):
        log = logging.getLogger("ble")
        ble = TEGSenseBLE()

        buf = bytearray(1024 * 1024 * 100)
        bi = 0
        bend = 0
        syncword = b"\xEF\xBE\xAD\xDE"

        connection_time = None
        mcu_offset = None
        while True:
            try:
                ble.connect()
                connection_time = np.datetime64(dt.datetime.now())
                mcu_offset = None

                # Clear any existing items in the outgoing queue.
                try:
                    while True:
                        self.outgoing.get_nowait()
                except Empty:
                    pass

                # Wait for data.
                while ble.wait_for_data():
                    # Add data to buffer.
                    data_len = len(ble.data)
                    if bend + data_len > len(buf):
                        log.warning("Buffer overflow, resetting.")
                        bend = 0
                        bi = 0
                    buf[bend : bend + data_len] = ble.data
                    bend += data_len

                    # Send any outgoing commands.
                    try:
                        while True:
                            cmd = self.outgoing.get_nowait()
                            which, value = command.parse_command(cmd)
                            log.info(
                                f"Sending command: {cmd.hex()} -> {which.name}, {value} (0x{value:X})"
                            )
                            ble.send(cmd)
                    except Empty:
                        pass

                    # Try to parse any available messages.
                    try:
                        while True:
                            bi += buf[bi:bend].find(syncword)
                            pkt = packet.parse(buf[bi:bend])
                            bi += pkt["len"]
                            N = pkt["N"]

                            # If this is the first packet, set the MCU offset and store the packet for the controls to update.
                            if mcu_offset is None:
                                mcu_offset = pkt["time"][0]
                                log.info(
                                    f"MCU offset: {mcu_offset} = {connection_time}"
                                )
                                self.control_updates = pkt

                            self.time_buffer[
                                self.write_index : self.write_index + N
                            ] = (pkt["time"] - mcu_offset).astype(
                                "timedelta64[ms]"
                            ) + connection_time
                            self.ir_ppg_buffer[
                                self.write_index : self.write_index + N
                            ] = pkt["ir"]
                            self.red_ppg_buffer[
                                self.write_index : self.write_index + N
                            ] = pkt["red"]
                            self.write_index += N
                    except packet.PacketInvalidSyncword:
                        bi += 1
                    except packet.PacketTooSmall:
                        pass
                    except packet.PacketInvalid:
                        bi += 1
            except:
                log.error(traceback.format_exc())
                ble.disconnect()
                time.sleep(1)
                continue

    def change_adc_range(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"ADC range changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(
                command.Command.ADCRange, command.encode_ADCRange(int(new))
            )
        )

    def change_sample_rate(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Sample rate changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(
                command.Command.SampleRate, command.encode_SampleRate(int(new))
            )
        )

    def change_pulse_width(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Pulse width changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(
                command.Command.PulseWidth,
                command.encode_PulseWidth(int(new.split("/")[0])),
            )
        )

    def change_sample_avg(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Sample average changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(
                command.Command.SampleAvg, command.encode_SampleAvg(int(new))
            )
        )

    def change_pa_red(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"PA Red changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(command.Command.RedLEDPA, int(new * 255.0 / 51.0))
        )

    def change_pa_ir(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"PA IR changed from {old} to {new}.")
        self.outgoing.put(
            command.make_command(command.Command.IRLEDPA, int(new * 255.0 / 51.0))
        )

    def change_collection_period(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Collection period changed from {old} to {new}.")
        _, st = command.decode_CollectionMode(self.last_collection_mode)
        self.last_collection_mode = command.encode_CollectionMode(int(new), st)
        self.outgoing.put(
            command.make_command(
                command.Command.CollectionMode, self.last_collection_mode
            )
        )

    def change_startup_timeout(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Startup timeout changed from {old} to {new}.")
        cp, _ = command.decode_CollectionMode(self.last_collection_mode)
        self.last_collection_mode = command.encode_CollectionMode(cp, int(new))
        self.outgoing.put(
            command.make_command(
                command.Command.CollectionMode, self.last_collection_mode
            )
        )

    def send_reboot(self):
        log = logging.getLogger("update")
        log.info(f"Sending reboot command.")
        self.outgoing.put(command.make_command(command.Command.Reboot, 1))

    def change_rollover(self, attr, old, new):
        log = logging.getLogger("update")
        log.info(f"Rollover changed from {old} to {new}.")
        self.rollover = int(new)

    def clear_plot(self):
        log = logging.getLogger("update")
        log.info(f"Clearing plot.")
        self.clear_plot = True

    def make_document(self, doc):
        # Data plots.
        source = ColumnDataSource(
            {
                "time": np.empty(0, dtype="datetime64[ms]"),
                "IR": np.empty(0, np.float64),
                "Red": np.empty(0, np.float64),
            }
        )

        fig_ir = figure(
            title="Infrared PPG Waveforms",
            sizing_mode="stretch_both",
            x_axis_label="Time (s)",
            x_axis_type="datetime",
            y_axis_label="Current (µA)",
        )
        fig_ir.line(source=source, x="time", y="IR", color="blue")
        fig_ir.xaxis.formatter = DatetimeTickFormatter(seconds="%H:%M:%S")

        fig_red = figure(
            title="Red PPG Waveforms",
            sizing_mode="stretch_both",
            x_axis_label="Time (s)",
            x_axis_type="datetime",
            y_axis_label="Current (µA)",
            x_range=fig_ir.x_range,
        )
        fig_red.line(source=source, x="time", y="Red", color="blue")
        fig_red.xaxis.formatter = DatetimeTickFormatter(seconds="%H:%M:%S")

        # plot_layout = column(fig_ir, fig_red, sizing_mode='stretch_both')
        plot_layout = gridplot([[fig_ir], [fig_red]], sizing_mode="stretch_both")

        # Controls.
        sel_adc_range = Select(
            title="ADC Range (nA):",
            value="4096",
            options=["2048", "4096", "8192", "16384"],
            width_policy="max",
        )
        sel_adc_range.on_change("value", self.change_adc_range)

        sel_sample_rate = Select(
            title="Sample Rate (Hz):",
            value="100",
            options=["50", "100", "200", "400", "800", "1000", "1600", "3200"],
            width_policy="max",
        )
        sel_sample_rate.on_change("value", self.change_sample_rate)

        sel_pulse_width = Select(
            title="Pulse Width (µs / ADC bits):",
            value="118 / 16",
            options=["69 / 15", "118 / 16", "215 / 17", "411 / 18"],
            width_policy="max",
        )
        sel_pulse_width.on_change("value", self.change_pulse_width)

        sel_sample_avg = Select(
            title="Sample Average:",
            value="1",
            options=["1", "2", "4", "8", "16", "32"],
            width_policy="max",
        )
        sel_sample_avg.on_change("value", self.change_sample_avg)

        sld_pa_red = Slider(
            title="Red LED Current (mA):", value=0, start=0, end=51, step=0.2
        )
        sld_pa_red.on_change("value", self.change_pa_red)

        sld_pa_ir = Slider(
            title="IR LED Current (mA):", value=0, start=0, end=51, step=0.2
        )
        sld_pa_ir.on_change("value", self.change_pa_ir)

        sld_collection_period = Slider(
            title="Collection period (ms):", value=0, start=0, end=7500, step=500
        )
        sld_collection_period.on_change("value", self.change_collection_period)

        sld_startup_timeout = Slider(
            title="Startup timeout (s):", value=0, start=0, end=150, step=10
        )
        sld_startup_timeout.on_change("value", self.change_startup_timeout)

        btn_reboot = Button(
            label="Flash Config and Reboot", button_type="success", width_policy="max"
        )
        btn_reboot.on_click(self.send_reboot)

        sld_rollover = Slider(
            title="Rollover (samples):", value=500, start=100, end=2000, step=25
        )
        sld_rollover.on_change("value", self.change_rollover)

        btn_clear_plot = Button(
            label="Clear Plot", button_type="danger", width_policy="max"
        )
        btn_clear_plot.on_click(self.clear_plot)

        controls_layout = column(
            sel_adc_range,
            sel_sample_rate,
            sel_pulse_width,
            sel_sample_avg,
            sld_pa_ir,
            sld_pa_red,
            sld_collection_period,
            sld_startup_timeout,
            btn_reboot,
            sld_rollover,
            btn_clear_plot,
            width_policy="min",
        )

        layout = row(plot_layout, controls_layout, sizing_mode="stretch_both")

        def update():
            # Clear the plot first?
            if self.clear_plot:
                self.clear_plot = False
                source.data = {
                    "time": np.empty(0, dtype="datetime64[ms]"),
                    "IR": np.empty(0, np.float64),
                    "Red": np.empty(0, np.float64),
                }

            # Update plot if there's new data.
            wi = self.write_index
            if self.read_index < wi:
                source.stream(
                    dict(
                        time=self.time_buffer[self.read_index : wi],
                        IR=self.ir_ppg_buffer[self.read_index : wi],
                        Red=self.red_ppg_buffer[self.read_index : wi],
                    ),
                    rollover=self.rollover,
                )
                self.read_index = wi

            # Do we need to update the controls?
            if self.control_updates is not None:
                pkt = self.control_updates
                self.control_updates = None

                sel_adc_range.value = str(pkt["adc_range"])
                sel_sample_rate.value = str(pkt["sample_rate"])
                sel_pulse_width.value = f"{pkt['pulse_width']} / {pkt['adc_bits']}"
                sel_sample_avg.value = str(pkt["sample_avg"])
                sld_pa_red.value = pkt["red_pa"] * 51.0 / 255.0
                sld_pa_ir.value = pkt["ir_pa"] * 51.0 / 255.0
                sld_collection_period.value = pkt["collection_period"]
                sld_startup_timeout.value = pkt["startup_timeout"]

        doc.add_root(layout)
        doc.add_periodic_callback(update, 50)
        doc.title = "PPGView"


def main():
    # Configure logging.
    handlers = [logging.StreamHandler()]
    dtnow = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    nowstamp = f"ppgview-{dtnow}"
    handlers.append(logging.FileHandler(f"{nowstamp}.log"))
    logging.basicConfig(
        handlers=handlers,
        datefmt="%H:%M:%S",
        format="{name:.<15} {asctime}: [{levelname}] {message}",
        style="{",
        level=logging.INFO,
    )
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    log = logging.getLogger("main()")
    log.info(
        f"Start time: {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}"
    )

    app = BokehApp()
    log.info(f"Finished running. Collected {app.write_index} samples.")
