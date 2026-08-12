"""Isolated Centrifugo connection-capacity probe; never targets staging."""
import asyncio, json, os, sys, time

def percentile(values,p):
    values=sorted(values); return values[min(len(values)-1,int((len(values)-1)*p))] if values else 0

async def main(count):
    if os.getenv("BEYVRA_LOAD_ISOLATED")!="1": raise SystemExit("ISOLATED_LOAD_TARGET_REQUIRED")
    import websockets
    url=os.getenv("CENTRIFUGO_TEST_URL","ws://centrifugo:8000/connection/websocket?format=json")
    if not url.startswith("ws://centrifugo:"): raise SystemExit("NON_ISOLATED_REALTIME_TARGET_REFUSED")
    latencies=[]; failures=0; gaps=0
    async def client(index):
        nonlocal failures,gaps
        started=time.monotonic()
        try:
            async with websockets.connect(url,open_timeout=5,close_timeout=1) as socket:
                await socket.send(json.dumps({"id":index+1,"connect":{}})); response=json.loads(await asyncio.wait_for(socket.recv(),5))
                if response.get("error"): raise RuntimeError("CONNECT_REJECTED")
                latencies.append((time.monotonic()-started)*1000); await asyncio.sleep(.2)
        except Exception: failures+=1
    started=time.monotonic(); await asyncio.gather(*(client(i) for i in range(count))); duration=time.monotonic()-started
    report={"clients_requested":count,"clients_connected":len(latencies),"failures":failures,"sequence_gaps":gaps,"duration_seconds":round(duration,3),"connection_latency_ms":{"p50":round(percentile(latencies,.5),3),"p95":round(percentile(latencies,.95),3),"p99":round(percentile(latencies,.99),3)}}
    print(json.dumps(report,sort_keys=True))
    if failures or gaps: raise SystemExit(1)

if __name__=="__main__": asyncio.run(main(int(sys.argv[1])))
