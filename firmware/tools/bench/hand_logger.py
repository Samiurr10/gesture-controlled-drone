"""Keep the LEFT hand's USB console open (opening it resets the board, so only once) and
log `link` and `stats` every 2 s plus every unsolicited line, to catch a packet stall."""
import serial, sys, time
s = serial.Serial(); s.port = sys.argv[1]; s.baudrate = 115200; s.timeout = 0.2; s.dtr = s.rts = False; s.open()
out = open(sys.argv[2], "a", buffering=1); due = 0
while True:
    if time.time() >= due:
        s.write(b"link\nstats\n"); due = time.time() + 2
    for line in s.read(8192).decode(errors="replace").splitlines():
        if line.strip():
            out.write(f"{time.strftime('%H:%M:%S')} {line}\n")
