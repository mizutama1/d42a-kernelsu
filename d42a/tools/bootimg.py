#!/usr/bin/env python3
"""Minimal Android boot image (header v0/v1/v2) unpack/repack tool.

Usage:
  python bootimg.py unpack boot.img outdir
  python bootimg.py repack outdir boot_new.img [--kernel FILE] [--ramdisk FILE] [--dtb FILE]
"""
import struct, sys, os, argparse

BOOT_MAGIC = b"ANDROID!"

def pages(n, page):
    return (n + page - 1) // page * page

def unpack(img_path, outdir):
    d = open(img_path, "rb").read()
    assert d[:8] == BOOT_MAGIC, "not an Android boot image"
    (k_sz, k_addr, r_sz, r_addr, s_sz, s_addr, tags,
     page, hv, osv) = struct.unpack("<10I", d[8:48])
    name = d[48:64].rstrip(b"\0")
    cmdline = d[64:576].split(b"\0")[0]
    idb = d[576:608]
    extra = d[608:1632]

    rdtbo_sz = rdtbo_off = hsz = dtb_sz = 0
    dtb_addr = 0
    if hv >= 1:
        rdtbo_sz = struct.unpack("<I", d[1632:1636])[0]
        rdtbo_off = struct.unpack("<Q", d[1636:1644])[0]
        hsz = struct.unpack("<I", d[1644:1648])[0]
    if hv >= 2:
        dtb_sz = struct.unpack("<I", d[1648:1652])[0]
        dtb_addr = struct.unpack("<Q", d[1652:1660])[0]

    os.makedirs(outdir, exist_ok=True)
    off = page
    parts = {}
    for key, size in (("kernel", k_sz), ("ramdisk", r_sz), ("second", s_sz)):
        if size:
            parts[key] = d[off:off + size]
            open(os.path.join(outdir, key), "wb").write(parts[key])
        off += pages(size, page)
    if dtb_sz:
        # dtb is located by dtb_addr for v2 images produced by mkbootimg;
        # in practice it follows the last section.
        parts["dtb"] = d[off:off + dtb_sz]
        open(os.path.join(outdir, "dtb"), "wb").write(parts["dtb"])
        off += pages(dtb_sz, page)
    if rdtbo_sz and rdtbo_off:
        parts["recovery_dtbo"] = d[rdtbo_off:rdtbo_off + rdtbo_sz]
        open(os.path.join(outdir, "recovery_dtbo"), "wb").write(parts["recovery_dtbo"])

    meta = dict(k_sz=k_sz, k_addr=k_addr, r_sz=r_sz, r_addr=r_addr, s_sz=s_sz,
                s_addr=s_addr, tags=tags, page=page, hv=hv, osv=osv,
                name=name, cmdline=cmdline, id=idb, extra=extra,
                rdtbo_sz=rdtbo_sz, rdtbo_off=rdtbo_off, hsz=hsz,
                dtb_sz=dtb_sz, dtb_addr=dtb_addr)
    with open(os.path.join(outdir, "meta.txt"), "w") as f:
        for k, v in meta.items():
            f.write(f"{k}={v if not isinstance(v, bytes) else v.hex()}\n")
    print("unpacked:", {k: len(v) for k, v in parts.items()}, "header v", hv, "page", page)
    return meta

def load_meta(outdir):
    meta = {}
    for line in open(os.path.join(outdir, "meta.txt")):
        k, _, v = line.strip().partition("=")
        meta[k] = v
    for k in ("k_sz","k_addr","r_sz","r_addr","s_sz","s_addr","tags","page","hv","osv",
              "rdtbo_sz","rdtbo_off","hsz","dtb_sz","dtb_addr"):
        meta[k] = int(meta[k], 0)
    for k in ("name","cmdline","id","extra"):
        meta[k] = bytes.fromhex(meta[k])
    return meta

def repack(outdir, out_path, kernel=None, ramdisk=None, dtb=None, cmdline=None):
    m = load_meta(outdir)
    rd = lambda n: open(os.path.join(outdir, n), "rb").read()
    k = open(kernel, "rb").read() if kernel else rd("kernel")
    r = open(ramdisk, "rb").read() if ramdisk else rd("ramdisk")
    s = rd("second") if os.path.exists(os.path.join(outdir, "second")) else b""
    dt = open(dtb, "rb").read() if dtb else (rd("dtb") if os.path.exists(os.path.join(outdir, "dtb")) else b"")
    page = m["page"]
    hv = m["hv"]
    hdr = bytearray(1660 if hv >= 2 else (1648 if hv >= 1 else 1632))
    hdr[0:8] = BOOT_MAGIC
    struct.pack_into("<10I", hdr, 8, len(k), m["k_addr"], len(r), m["r_addr"],
                     len(s), m["s_addr"], m["tags"], page, hv, m["osv"])
    nm = m["name"][:16].ljust(16, b"\0")
    hdr[48:64] = nm
    cl = (cmdline.encode() if isinstance(cmdline, str) else cmdline) if cmdline is not None else m["cmdline"]
    hdr[64:576] = cl[:511].ljust(512, b"\0")
    hdr[576:608] = m["id"]
    hdr[608:1632] = m["extra"]
    if hv >= 1:
        struct.pack_into("<I", hdr, 1632, m["rdtbo_sz"])
        struct.pack_into("<Q", hdr, 1636, m["rdtbo_off"])
        struct.pack_into("<I", hdr, 1644, len(hdr))
    if hv >= 2:
        struct.pack_into("<I", hdr, 1648, len(dt))
        struct.pack_into("<Q", hdr, 1652, m["dtb_addr"])

    out = bytearray()
    out += hdr.ljust(page, b"\0")
    out += k.ljust(pages(len(k), page), b"\0")
    out += r.ljust(pages(len(r), page), b"\0")
    if s:
        out += s.ljust(pages(len(s), page), b"\0")
    if dt:
        out += dt.ljust(pages(len(dt), page), b"\0")
    open(out_path, "wb").write(bytes(out))
    print(f"repacked {out_path}: {len(out)} bytes (kernel={len(k)}, ramdisk={len(r)}, dtb={len(dt)})")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unpack"); u.add_argument("img"); u.add_argument("outdir")
    rp = sub.add_parser("repack")
    rp.add_argument("outdir"); rp.add_argument("out")
    rp.add_argument("--kernel"); rp.add_argument("--ramdisk"); rp.add_argument("--dtb")
    rp.add_argument("--cmdline")
    a = ap.parse_args()
    if a.cmd == "unpack":
        unpack(a.img, a.outdir)
    else:
        repack(a.outdir, a.out, a.kernel, a.ramdisk, a.dtb, a.cmdline)

if __name__ == "__main__":
    main()
