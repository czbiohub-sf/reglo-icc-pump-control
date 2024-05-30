from reglo_icc_pump import RegloIccPump


p = RegloIccPump.from_serial_portname(
    "COM1",
    dispense_dirs={1: "ccw", 3: "ccw"},
    tubing_ids={n: 1.52 for n in [1, 2, 3, 4]},
    )
print(repr(p.model_no))
print(repr(p.serial_no))
print(repr(p.sw_ver))
print(repr(p.head_code))
print(repr(p.channel_nos))
print(p.tubing_ids)

p.show_msg("Concurrent")
print("Concurrent pumping operations")
for ch_no in p.channel_nos:
    p.aspirate_vol(ch_no, 2.5e-3, 0.5, blocking=False)
p.wait_for_stop()

p.show_msg("Sequential")
print("Sequential pumping operations")
for ch_no in p.channel_nos:
    p.dispense_vol(ch_no, 42e-3, 10.0)
p.show_msg("Done")
