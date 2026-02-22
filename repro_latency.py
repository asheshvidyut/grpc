import asyncio
import time
import grpc
from grpc.experimental import aio
import cProfile
import pstats
import io

# Simple Proto-less service
class GenericHandler(grpc.GenericRpcHandler):
    def service(self, handler_call_details):
        return grpc.unary_unary_rpc_method_handler(
            self.echo,
            request_deserializer=lambda x: x,
            response_serializer=lambda x: x
        )

    async def echo(self, request, context):
        return request

async def run_benchmark(iterations=1000):
    server = aio.server()
    server.add_generic_rpc_handlers((GenericHandler(),))
    port = server.add_insecure_port('localhost:0')
    await server.start()

    async with aio.insecure_channel(f'localhost:{port}') as channel:
        unary_call = channel.unary_unary('/test/echo', 
                                         request_serializer=lambda x: x, 
                                         response_deserializer=lambda x: x)
        
        # Warmup
        for _ in range(100):
            await unary_call(b'warmup')

        start = time.monotonic()
        for _ in range(iterations):
            await unary_call(b'payload')
        end = time.monotonic()
    
    await server.stop(None)
    
    avg_latency = (end - start) / iterations * 1000 * 1000 # microseconds
    print(f"Average Latency: {avg_latency:.2f} us")
    return avg_latency

def main():
    pr = cProfile.Profile()
    pr.enable()
    asyncio.run(run_benchmark())
    pr.disable()
    
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats(30)
    print(s.getvalue())

if __name__ == '__main__':
    main()
