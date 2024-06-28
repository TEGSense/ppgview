from enum import Enum

import logging

log = logging.getLogger("command")


class Command(Enum):
    NoOp = 0x00
    ADCRange = 0x01
    SampleRate = 0x02
    PulseWidth = 0x04
    SampleAvg = 0x08
    IRLEDPA = 0x10
    RedLEDPA = 0x20
    Reboot = 0x40
    CollectionMode = 0x80


def encode_ADCRange(value: int) -> int:
    if value == 2048:
        return 0x00
    if value == 4096:
        return 0x20
    if value == 8192:
        return 0x40
    if value == 16384:
        return 0x60
    raise Exception(f"Invalid ADC range: {value}")


def decode_ADCRange(value: int) -> int:
    if value == 0x00:
        return 2048
    if value == 0x20:
        return 4096
    if value == 0x40:
        return 8192
    if value == 0x60:
        return 16384
    raise Exception(f"Invalid ADC range: {value}")


def encode_SampleRate(value: int) -> int:
    if value == 50:
        return 0x00
    if value == 100:
        return 0x04
    if value == 200:
        return 0x08
    if value == 400:
        return 0x0C
    if value == 800:
        return 0x10
    if value == 1000:
        return 0x14
    if value == 1600:
        return 0x18
    if value == 3200:
        return 0x1C
    raise Exception(f"Invalid sample rate: {value}")


def decode_SampleRate(value: int) -> int:
    if value == 0x00:
        return 50
    if value == 0x04:
        return 100
    if value == 0x08:
        return 200
    if value == 0x0C:
        return 400
    if value == 0x10:
        return 800
    if value == 0x14:
        return 1000
    if value == 0x18:
        return 1600
    if value == 0x1C:
        return 3200
    raise Exception(f"Invalid sample rate: {value}")


def encode_PulseWidth(value: int) -> int:
    if value == 69:
        return 0x00
    if value == 118:
        return 0x01
    if value == 215:
        return 0x02
    if value == 411:
        return 0x03
    raise Exception(f"Invalid pulse width: {value}")


def decode_PulseWidth(value: int) -> int:
    if value == 0x00:
        return 69
    if value == 0x01:
        return 118
    if value == 0x02:
        return 215
    if value == 0x03:
        return 411
    raise Exception(f"Invalid pulse width: {value}")


def decode_ADCBits(value: int) -> int:
    # value should be the PulseWidth input.
    if value == 0x00:
        return 15
    if value == 0x01:
        return 16
    if value == 0x02:
        return 17
    if value == 0x03:
        return 18
    raise Exception(f"Invalid ADC bits: {value}")


def encode_SampleAvg(value: int) -> int:
    if value == 1:
        return 0x00
    if value == 2:
        return 0x20
    if value == 4:
        return 0x40
    if value == 8:
        return 0x60
    if value == 16:
        return 0x80
    if value == 32:
        return 0xA0
    raise Exception(f"Invalid sample average: {value}")


def decode_SampleAvg(value: int) -> int:
    if value == 0x00:
        return 1
    if value == 0x20:
        return 2
    if value == 0x40:
        return 4
    if value == 0x60:
        return 8
    if value == 0x80:
        return 16
    if value == 0xA0:
        return 32
    raise Exception(f"Invalid sample average: {value}")


def encode_CollectionMode(collection_period: int, startup_timeout: int) -> int:
    if collection_period < 0 or collection_period > 7500:
        raise Exception(f"Invalid collection period: {collection_period}")
    if startup_timeout < 0 or startup_timeout > 150:
        raise Exception(f"Invalid startup timeout: {startup_timeout}")
    cp = int(collection_period / 500)
    st = int(startup_timeout / 10) << 4
    log.info(
        f"encode_CollectionMode: collection_period={collection_period} startup_timeout={startup_timeout}"
    )
    log.info(f"encode_CollectionMode: cp={cp} (0x{cp:02X}) st={st} (0x{st:02X})")
    return cp | st


def decode_CollectionMode(value: int) -> (int, int):
    cp = (value & 0x0F) * 500
    st = ((value & 0xF0) >> 4) * 10
    return (cp, st)


def make_command(cmd: Command, payload: int) -> bytes:
    if payload < 0 or payload > 255:
        raise Exception(f"Invalid payload: {payload}")
    command = bytes([cmd.value, payload])
    return command


def parse_command(command: bytes) -> (Command, int):
    cmd = Command(command[0])
    if cmd == Command.NoOp:
        return (cmd, 0)
    if cmd == Command.ADCRange:
        return (cmd, decode_ADCRange(command[1]))
    if cmd == Command.SampleRate:
        return (cmd, decode_SampleRate(command[1]))
    if cmd == Command.PulseWidth:
        return (cmd, decode_PulseWidth(command[1]))
    if cmd == Command.SampleAvg:
        return (cmd, decode_SampleAvg(command[1]))
    if cmd == Command.IRLEDPA:
        return (cmd, command[1])
    if cmd == Command.RedLEDPA:
        return (cmd, command[1])
    if cmd == Command.Reboot:
        return (cmd, command[1])
    if cmd == Command.CollectionMode:
        return (cmd, command[1])
    raise Exception(f"Invalid command: {cmd} ({command.hex()}) payload {command[1]}")
