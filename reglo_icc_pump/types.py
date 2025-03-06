from enum import Enum


class RegloIccPumpError(Exception):
    """Superclass of all RegloIccPump errors"""
    pass


class DeviceNotFound(RegloIccPumpError):
    """
    No USB-connected pumps detected, or none matching the specified criteria
    """
    pass


class SerialNoMismatch(RegloIccPumpError):
    """
    The serial number reported by the pump doesn't match what was expected
    """
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


class StallDetectionDetected(RegloIccPumpError):
    """
    The pump reports that the channel is still running but its time counter is
    no longer counting up. This likely means the half baked stall detection
    feature apparently introduced in firmware V204 has triggered.
    """


class InvalidParameter(RegloIccPumpError):
    """
    The pump reported (or the driver caught proactively) that a supplied
    parameter for a pump command is out of range or otherwise invalid
    """


class InvalidTubingId(InvalidParameter):
    """
    The specified tubing inner diameter is not one of the acceptable values
    """
    pass
    pass


class PumpDirection(Enum):
    """Pump rotor rotation direction, as viewed from the front"""

    #: Clockwise
    CW = "cw"

    #: Counter-clockwise
    CCW = "ccw"

    def opposite(self) -> 'PumpDirection':
        """Return the opposite direction"""
        return (
            PumpDirection.CW if self == PumpDirection.CCW
            else PumpDirection.CCW
            )
