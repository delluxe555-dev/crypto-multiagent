import asyncio, websockets, json
async def main():
    for url in ["wss://fstream.binance.com/stream?streams=btcusdt@depth@0ms/btcusdt@trade","wss://fstream.binance.com/ws/btcusdt@depth@100ms"]:
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                m = await asyncio.wait_for(ws.recv(), 10); print(url, "OK", m[:200])
        except Exception as e: print(url, "ERR", repr(e)[:200])
asyncio.run(main())
