#!/usr/bin/env python3
import asyncio, statistics, subprocess, sys, time, socket
import grpc

METHOD, EMPTY = "/bench.Bench/Call", b""

async def _handler(request, context):
    return EMPTY

async def serve(port):
    server = grpc.aio.server(options=[("grpc.so_reuseport", 0)])
    rpc = grpc.unary_unary_rpc_method_handler(
        _handler, request_deserializer=None, response_serializer=None)
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("bench.Bench", {"Call": rpc}),))
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    await server.wait_for_termination()

async def run_client(port, concurrency, trials, trial_seconds):
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    call = channel.unary_unary(METHOD, request_serializer=None,
                               response_deserializer=None, _registered_method=False)
    await asyncio.wait_for(channel.channel_ready(), timeout=10)
    await call(EMPTY)  # warm
    rates = []
    for t in range(trials):
        count = 0
        deadline = time.perf_counter() + trial_seconds
        async def worker():
            nonlocal count
            while time.perf_counter() < deadline:
                await call(EMPTY); count += 1
        start = time.perf_counter()
        await asyncio.gather(*[worker() for _ in range(concurrency)])
        dur = time.perf_counter() - start
        rate = count / dur
        rates.append(rate)
        print(f"  Trial {t+1}/{trials}: {count:,} requests in {dur:.2f}s -> {rate:,.1f} RPS")
    await channel.close()
    return statistics.mean(rates[1:])  # drop first trial (warmup)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        asyncio.run(serve(int(sys.argv[2])))
    else:
        port = free_port()
        srv = subprocess.Popen([sys.executable, sys.argv[0], "server", str(port)])
        try:
            time.sleep(2.5)
            print(f"\nStarting benchmark (concurrency=100, trials=20, trial_seconds=3)...")
            rps = asyncio.run(run_client(port, 100, 20, 3))
            print(f"\nRESULT rps={rps:.1f} grpcio={grpc.__version__}\n")
        finally:
            srv.terminate(); srv.wait(timeout=10)
