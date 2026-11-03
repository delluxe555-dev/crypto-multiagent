import asyncio, websockets, json
async def main():
    async with websockets.connect("wss://ws-fapi.binance.com/ws-fapi/v1", open_timeout=10) as ws:
        await ws.send(json.dumps({"id":1,"method":"depth","params":{"symbol":"BTCUSDT","limit":1000}}))
        m = await asyncio.wait_for(ws.recv(), 10); print(m[:300])
asyncio.run(main())
