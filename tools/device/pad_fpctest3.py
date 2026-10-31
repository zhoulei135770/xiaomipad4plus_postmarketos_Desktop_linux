import ctypes, fcntl, os, struct, time
GPIO_GET=0xC16CB403; GPIO_SET=0xC040B409
SPI_MODE=0x40016B01; SPI_BITS=0x40016B03; SPI_SPEED=0x40046B04
SPI_MSG2=0x40406B00

def g_out(chip, off, val):
    fd=os.open(chip,os.O_RDWR); r=bytearray(364)
    struct.pack_into("=I",r,0,off); struct.pack_into("=I",r,256,2)
    struct.pack_into("=B",r,260,val); r[324:325]=b"t"; struct.pack_into("=I",r,356,1)
    fcntl.ioctl(fd,GPIO_GET,r,True); l=struct.unpack_from("=i",r,360)[0]; os.close(fd); return l
def g_set(l,v):
    d=bytearray(64); struct.pack_into("=B",d,0,v); fcntl.ioctl(l,GPIO_SET,d,True)

avdd=g_out("/dev/gpiochip0",98,1); vddio=g_out("/dev/gpiochip0",92,1); rst=g_out("/dev/gpiochip0",108,0)
spi=os.open("/dev/spidev0.0",os.O_RDWR)
m=bytearray(1); fcntl.ioctl(spi,SPI_MODE,m,True)
b=bytearray(1); b[0]=8; fcntl.ioctl(spi,SPI_BITS,b,True)
s=bytearray(4); struct.pack_into("=I",s,0,1000000); fcntl.ioctl(spi,SPI_SPEED,s,True)

def read_reg(reg, n, cs_hold=True):
    t1=ctypes.create_string_buffer(bytes([reg]),1)
    r2=ctypes.create_string_buffer(n)
    cc = 0 if cs_hold else 1
    msg=struct.pack("=QQIIHBBI", ctypes.addressof(t1),0,1,1000000,0,8,cc,0)
    msg+=struct.pack("=QQIIHBBI", 0, ctypes.addressof(r2), n, 1000000,0,8,0,0)
    fcntl.ioctl(spi,SPI_MSG2,bytearray(msg),True)
    return bytes(r2.raw)

def power_and_read(label, rst_assert, rst_release, delay):
    g_set(avdd,1); g_set(vddio,1); time.sleep(delay)
    g_set(rst,rst_assert); time.sleep(0.002); g_set(rst,rst_release); time.sleep(delay)
    vals=[]
    for reg in (0x00,0xaf,0xfc):
        v=read_reg(reg,6)
        vals.append("0x%02x=%s" % (reg," ".join("%02x"%x for x in v)))
    print("%-28s %s" % (label, " | ".join(vals)))

print("--- 片选保持 (cs_change=0) ---")
power_and_read("rst low-active, 10ms", 0, 1, 0.010)
power_and_read("rst low-active, 60ms", 0, 1, 0.060)
power_and_read("rst high-active, 20ms", 1, 0, 0.020)
print("--- 片选释放 (cs_change=1，旧方式) ---")
g_set(rst,0); time.sleep(0.002); g_set(rst,1); time.sleep(0.02)
for reg in (0x00,0xaf):
    v=read_reg(reg,6,cs_hold=False)
    print("(cs toggled) 0x%02x=%s" % (reg," ".join("%02x"%x for x in v)))
g_set(avdd,0); g_set(vddio,0)