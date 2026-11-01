import paramiko, os, time

SRC = "/srv/debport/debian-rootfs.img"
DST = r"D:\debport\debian-rootfs-v12.img"
CHUNK = 32 * 1024 * 1024

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.1.25", 22, username="zhoulei", password="zhoulei135",
          timeout=20, look_for_keys=False, allow_agent=False)
s = c.open_sftp()
f = s.open(SRC, "rb")
size = s.stat(SRC).st_size
print("size", size, flush=True)
t = time.time()
done = 0
with open(DST, "wb") as out:
    while done < size:
        f.seek(done)
        b = f.read(min(CHUNK, size - done))
        if not b:
            print("short read at", done, flush=True)
            break
        out.write(b)
        done += len(b)
        if done % (512 * 1024 * 1024) < CHUNK:
            print("%.2f/%.2f GB" % (done / 1e9, size / 1e9), flush=True)
print("done %.0fs %.2fGB" % (time.time() - t, done / 1e9), flush=True)
f.close(); s.close(); c.close()

