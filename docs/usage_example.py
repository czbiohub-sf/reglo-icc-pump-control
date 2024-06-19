import time

from reglo_icc_pump import RegloIccPump


print("Pumps are connected on these ports:")
for portname in RegloIccPump.list_connected_devices():
    print(f"  {portname!r}")

print("\nSerial number check:")
try:
    foo = RegloIccPump.from_serial_portname(
        "/dev/ttyACM0",
        serial_no="WRONG1234"
        )
    print("  Okay!")
except RegloIccPump.SerialNoMismatch as e:
    print(f"  {e!r}")
    time.sleep(0.2)

print()
p = RegloIccPump.open_first_device(
    dispense_dirs={1: "ccw", 3: "ccw"},
    tubing_ids={n: 1.52 for n in [1, 2, 3, 4]},
    )
print(f"Port name:        {p.ser_port.port!r}")
print(f"Serial number:    {p.serial_no!r}")
print(f"Firmware version: {p.sw_ver!r}")
print(f"Pump head:        {p.head_code!r}")
print(f"Channel numbers:  {p.channel_nos!r}")

p.show_msg("Concurrent")
print("\nConcurrent pumping operations...")
for ch_no in p.channel_nos:
    p.aspirate_vol(ch_no, 5.0e-3, 0.5, blocking=False)
p.wait_for_stop()

p.show_msg("Sequential")
print("\nSequential pumping operations...")
for ch_no in p.channel_nos:
    p.dispense_vol(ch_no, 42e-3, 10.0)
p.show_msg("Done")
