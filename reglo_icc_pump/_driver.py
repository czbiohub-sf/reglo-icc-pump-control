from enum import Enum
import math
import time
from typing import (
    Any, Callable, Dict, Iterable, List, Literal, Optional, TextIO, Tuple,
    Union)

import serial
import serial.tools.list_ports

from . import types


_PumpDirectionOrLiteral = Union[types.PumpDirection, Literal['cw', 'ccw']]


class RegloIccPump:
    BAUDRATE = 9600
    CMD_TIMEOUT_S = 2.

    RegloIccPumpError = types.RegloIccPumpError
    DeviceNotFound = types.DeviceNotFound
    SerialNoMismatch = types.SerialNoMismatch
    CommandTimeout = types.CommandTimeout
    InvalidResponse = types.InvalidResponse
    RemoteError = types.RemoteError
    InvalidTubingId = types.InvalidTubingId
    StallDetectionDetected = types.StallDetectionDetected
    PumpDirection = types.PumpDirection

    DEFAULT_DISPENSE_DIR = PumpDirection.CW
    USB_HW_IDS = {
        (0x265C, 0x0001),
        }

    dispense_dirs: Dict[int, _PumpDirectionOrLiteral]
    _pump_addr: int
    _channel_nos: List[int]
    _pump_serial_no: str
    _pump_model_no: str
    _pump_sw_ver: str
    _pump_head_code: str
    _last_odo_val: dict[int, int]
    _last_odo_val_tstamp: dict[int, float]

    def __init__(
            self,
            ser_port: serial.Serial,
            pump_addr: int = 1,
            dispense_dirs: Optional[
                Dict[int, _PumpDirectionOrLiteral]] = None,
            tubing_ids: Optional[Dict[int, float]] = None,
            serial_no: Optional[str] = None,
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
        :param serial_no: If not ``None``, this will be checked against the
            serial number reported by the pump and :class:`SerialNoMismatch`
            will be raised in case of a mismatch.

        :raises SerialNoMismatch: if the serial number reported by the pump
            doesn't match the one (optionally) specified
        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        self.ser_port = ser_port
        if hasattr(ser_port, 'timeout'):
            self.ser_port.timeout = self.CMD_TIMEOUT_S
        if hasattr(ser_port, 'baudrate'):
            self.ser_port.baudrate = self.BAUDRATE
        self._pump_addr = pump_addr
        self._pump_serial_no = self._ask_serial_no()
        if serial_no is not None and self.serial_no != serial_no:
            raise self.SerialNoMismatch(
                f"Wrong pump serial number (expected {serial_no!r}, "
                f"pump reported {self.serial_no!r})")
        n_channels = self._ask_num_channels()
        self._run_cmd(f"{self.pump_addr}~1")
        self._channel_nos = list(range(1, n_channels+1))
        self._init_channel_odos()
        self.dispense_dirs = {
            x: self.DEFAULT_DISPENSE_DIR for x in self.channel_nos}
        if dispense_dirs is not None:
            self.dispense_dirs.update({
                k: self.PumpDirection(v) for (k, v) in dispense_dirs.items()})
        self.tubing_ids: Dict[int, float] = {}
        if tubing_ids is not None:
            for ch_no, tubing_id in tubing_ids.items():
                self.set_tubing_id(ch_no, tubing_id)
        self._pump_model_no, self._pump_sw_ver, self._pump_head_code = \
            self._ask_pump_info()

    @classmethod
    def list_connected_devices(
            cls, usb_vidpid: Optional[Tuple[int, int]] = None
            ) -> List[Tuple[str, Optional[str]]]:
        """
        Get a list of all pumps currently connected via USB. Detection is
        based on the USB vendor/product ID values reported by the OS. This
        method does not attempt to open the devices or verify that they are
        actually accessible. Pumps connected via USB-to-RS-232 interfaces will
        not be detected.

        Only supported on Windows, macOS and Linux.

        :param usb_vidpid: A tuple ``(vid, pid)`` specifying a particular
            USB vendor and product ID to look for instead of using the default
            list of IDs.
        :returns: A list of tuples ``(portname, location)`` where ``portname``
            the name of a logical serial port (e.g. ``"COM42"`` or
            ``"/dev/ttyACM0"``) as recognized by pySerial and ``location`` is
            a string representing which actual USB port the pump is connected
            to. The latter is useful for connecting to a specific pump (see
            :meth:`from_usb_location`) since they don't expose a serial number
            via USB descriptors.
            ``location`` may be ``None`` on platforms other than Windows, MacOS
            or Linux.
        """
        usb_vidpids = (
            {tuple(usb_vidpid)} if usb_vidpid is not None
            else set(cls.USB_HW_IDS)
            )
        return [
            (info.device, info.location)
            for info in serial.tools.list_ports.comports()
            if (info.vid, info.pid) in usb_vidpids
            ]

    @classmethod
    def open_first_device(
            cls,
            usb_vidpid: Optional[Tuple[int, int]] = None,
            **kwargs) -> 'RegloIccPump':
        """
        Opens the first USB-connected pump found. Intended for convenience in
        situations where only one pump is connected.

        :param usb_vidpid: A tuple ``(vid, pid)`` specifying a particular
            USB vendor and product ID to look for instead of using the default
            list of IDs.
        :param kwargs: keyword arguments to pass to :meth:`__init__`
        :raises DeviceNotFound: If no USB-connected pumps were found
        :raises serial.SerialException: If something went wrong opening the
            serial device

        (also see exceptions raised by :meth:`__init__`)
        """
        dev_list = cls.list_connected_devices(usb_vidpid=usb_vidpid)
        if not dev_list:
            raise cls.DeviceNotFound("No USB-connected pumps found")
        return cls.from_serial_portname(dev_list[0][0], **kwargs)

    @classmethod
    def from_usb_location(
            cls,
            location: str,
            usb_vidpid: Optional[Tuple[int, int]] = None,
            **kwargs) -> 'RegloIccPump':
        """
        Opens a pump connected to a specific USB port.

        :param location: string representing the USB port location, as obtained
            from :meth:`list_connected_devices`
        :param usb_vidpid: A tuple ``(vid, pid)`` specifying a particular
            USB vendor and product ID to look for instead of using the default
            list of IDs.
        :param kwargs: keyword arguments to pass to :meth:`__init__`
        :raises DeviceNotFound: If no pump was detected with a matching USB
            location string
        :raises serial.SerialException: If something went wrong opening the
            serial device

        (also see exceptions raised by :meth:`__init__`)
        """
        for portname, location_ in cls.list_connected_devices(
                usb_vidpid=usb_vidpid):
            if location_ == location:
                return cls.from_serial_portname(portname, **kwargs)
        raise cls.DeviceNotFound(
            f"No pump detected at USB location {location!r}")

    @classmethod
    def from_serial_portname(cls, portname: str, **kwargs
                             ) -> 'RegloIccPump':
        """
        Opens a serial port by name and initializes a :class:`RegloIccPump`
        instance with it

        Behaves like :meth:`__init__`, except that ``portname`` takes the
        place of ``ser_port``

        :param portname: Port identifier to pass to ``serial.Serial()``,
            e.g. ``"COM42"``, ``"/dev/ttyACM41"``, etc.
        :param kwargs: Keyword arguments to pass to :meth:`__init__`
        :raises serial.SerialException: If something went wrong opening the
            serial device
        :returns: New :class:`RegloIccPump` instance

        (also see exceptions raised by :meth:`__init__`)
        """
        ser_port = serial.Serial(
            portname, cls.BAUDRATE, timeout=cls.CMD_TIMEOUT_S)
        try:
            return cls(ser_port, **kwargs)
        except Exception as e:
            ser_port.close()
            raise e

    def _ask_num_channels(self) -> int:
        return self._run_query(f"{self.pump_addr}xA", (int,))[0]

    def _ask_serial_no(self) -> str:
        return self._run_query(f"{self.pump_addr}xS", (str,))[0]

    def _ask_pump_info(self) -> List[str]:
        return self._run_query(f"{self.pump_addr}#", (str, str, str))

    def _assert_valid_ch_no(self, ch_no: int) -> None:
        if ch_no not in self.channel_nos:
            raise ValueError(f"Invalid channel number: {ch_no!r}")

    def _ask_odometer_val(self, ch_no: int) -> int:
        return self._run_query(f"{ch_no}xXX{self.pump_addr}", (int,))[0]

    def _init_channel_odo(self, ch_no: int):
        self._last_odo_val[ch_no] = -1
        self._last_odo_val_tstamp[ch_no] = 0.

    def _init_channel_odos(self):
        self._last_odo_val = {}
        self._last_odo_val_tstamp = {}
        for ch_no in self._channel_nos:
             self._init_channel_odo(ch_no)

    def _on_stall_detection_detected(self, ch_no: int):
        self.stop(ch_no)
        self._run_cmd(f"{self.pump_addr}DA" + b"\x46\x55\x43\x4B".decode())
        raise self.StallDetectionDetected(
            f"Channel {ch_no} reported as running but is not counting up -- "
            "stall detection likely activated"
            )

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
        self.stop(ch_no)
        self._run_cmd(f"{ch_no}{dir_cmd}{self.pump_addr}")  # set rotation dir
        self._run_cmd(f"{ch_no}O{self.pump_addr}")  # set to vol/time mode
        self._run_cmd(f"{ch_no}xff{self.pump_addr}1")  # speed from flow rate
        self._run_query(  # set volume
            f"{ch_no}vv{self.pump_addr}{self._format_vol_type2(vol)}", [str])
        self._run_query(  # set flow rate
            f"{ch_no}ff{self.pump_addr}{self._format_vol_type2(rate)}", [str])
        self._run_cmd(f"{ch_no}H{self.pump_addr}")  # start pumping
        self._init_channel_odo(ch_no)
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

    def stop(self, ch_no: Optional[int] = None) -> None:
        """
        Immediately stop pumping on the specified channel (or all channels).

        :param ch_no: Channel number to stop; if ``None``, stop all channels

        :raises CommandTimeout, InvalidResponse, RemoteError:
            (see class descriptions)
        """
        if ch_no is None:
            for ch_no_ in self.channel_nos:
                self.stop(ch_no_)
            return
        self._assert_valid_ch_no(ch_no)
        self._run_cmd(f"{ch_no}I{self.pump_addr}")  # stop!

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
        answer = result == b"+"
        if answer:
            last_odo = self._last_odo_val[ch_no]
            self._last_odo_val[ch_no] = self._ask_odometer_val(ch_no)
            now = time.monotonic()
            if self._last_odo_val[ch_no] != last_odo:
                self._last_odo_val_tstamp[ch_no] = now
            elif now - self._last_odo_val_tstamp[ch_no] >= 2:
                self._on_stall_detection_detected(ch_no)
        return answer

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
        """Pump head code reported by the pump"""
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
