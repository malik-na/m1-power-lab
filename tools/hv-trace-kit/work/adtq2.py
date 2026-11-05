import struct
aio=[c for c in root['children'] if str(c.get('name'))=='arm-io'][0]
r=B(aio['ranges']); rng=[struct.unpack_from('<QQQ',r,i) for i in range(0,len(r),24)]
def xl(a):
    for ch,pa,sz in rng:
        if ch<=a<ch+sz: return a-ch+pa
    return a
for c in aio['children']:
    nm=str(c.get('name'))
    if any(s in nm.lower() for s in ('aic','smc','pmp','wdt','aop','aes','spmi','sio','mca','amcc','mcc','dcs','atc')) :
        reg=B(c.get('reg',b''))
        regs=[struct.unpack_from('<QQ',reg,i) for i in range(0,len(reg)//16*16,16)]
        print(nm, [(hex(xl(a)),hex(s)) for a,s in regs][:8], B(c.get('compatible',b''))[:40])
