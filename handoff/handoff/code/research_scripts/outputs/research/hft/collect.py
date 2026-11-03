"""Collect Binance USDT-M futures L2 diff depth + trades (public websocket, no API key) in hftbacktest raw format.
Snapshot taken via the public ws-fapi 'depth' request (REST fapi is geo-blocked from this box)."""
import asyncio, websockets, json, gzip, time, sys
SYMS = ["btcusdt","ethusdt","solusdt"]
DUR = int(sys.argv[1]) if len(sys.argv)>1 else 3600
END = time.time()+DUR
stats = {s:{"lines":0,"reconn":0,"snap":0} for s in SYMS}

async def snapshot(sym):
    async with websockets.connect("wss://ws-fapi.binance.com/ws-fapi/v1", open_timeout=10) as ws:
        await ws.send(json.dumps({"id":1,"method":"depth","params":{"symbol":sym.upper(),"limit":1000}}))
        m = json.loads(await asyncio.wait_for(ws.recv(), 10))
        return m["result"], time.time_ns()

async def run(sym):
    f = gzip.open(f"raw/{sym}.gz", "ab")
    try:
        while time.time() < END:
            try:
                url = f"wss://fstream.binance.com/stream?streams={sym}@depth@0ms/{sym}@trade"
                async with websockets.connect(url, open_timeout=10, max_size=2**24, ping_interval=20) as ws:
                    buf = []
                    snap_task = asyncio.create_task(snapshot(sym))
                    snap = None
                    while time.time() < END:
                        raw = await asyncio.wait_for(ws.recv(), 30)
                        ts = time.time_ns()
                        if snap is None:
                            buf.append((ts, raw))
                            if snap_task.done():
                                res, sts = snap_task.result()
                                lu = res["lastUpdateId"]
                                f.write(f"{sts} ".encode()+json.dumps(res).encode()+b"\n")
                                stats[sym]["snap"] += 1
                                snap = True
                                for t, r in buf:
                                    d = json.loads(r)["data"]
                                    if d["e"]=="depthUpdate" and d["u"] < lu: continue
                                    f.write(f"{t} ".encode()+r.encode()+b"\n"); stats[sym]["lines"]+=1
                                buf = []
                        else:
                            f.write(f"{ts} ".encode()+raw.encode()+b"\n"); stats[sym]["lines"]+=1
            except Exception as e:
                stats[sym]["reconn"] += 1
                print(time.strftime("%H:%M:%S"), sym, "reconnect", repr(e)[:150], flush=True)
                await asyncio.sleep(1)
    finally:
        f.close()

async def reporter():
    while time.time() < END:
        await asyncio.sleep(60)
        print(time.strftime("%H:%M:%S"), json.dumps(stats), flush=True)

async def main():
    await asyncio.gather(reporter(), *[run(s) for s in SYMS])
asyncio.run(main())
print("DONE", json.dumps(stats), flush=True)
