``reglo_icc_pump`` module
=========================

Driver class
------------
.. autoclass:: reglo_icc_pump.RegloIccPump
   :members: __init__, from_serial_portname, set_tubing_id, pump_vol, aspirate_vol, dispense_vol, is_running, wait_for_stop, show_msg, channel_nos, model_no, serial_no, sw_ver, head_code
   :member-order: bysource

Enums
-----
.. autoclass:: reglo_icc_pump.RegloIccPump.PumpDirection
   :members:
   :undoc-members:

Exceptions
----------
.. autoclass:: reglo_icc_pump.RegloIccPump.RegloIccPumpError
.. autoclass:: reglo_icc_pump.RegloIccPump.CommandTimeout
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidResponse
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.RemoteError
   :show-inheritance: True
.. autoclass:: reglo_icc_pump.RegloIccPump.InvalidTubingId
   :show-inheritance: True

Usage example
=============
.. literalinclude:: usage_example.py
   :language: python

