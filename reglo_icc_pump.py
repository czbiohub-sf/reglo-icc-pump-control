from enum import Enum
import math
import time
from typing import (
    Any, Callable, Dict, Iterable, List, Literal, Optional, TextIO, Union)

import serial


__all__ = ["RegloIccPump"]


class _enums:
    class PumpDirection(Enum):
        """Pump rotor rotation direction, as viewed from the front"""

        #: Clockwise
        CW = "cw"

        #: Counter-clockwise
        CCW = "ccw"

        def opposite(self) -> '_enums.PumpDirection':
            """Return the opposite direction"""
            return self.CW if type(self)(self) == self.CCW else self.CCW


_PumpDirectionOrLiteral = Union[_enums.PumpDirection, Literal["cw", "ccw"]]


class _errors:
    class RegloIccPumpError(Exception):
        """Superclass of all other errors"""
        pass

    class CommandTimeout(RegloIccPumpError):
        """No response was received to a command"""
        pass

    class InvalidResponse(RegloIccPumpError):
        """Data received from the pump did not match expectations"""
        pass

    class RemoteError(RegloIccPumpError):
        """The pump responded to a command with an error"""
        pass

    class InvalidTubingId(RegloIccPumpError):
        """The pump reported the specified tubing inner diameter is invalid"""
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

    dispense_dirs: Dict[int, _PumpDirectionOrLiteral]
    _pump_addr: int
    _channel_nos: List[int]
    _pump_serial_no: str
    _pump_model_no: str
    _pump_sw_ver: str
    _pump_head_code: str

    def __init__(
            self,
            ser_port: serial.Serial,
            pump_addr: int = 1,
            dispense_dirs: Optional[
                Dict[int, _PumpDirectionOrLiteral]] = None,
            tubing_ids: Optional[Dict[int, float]] = None,
            ):
        """
        Initialize a driver instance using the specified serial port and
        perform initial configuration of the pump.

        :param ser_port: `serial.Serial` instance (or something with a
            compatible interface) to use for communications. Note that the
            `timeout` and `baudrate` attributes will be re-set if they exist.
        :param pump_addr: Pump address. If not daisy-chaining, usually this
            should be left as default. Pumps are supposed to ship with the
            address set to 1.
        :param dispense_dirs: Mapping of channel numbers to rotation directions
            defining the "dispense" direction for each channel as used by
            :meth:`dispense_vol` and :meth:`aspirate_vol`.
        :param tubing_ids: Mapping of channel numbers to the inner diameter of
            tubing used on each channel (see :meth:`set_tubing_id`). If
            ``None``, the pump will use whatever values were in its memory.

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        self.ser_port = ser_port
        if hasattr(ser_port, 'timeout'):
            self.ser_port.timeout = self.CMD_TIMEOUT_S
        if hasattr(ser_port, 'baudrate'):
            self.ser_port.baudrate = self.BAUDRATE
        self._pump_addr = pump_addr
        self._run_cmd(f"{self.pump_addr}~1")
        n_channels = self._ask_num_channels()
        self._channel_nos = list(range(1, n_channels+1))
        self.dispense_dirs = {
            x: self.DEFAULT_DISPENSE_DIR for x in self.channel_nos}
        if dispense_dirs is not None:
            self.dispense_dirs.update({
                k: self.PumpDirection(v) for (k, v) in dispense_dirs.items()})
        self.tubing_ids: Dict[int, float] = {}
        if tubing_ids is not None:
            for ch_no, tubing_id in tubing_ids.items():
                self.set_tubing_id(ch_no, tubing_id)
        self._pump_serial_no = self._ask_serial_no()
        self._pump_model_no, self._pump_sw_ver, self._pump_head_code = \
            self._ask_pump_info()

    @classmethod
    def from_serial_portname(cls, portname: str, *args, **kwargs
                             ) -> 'RegloIccPump':
        """
        Opens a serial port by name and initializes a :class:`RegloIccPump`
        instance with it

        Parameters and exceptions are the same as for :meth:`__init__`, except
        that ``portname`` takes the place of ``ser_port``, and pyserial may
        raise :exc:`serial.SerialException`.

        :param portname: Port identifier to pass to ``serial.Serial()``,
            e.g. ``"COM42"``, ``"/dev/ttyACM41"``, etc.

        :returns: New :class:`RegloIccPump` instance
        """
        ser_port = serial.Serial(
            portname, cls.BAUDRATE, timeout=cls.CMD_TIMEOUT_S)
        return cls(ser_port, *args, **kwargs)

    def _ask_num_channels(self) -> int:
        return self._run_query(f"{self.pump_addr}xA", (int,))[0]

    def _ask_serial_no(self) -> str:
        return self._run_query(f"{self.pump_addr}xS", (str,))[0]

    def _ask_pump_info(self) -> List[str]:
        return self._run_query(f"{self.pump_addr}#", (str, str, str))

    def _assert_valid_ch_no(self, ch_no: int) -> None:
        if ch_no not in self.channel_nos:
            raise ValueError(f"Invalid channel number: {ch_no!r}")

    def _send_cmd(self, cmd: str) -> None:
        # print("XXXX cmd is", cmd)
        self.ser_port.write(cmd.encode() + b"\r")

    def _run_cmd(self, cmd: str, check_success: bool = True) -> bytes:
        self._send_cmd(cmd)
        resp = self.ser_port.read(1)
        if not resp:
            raise self.CommandTimeout()
        if resp not in b"*#-+":
            raise self.InvalidResponse()  # TODO descriptive messages for these
        if check_success and resp != b"*":
            raise self.RemoteError()
        return resp

    def _run_query(self, cmd: str, field_types: Iterable[Callable]
                   ) -> List[Any]:
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

    def set_tubing_id(self, ch_no: int, inner_diam: float) -> float:
        """
        Sets the inner diameter of the tubing for a given channel

        :param ch_no: Pump channel number
        :param inner_diam: Tubing, inner diameter, in mm. Must match one of
            the values listed in the pump documentation.

        :returns: The value reported back by the pump, in mm

        :raises InvalidTubingId: if the pump rejected the given value
        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        self._assert_valid_ch_no(ch_no)
        try:
            self._run_cmd(
                f"{ch_no}++{self.pump_addr}{round(inner_diam * 100.):04d}")
        except self.RemoteError:
            raise self.InvalidTubingId(inner_diam)
        resp_val, resp_unit = self._run_query(
            f"{ch_no}++{self.pump_addr}", [float, str])
        self.tubing_ids[ch_no] = resp_val
        return resp_val

    def pump_vol(
            self,
            ch_no: int,
            direction: _PumpDirectionOrLiteral,
            vol: float,  # mL
            rate: float,  # mL/minute
            blocking: bool = True
            ) -> None:
        """
        Commands the pump to pump a volume of liquid with a specified rotation
        direction and flow rate

        :param ch_no: Pump channel number
        :param direction: Direction the pump rotor should rotate in
        :param vol: Volume to pump in mL
        :param rate: Pump rate in mL/minute
        :param blocking: If true, only returns after pump operation finishes,
            otherwise returns immediately; defaults to ``True``

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
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

    def dispense_vol(self, ch_no: int, vol: float, rate: float,
                     *args, **kwargs) -> None:
        """
        Similar to :meth:`pump_vol` except rotation direction is determined by
        configuration (pump rotates in the "dispense" direction as set for
        this channel)

        Arguments and exceptions are the same as for :meth:`pump_vol` except
        that there is no ``direction`` parameter.
        """
        self._assert_valid_ch_no(ch_no)
        self.pump_vol(
            ch_no=ch_no,
            direction=self.dispense_dirs[ch_no],
            vol=vol,
            rate=rate,
            **kwargs)

    def aspirate_vol(self, ch_no: int, vol: float, rate: float, **kwargs
                     ) -> None:
        """
        Similar to :meth:`pump_vol` except rotation direction is determined by
        configuration (pump rotates *opposite to* the "dispense" direction as
        set for this channel)

        Arguments and exceptions are the same as for :meth:`pump_vol` except
        that there is no ``direction`` parameter.
        """
        self._assert_valid_ch_no(ch_no)
        self.pump_vol(
            ch_no=ch_no,
            direction=self.PumpDirection(self.dispense_dirs[ch_no]).opposite(),
            vol=vol,
            rate=rate,
            **kwargs)

    def is_running(self, ch_no: int) -> bool:
        """
        Check whether the specified channel is currently pumping

        :param ch_no: Pump channel number

        :returns: `True` if specified channel is currently busy pumping,
            `False` if not

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        self._assert_valid_ch_no(ch_no)
        result = self._run_cmd(
            f"{ch_no}E{self.pump_addr}", check_success=False)
        return result == b"+"

    def wait_for_stop(self, ch_no: Optional[int] = None) -> None:
        """
        Poll the status of a particular channel (or all channels) until
        pumping is complete.

        :param ch_no: Channel number to check; if ``None``, check all channels

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        if ch_no is None:
            for ch_no_ in self.channel_nos:
                self.wait_for_stop(ch_no_)
            return
        while self.is_running(ch_no):
            pass
        # print(f"XXXX done waiting for {ch_no}")

    def show_msg(self, msg: str) -> None:
        """
        Shows a message on the display, if present.

        :param msg: Text to display, up to 15 characters

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        self._run_cmd(f"{self.pump_addr}DA{msg[:15]}")

    @property
    def pump_addr(self) -> int:
        """Pump address -- see :meth:`__init__`"""
        return self._pump_addr

    @property
    def channel_nos(self) -> List[int]:
        """List of valid channel numbers"""
        return list(self._channel_nos)

    @property
    def model_no(self) -> str:
        """Model number reported by the pump"""
        return self._pump_model_no

    @property
    def serial_no(self) -> str:
        """Serial number reported by the pump"""
        return self._pump_serial_no

    @property
    def sw_ver(self) -> str:
        """Software version reported by the pump"""
        return self._pump_sw_ver

    @property
    def head_code(self) -> str:
        return self._pump_head_code

    @staticmethod
    def _format_vol_type2(vol: float) -> str:
        left, right = f"{vol:.3e}".rsplit("e", 1)
        m_str = "".join(left.split("."))
        exp = int(right)
        return f"{m_str}{exp:+1d}"

    @staticmethod
    def _format_discrete_type2(vol: float) -> str:
        left, right = f"{vol:.3e}".rsplit("e", 1)
        m_str = "".join(left.split("."))
        exp = int(right)
        return f"{m_str}{exp:+1d}"
