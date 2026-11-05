import struct
def node(path):
    n=root
    for part in path.strip('/').split('/'):
        for c in n.get('children',[]):
            if str(c.get('name'))==part: n=c; break
        else: return None
    return n
aio=node('arm-io')
r=B(aio['ranges']); rng=[struct.unpack_from('<QQQ',r,i) for i in range(0,len(r),24)]
print('arm-io ranges',[(hex(a),hex(b),hex(c)) for a,b,c in rng])
def xl(a):
    for ch,pa,sz in rng:
        if ch<=a<ch+sz: return a-ch+pa
    return a
for p in ['arm-io/pmgr','arm-io/aic','arm-io/smc','arm-io/pmp','arm-io/nub-spmi','arm-io/nub-spmi1','arm-io/wdt','arm-io/aop','arm-io/uart0','arm-io/nub-spmi/spmi-pmu','arm-io/dart-pmp','arm-io/aes']:
    n=node(p)
    if n is None: print(p,'MISSING'); continue
    reg=B(n.get('reg',b''))
    regs=[struct.unpack_from('<QQ',reg,i) for i in range(0,len(reg)//16*16,16)]
    print(p, [(hex(xl(a)),hex(s)) for a,s in regs] if p.count('/')<2 else reg.hex(), {k:(B(n[k])[:16].hex()) for k in n if k in ('gen','interrupts','compatible','wdt-version','role')})
pm=node('arm-io/pmgr'); print([k for k in pm if k!='children'])
