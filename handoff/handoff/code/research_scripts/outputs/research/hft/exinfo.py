import asyncio, websockets, json
async def main():
    async with websockets.connect("wss://ws-fapi.binance.com/ws-fapi/v1", open_timeout=10, max_size=2**26) as ws:
        await ws.send(json.dumps({"id":1,"method":"exchangeInfo","params":{}}))
        m = json.loads(await asyncio.wait_for(ws.recv(), 20))
        out={}
        for s in m["result"]["symbols"]:
            if s["symbol"] in ("BTCUSDT","ETHUSDT","SOLUSDT"):
                f={x["filterType"]:x for x in s["filters"]}
                out[s["symbol"]]={"tick":f["PRICE_FILTER"]["tickSize"],"lot":f["LOT_SIZE"]["stepSize"],"minQty":f["LOT_SIZE"]["minQty"],"minNotional":f.get("MIN_NOTIONAL",{}).get("notional")}
        print(json.dumps(out)); json.dump(out,open("exinfo.json","w"))
asyncio.run(main())
