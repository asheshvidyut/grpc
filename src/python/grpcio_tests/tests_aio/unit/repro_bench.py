#!/usr/bin/env python3
import asyncio, statistics, subprocess, sys, time, socket
import grpc

METHOD, EMPTY = "/bench.Bench/Call", b""

async def _handler(request, context):
    return EMPTY

async def serve(port):
    server = grpc.aio.server(options=[("grpc.so_reuseport", 1)])
    rpc = grpc.unary_unary_rpc_method_handler(
        _handler, request_deserializer=None, response_serializer=None)
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("bench.Bench", {"Call": rpc}),))
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    await server.wait_for_termination()

async def run_client(ports, concurrency, trials, trial_seconds):
    channels = [grpc.aio.insecure_channel(f"127.0.0.1:{p}") for p in ports]
    calls = [ch.unary_unary(METHOD, request_serializer=None, response_deserializer=None) for ch in channels]
    for ch in channels:
        await asyncio.wait_for(ch.channel_ready(), timeout=10)
    for c in calls:
        await c(EMPTY)  # warm
    rates = []
    num_channels = len(channels)
    for t in range(trials):
        count = 0
        deadline = time.perf_counter() + trial_seconds
        async def worker(w_id):
            nonlocal count
            call_fn = calls[w_id % num_channels]
            while time.perf_counter() < deadline:
                await call_fn(EMPTY); count += 1
        start = time.perf_counter()
        await asyncio.gather(*[worker(i) for i in range(concurrency)])
        dur = time.perf_counter() - start
        rate = count / dur
        rates.append(rate)
        print(f"  Trial {t+1}/{trials}: {count:,} requests in {dur:.2f}s -> {rate:,.1f} RPS")
    for ch in channels:
        await ch.close()
    return statistics.mean(rates[1:])  # drop first trial (warmup)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        asyncio.run(serve(int(sys.argv[2])))
    else:
        num_servers = 4
        ports = [free_port() for _ in range(num_servers)]
        servers = [
            subprocess.Popen([sys.executable, sys.argv[0], "server", str(p)])
            for p in ports
        ]
        try:
            time.sleep(2.5)
            print(f"\nStarting benchmark (concurrency=100, trials=10, trial_seconds=3, num_servers={num_servers})...")
            rps = asyncio.run(run_client(ports, 100, 10, 3))
            print(f"\nRESULT rps={rps:.1f} grpcio={grpc.__version__}\n")
        finally:
            for srv in servers:
                srv.terminate()
                srv.wait(timeout=5)
