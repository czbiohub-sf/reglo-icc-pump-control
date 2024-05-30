from enum import Enum
import math
import time
from typing import Callable, Dict, Iterable, List, Optional, TextIO, Union

import serial


__all__ = ["RegloIccPump"]


class _enums:
    class PumpDirection(Enum):
        CW = "cw"
        CCW = "ccw"

        def opposite(self):
            return self.CW if type(self)(self) == self.CCW else self.CCW


class _errors:
    class RegloIccPumpError(Exception):
        pass

    class CommandTimeout(RegloIccPumpError):
        pass

    class InvalidResponse(RegloIccPumpError):
        pass

    class RemoteError(RegloIccPumpError):
        pass

    class InvalidTubingId(RegloIccPumpError):
        pass


class RegloIccPump:
    BAUDRATE = 9600
    CMD_TIMEOUT_S = 2.

    RegloIccPumpError = _errors.RegloIccPumpError
    CommandTimeout = _errors.CommandTimeout
    InvalidResponse = _errors.InvalidResponse
    RemoteError = _errors.RemoteError
    InvalidTubingId = _errors.InvalidTubingId
    PumpDirection = _enums.PumpDirection

    DEFAULT_DISPENSE_DIR = PumpDirection.CW

    channel_nos: List[int]
    dispense_dirs: Dict[int, PumpDirection]
    pump_addr: int
    pump_serial_no: str
    pump_model_no: str
    pump_sw_ver: str
    pump_head_code: str

    def __init__(
            self,
            ser_port: serial.Serial,
            pump_addr: int = 1,
            dispense_dirs: Optional[
                Dict[int, 'RegloIccPump.PumpDirection']] = None,
            tubing_ids: Optional[Dict[int, float]] = None,
            ):
        self.ser_port = ser_port
        if hasattr(ser_port, 'timeout'):
            self.ser_port.timeout = self.CMD_TIMEOUT_S
        if hasattr(ser_port, 'baudrate'):
            self.ser_port.baudrate = self.BAUDRATE
        self.pump_addr = pump_addr
        self._run_cmd(f"{self.pump_addr}~1")
        n_channels = self._ask_num_channels()
        self.channel_nos = list(range(1, n_channels+1))
        self.dispense_dirs = {
            x: self.DEFAULT_DISPENSE_DIR for x in self.channel_nos}
        if dispense_dirs is not None:
            self.dispense_dirs.update({
                k: self.PumpDirection(v) for (k, v) in dispense_dirs.items()})
        self.tubing_ids = {}
        if tubing_ids is not None:
            for ch_no, tubing_id in tubing_ids.items():
                self.set_tubing_id(ch_no, tubing_id)
        self.pump_serial_no = self._ask_serial_no()
        self.pump_model_no, self.pump_sw_ver, self.pump_head_code = \
            self._ask_pump_info()

    @classmethod
    def from_serial_portname(cls, portname: str, *args, **kwargs):
        ser_port = serial.Serial(
            portname, cls.BAUDRATE, timeout=cls.CMD_TIMEOUT_S)
        return cls(ser_port, *args, **kwargs)

    def _ask_num_channels(self):
        return self._run_query(f"{self.pump_addr}xA", (int,))[0]

    def _ask_serial_no(self):
        return self._run_query(f"{self.pump_addr}xS", (str,))[0]

    def _ask_pump_info(self):
        return self._run_query(f"{self.pump_addr}#", (str, str, str))

    def _assert_valid_ch_no(self, ch_no: int):
        if ch_no not in self.channel_nos:
            raise ValueError(f"Invalid channel number: {ch_no!r}")

    def _send_cmd(self, cmd: str):
        # print("XXXX cmd is", cmd)
        self.ser_port.write(cmd.encode() + b"\r")

    def _run_cmd(self, cmd: str, check_success: bool = True):
        self._send_cmd(cmd)
        resp = self.ser_port.read(1)
        if not resp:
            raise self.CommandTimeout()
        if resp not in b"*#-+":
            raise self.InvalidResponse()  # TODO descriptive messages for these
        if check_success and resp != b"*":
            raise self.RemoteError()
        return resp

    def _run_query(self, cmd: str, field_types: Iterable[Callable]):
        field_types = list(field_types)
        self._send_cmd(cmd)
        resp = self.ser_port.read_until(b"\r\n").decode("ascii").strip()
        if not resp:
            raise self.CommandTimeout()
        resp_fields = resp.rsplit(None, len(field_types) - 1)
        exp_n_fields = len(field_types)
        got_n_fields = len(resp_fields)
        if exp_n_fields != got_n_fields:
            raise self.InvalidResponse(
                f"Expected response with {exp_n_fields} "
                f"data fields, got {got_n_fields}")
        return_vals = []
        for field_idx, field_raw in enumerate(resp_fields):
            try:
                conv = field_types[field_idx](field_raw)
            except ValueError as e:
                raise self.InvalidResponse(
                    f"Failed to convert value in field {field_idx}") from e
            return_vals.append(conv)
        return return_vals

    def set_tubing_id(self, ch_no: int, inner_diam: float):
        self._assert_valid_ch_no(ch_no)
        try:
            self._run_cmd(
                f"{ch_no}++{self.pump_addr}{round(inner_diam * 100.):04d}")
        except RemoteError:
            raise self.InvalidTubingId(inner_diam)
        resp_val, resp_unit = self._run_query(
            f"{ch_no}++{self.pump_addr}", [float, str])
        self.tubing_ids[ch_no] = resp_val

    def pump_vol(
            self,
            ch_no: int,
            direction: Union[str, 'RegloIccPump.PumpDirection'],
            vol: float,  # mL
            rate: float,  # mL/minute
            blocking: bool = True
            ):
        direction = self.PumpDirection(direction)
        dir_cmd = "J" if direction == self.PumpDirection.CW else "K"
        self._run_cmd(f"{ch_no}{dir_cmd}{self.pump_addr}")  # set rotation dir
        self._run_cmd(f"{ch_no}O{self.pump_addr}")  # set to vol/time mode
        self._run_cmd(f"{ch_no}xff{self.pump_addr}1")  # speed from flow rate
        self._run_query(  # set volume
            f"{ch_no}vv{self.pump_addr}{self._format_vol_type2(vol)}", [str])
        self._run_query(  # set flow rate
            f"{ch_no}ff{self.pump_addr}{self._format_vol_type2(rate)}", [str])
        self._run_cmd(f"{ch_no}H{self.pump_addr}")  # start pumping
        if blocking:
            self.wait_for_stop(ch_no)

    def aspirate_vol(self, ch_no: int, vol: float, rate: float, **kwargs):
        self._assert_valid_ch_no(ch_no)
        return self.pump_vol(
            ch_no=ch_no,
            direction=self.dispense_dirs[ch_no].opposite(),
            vol=vol,
            rate=rate,
            **kwargs)

    def dispense_vol(self, ch_no: int, vol: float, rate: float,
                     *args, **kwargs):
        self._assert_valid_ch_no(ch_no)
        return self.pump_vol(
            ch_no=ch_no,
            direction=self.dispense_dirs[ch_no],
            vol=vol,
            rate=rate,
            **kwargs)

    def is_running(self, ch_no: int):
        self._assert_valid_ch_no(ch_no)
        result = self._run_cmd(
            f"{ch_no}E{self.pump_addr}", check_success=False)
        return result == b"+"

    def wait_for_stop(self, ch_no: Optional[int] = None):
        if ch_no is None:
            for ch_no_ in self.channel_nos:
                self.wait_for_stop(ch_no_)
            return
        while self.is_running(ch_no):
            pass
        # print(f"XXXX done waiting for {ch_no}")

    def show_msg(self, msg: str):
        self._run_cmd(f"{self.pump_addr}DA{msg[:15]}")

    @staticmethod
    def _format_vol_type2(vol: float):
        left, right = f"{vol:.3e}".rsplit("e", 1)
        m_str = "".join(left.split("."))
        exp = int(right)
        return f"{m_str}{exp:+1d}"

    @staticmethod
    def _format_discrete_type2(vol: float):
        left, right = f"{vol:.3e}".rsplit("e", 1)
        m_str = "".join(left.split("."))
        exp = int(right)
        return f"{m_str}{exp:+1d}"
