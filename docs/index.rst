``reglo_icc_pump`` module
=========================

Driver class
------------
.. autoclass:: reglo_icc_pump.RegloIccPump
   :members: __init__, from_serial_portname, list_connected_devices, open_first_device, from_usb_location, set_tubing_id, pump_vol, aspirate_vol, dispense_vol, is_running, wait_for_stop, show_msg, channel_nos, model_no, serial_no, sw_ver, head_code
   :member-order: bysource

Enums
-----
.. autoclass:: reglo_icc_pump.RegloIccPump.PumpDirection
   :members:

Exceptions
----------
.. autoclass:: reglo_icc_pump.RegloIccPump.RegloIccPumpError
.. autoclass:: reglo_icc_pump.RegloIccPump.DeviceNotFound
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.SerialNoMismatch
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.CommandTimeout
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidResponse
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.RemoteError
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidTubingId
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidFlowRate
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidVolume
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.StallDetectionDetected
   :show-inheritance: True

Usage example
=============
.. literalinclude:: usage_example.py
   :language: python
