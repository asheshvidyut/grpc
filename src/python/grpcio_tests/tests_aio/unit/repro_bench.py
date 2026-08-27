#!/usr/bin/env python3
import asyncio, statistics, subprocess, sys, time, socket
import grpc

UNARY_METHOD = "/bench.Bench/UnaryCall"
STREAM_METHOD = "/bench.Bench/StreamCall"
EMPTY = b""

async def _unary_handler(request, context):
    return EMPTY

async def _stream_handler(request_iterator, context):
    async for req in request_iterator:
        yield req

async def serve(port):
    server = grpc.aio.server(options=[("grpc.so_reuseport", 1)])
    unary_rpc = grpc.unary_unary_rpc_method_handler(
        _unary_handler, request_deserializer=None, response_serializer=None)
    stream_rpc = grpc.stream_stream_rpc_method_handler(
        _stream_handler, request_deserializer=None, response_serializer=None)
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("bench.Bench", {
            "UnaryCall": unary_rpc,
            "StreamCall": stream_rpc,
        }),))
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    await server.wait_for_termination()

async def run_streaming_benchmark(ports, concurrency=20, num_messages=2000):
    channels = [grpc.aio.insecure_channel(f"127.0.0.1:{p}") for p in ports]
    for ch in channels:
        await asyncio.wait_for(ch.channel_ready(), timeout=10)
    
    num_channels = len(channels)
    
    async def stream_worker(w_id):
        ch = channels[w_id % num_channels]
        call = ch.stream_stream(STREAM_METHOD, request_serializer=None, response_deserializer=None)
        
        async def sender():
            for _ in range(num_messages):
                await call.write(EMPTY)
            await call.done_writing()
            
        async def receiver():
            received = 0
            async for _ in call:
                received += 1
            return received
            
        _, received = await asyncio.gather(sender(), receiver())
        return received

    # Warmup
    await stream_worker(0)

    start = time.perf_counter()
    results = await asyncio.gather(*[stream_worker(i) for i in range(concurrency)])
    elapsed = time.perf_counter() - start

    total_msgs = sum(results)
    rate = total_msgs / elapsed
    for ch in channels:
        await ch.close()
    return rate, total_msgs, elapsed

async def run_client(ports, concurrency, trials, trial_seconds):
    channels = [grpc.aio.insecure_channel(f"127.0.0.1:{p}") for p in ports]
    calls = [ch.unary_unary(UNARY_METHOD, request_serializer=None, response_deserializer=None) for ch in channels]
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
            print(f"\n================ 1. Streaming Throughput Benchmark ================")
            print(f"Running streaming benchmark (concurrency=20 streams, 2000 msgs/stream)...")
            stream_rate, total_msgs, s_time = asyncio.run(run_streaming_benchmark(ports, concurrency=20, num_messages=2000))
            print(f"RESULT Streaming: {total_msgs:,} msgs in {s_time:.2f}s -> {stream_rate:,.1f} msg/s")

            print(f"\n================ 2. Unary RPS Benchmark ================")
            print(f"Running unary benchmark (concurrency=100, trials=5, trial_seconds=3)...")
            rps = asyncio.run(run_client(ports, 100, 5, 3))
            print(f"RESULT Unary rps={rps:.1f} grpcio={grpc.__version__}\n")
        finally:
            for srv in servers:
                srv.terminate()
                srv.wait(timeout=5)
