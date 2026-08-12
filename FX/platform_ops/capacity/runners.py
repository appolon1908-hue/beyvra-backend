import statistics,time
def run_fixture(fn,count):
    durations=[];errors=0
    for _ in range(count):
        started=time.perf_counter()
        try:fn()
        except Exception:errors+=1
        durations.append((time.perf_counter()-started)*1000)
    ordered=sorted(durations)
    percentile=lambda p:ordered[min(len(ordered)-1,int(len(ordered)*p))]
    return {"count":count,"errors":errors,"error_rate":errors/count,"p50_ms":statistics.median(ordered),"p95_ms":percentile(.95),"p99_ms":percentile(.99)}
