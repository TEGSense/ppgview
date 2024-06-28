import numpy as np
import json

from ppgview import command

syncword = b"\xEF\xBE\xAD\xDE"


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return str(obj)  # .tolist()
        return json.JSONEncoder.default(self, obj)


def cfg_get_ADCRange(cfg):
    # Get ADC range.
    adcrng = cfg & ~0x9F
    return command.decode_ADCRange(adcrng)


def cfg_get_SampleRate(cfg):
    # Get sample rate in Hz.
    sr = cfg & ~0xE3
    return command.decode_SampleRate(sr)


def cfg_get_PulseWidth(cfg):
    # Get pulse width in µs.
    pw = cfg & ~0xFC
    return command.decode_PulseWidth(pw)


def cfg_get_ADCBits(cfg):
    # Get ADC resolution in bits.
    pw = cfg & ~0xFC
    return command.decode_ADCBits(pw)


def fifo_cfg_get_SampleAvg(fifo_cfg):
    sa = fifo_cfg & 0xE0
    return command.decode_SampleAvg(sa)


class PacketInvalidSyncword(Exception):
    pass


class PacketTooSmall(Exception):
    pass


class PacketInvalid(Exception):
    pass


def parse(buf, old_packets=False):
    if buf[:4] != syncword:
        raise PacketInvalidSyncword(f"Invalid syncword: 0x{buf[:4].hex()}")

    if old_packets:
        # Old packet definition:
        packet = dict(
            pid=int(np.frombuffer(buf[4:6], dtype="<u2", count=1)[0]),
            # 2byte pad
            time=int(np.frombuffer(buf[8:12], dtype="<u4", count=1)[0]),
            cfg=int(np.frombuffer(buf[12:13], dtype="<u1", count=1)[0]),
            fifo_cfg=int(np.frombuffer(buf[13:14], dtype="<u1", count=1)[0]),
            red_pa=int(np.frombuffer(buf[14:15], dtype="<u1", count=1)[0]),
            ir_pa=int(np.frombuffer(buf[15:16], dtype="<u1", count=1)[0]),
            N=int(np.frombuffer(buf[16:18], dtype="<u2", count=1)[0]),
            # 2byte pad
        )
        packet["cp_cfg"] = 0x00
    else:
        # New packet definition:
        packet = dict(
            time=int(np.frombuffer(buf[4:8], dtype="<u4", count=1)[0]),
            pid=int(np.frombuffer(buf[8:10], dtype="<u2", count=1)[0]),
            cfg=int(np.frombuffer(buf[10:11], dtype="<u1", count=1)[0]),
            fifo_cfg=int(np.frombuffer(buf[11:12], dtype="<u1", count=1)[0]),
            cp_cfg=int(np.frombuffer(buf[12:13], dtype="<u1", count=1)[0]),
            red_pa=int(np.frombuffer(buf[13:14], dtype="<u1", count=1)[0]),
            ir_pa=int(np.frombuffer(buf[14:15], dtype="<u1", count=1)[0]),
            # 1byte pad
            N=int(np.frombuffer(buf[16:18], dtype="<u2", count=1)[0]),
            # 2byte pad
        )
    if packet["N"] > 100:
        raise PacketInvalid(f"Invalid packet length: {packet['N']}")
    packet["adc_range"] = cfg_get_ADCRange(packet["cfg"])
    packet["sample_rate"] = cfg_get_SampleRate(packet["cfg"])
    packet["pulse_width"] = cfg_get_PulseWidth(packet["cfg"])
    packet["adc_bits"] = cfg_get_ADCBits(packet["cfg"])
    packet["sample_avg"] = fifo_cfg_get_SampleAvg(packet["fifo_cfg"])
    (
        packet["collection_period"],
        packet["startup_timeout"],
    ) = command.decode_CollectionMode(packet["cp_cfg"])
    packet["dt"] = packet["sample_avg"] / packet["sample_rate"] * 1000
    packet["time"] = np.arange(0, packet["N"]) * packet["dt"] + packet["time"]

    packet["len"] = 4 + 4 + 2 + 1 * 5 + 1 + 2 + 2 + packet["N"] * 4 * 2
    if len(buf) < packet["len"]:
        raise PacketTooSmall(f"{len(buf)} < {packet['len']}")

    adc_to_uA = -1.0 * packet["adc_range"] / 1000.0 / 2**18
    sep = packet["N"] * 4 + 20
    packet["red"] = (
        np.frombuffer(buf[20:sep], dtype="<u4", count=packet["N"]) * adc_to_uA
    )
    packet["ir"] = (
        np.frombuffer(buf[sep : packet["len"]], dtype="<u4", count=packet["N"])
        * adc_to_uA
    )

    return packet


def parse_all(buffer: bytes, start=0, end=-1):
    packets = []
    bi = start
    bend = end if end >= 0 else len(buffer)
    try:
        while True:
            bi += buffer[bi:bend].find(syncword)
            pkt = parse(buffer[bi:bend])
            bi += pkt["len"]
            packets.append(pkt)
    except PacketInvalidSyncword:
        bi += 1
    except PacketTooSmall:
        pass
    except PacketInvalid:
        bi += 1

    return packets
