"""Minimal read-only Parquet reader for flat optional-string columns (Snappy/uncompressed, dict+plain).
Used only for inspection in a sandbox without pyarrow."""
import struct, io
def snappy_decompress(b):
    pos=0
    n=0;s=0
    while True:
        c=b[pos];pos+=1;n|=(c&0x7f)<<s
        if not c&0x80:break
        s+=7
    out=bytearray()
    while pos<len(b):
        t=b[pos];pos+=1
        k=t&3
        if k==0:
            l=t>>2
            if l<60:l+=1
            else:
                nb=l-59;l=int.from_bytes(b[pos:pos+nb],'little')+1;pos+=nb
            out+=b[pos:pos+l];pos+=l
        else:
            if k==1:
                l=((t>>2)&7)+4;o=((t>>5)<<8)|b[pos];pos+=1
            elif k==2:
                l=(t>>2)+1;o=int.from_bytes(b[pos:pos+2],'little');pos+=2
            else:
                l=(t>>2)+1;o=int.from_bytes(b[pos:pos+4],'little');pos+=4
            for _ in range(l):out.append(out[-o])
    assert len(out)==n,(len(out),n)
    return bytes(out)
class TR:
    def __init__(s,buf,pos=0):s.buf=buf;s.pos=pos
    def varint(s):
        r=0;sh=0
        while True:
            b=s.buf[s.pos];s.pos+=1;r|=(b&0x7f)<<sh
            if not b&0x80:return r
            sh+=7
    def zz(s,n):return (n>>1)^-(n&1)
    def val(s,t):
        if t in(1,2):return t==1
        if t==3:
            v=s.buf[s.pos];s.pos+=1;return v
        if t in(4,5,6):return s.zz(s.varint())
        if t==7:
            v=struct.unpack('<d',s.buf[s.pos:s.pos+8])[0];s.pos+=8;return v
        if t==8:
            n=s.varint();v=bytes(s.buf[s.pos:s.pos+n]);s.pos+=n;return v
        if t in(9,10):
            h=s.buf[s.pos];s.pos+=1;n=h>>4;et=h&15
            if n==15:n=s.varint()
            out=[]
            for _ in range(n):
                if et in(1,2):
                    out.append(s.buf[s.pos]==1);s.pos+=1
                else:out.append(s.val(et))
            return out
        if t==12:return s.struct()
        raise Exception('t%d'%t)
    def struct(s):
        d={};last=0
        while True:
            h=s.buf[s.pos];s.pos+=1
            if h==0:break
            dl=h>>4;t=h&15
            fid=last+dl if dl else s.zz(s.varint());last=fid
            d[fid]=(t==1) if t in(1,2) else s.val(t)
        return d
def rle_hybrid(buf,pos,bw,count):
    out=[]
    while len(out)<count:
        r=0;sh=0
        while True:
            b=buf[pos];pos+=1;r|=(b&0x7f)<<sh
            if not b&0x80:break
            sh+=7
        if r&1:
            groups=r>>1;nbytes=groups*bw
            chunk=buf[pos:pos+nbytes];pos+=nbytes
            bits=int.from_bytes(chunk,'little')
            for i in range(groups*8):
                out.append((bits>>(i*bw))&((1<<bw)-1))
        else:
            run=r>>1;nb=(bw+7)//8
            v=int.from_bytes(buf[pos:pos+nb],'little') if nb else 0;pos+=nb
            out+=[v]*run
    return out[:count],pos
def read_parquet_strings(path):
    f=open(path,'rb').read()
    flen=struct.unpack('<I',f[-8:-4])[0]
    md=TR(f[-8-flen:-8]).struct()
    names=[s[4].decode() for s in md[2][1:]]
    cols={n:[] for n in names}
    for rg in md[4]:
        for name,cc in zip(names,rg[1]):
            m=cc[3];codec=m[4]
            pos=m.get(11) or m[9]
            if 11 in m and m[11]:pos=min(m[11],m[9])
            dict_vals=None;vals=[]
            end=pos+m[7]
            while pos<end:
                tr=TR(f,pos);ph=tr.struct();pos=tr.pos
                csz=ph[3];raw=f[pos:pos+csz];pos+=csz
                ptype=ph[1]
                if ptype==3:  # v2 data page
                    dp=ph[8]
                    rl=dp[5];dl=dp[6]
                    hdr=raw[:rl+dl];body=raw[rl+dl:]
                    if dp.get(7,True) and codec==1:body=snappy_decompress(body)
                    nvals=dp[1];data=hdr+body
                    defs,p=rle_hybrid(data,0,1,nvals) if dl==0 else (None,None)
                    if dl:
                        defs,_=rle_hybrid(data[rl:rl+dl],0,1,nvals)
                    p=rl+dl
                    page=data
                else:
                    page=snappy_decompress(raw) if codec==1 else raw
                    if ptype==2:
                        dph=ph[7];n=dph[1];p=0;dict_vals=[]
                        for _ in range(n):
                            l=struct.unpack('<I',page[p:p+4])[0];p+=4
                            dict_vals.append(page[p:p+l].decode('utf-8','replace'));p+=l
                        continue
                    dp=ph[5];nvals=dp[1]
                    l=struct.unpack('<I',page[0:4])[0]
                    defs,_=rle_hybrid(page[4:4+l],0,1,nvals);p=4+l
                nn=sum(defs)
                enc=dp[2]
                if enc in(2,8):
                    bw=page[p];p+=1
                    idx,_=rle_hybrid(page,p,bw,nn)
                    vs=[dict_vals[i] for i in idx]
                else:
                    vs=[]
                    for _ in range(nn):
                        l=struct.unpack('<I',page[p:p+4])[0];p+=4
                        vs.append(page[p:p+l].decode('utf-8','replace'));p+=l
                it=iter(vs)
                vals+=[next(it) if d else None for d in defs]
            cols[name]+=vals
    return cols
if __name__=='__main__':
    import sys
    c=read_parquet_strings(sys.argv[1])
    n=len(next(iter(c.values())))
    print('rows',n)
    for k,v in c.items():
        nn=sum(1 for x in v if x not in(None,''))
        print(f'{k:20s} non-empty={nn:4d} distinct={len(set(v)):4d} sample={str(v[0])[:90]!r}')
