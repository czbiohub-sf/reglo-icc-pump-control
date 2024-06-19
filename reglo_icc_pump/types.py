from enum import Enum


class RegloIccPumpError(Exception):
    """Superclass of all RegloIccPump errors"""
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
    """The pump reported that the specified tubing inner diameter is invalid"""
    pass


class PumpDirection(Enum):
    """Pump rotor rotation direction, as viewed from the front"""

    #: Clockwise
    CW = "cw"

    #: Counter-clockwise
    CCW = "ccw"

    def opposite(self) -> 'PumpDirection':
        """Return the opposite direction"""
        return self.CW if type(self)(self) == self.CCW else self.CCW
