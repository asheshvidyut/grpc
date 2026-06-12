import math_pb2
from server import FastMathService

req = math_pb2.MathRequest()
req.matrix_a.extend([1.0, 2.0, 3.0])
req.matrix_b.extend([4.0, 5.0, 6.0])

req_bytes = req.SerializeToString()

service = FastMathService()
print("Calling native dispatch...")
res_bytes = service._native_Dispatch_ComputeMatrix(req_bytes)
print("Finished!")

res = math_pb2.MathResponse()
res.ParseFromString(res_bytes)
print(res.result_matrix)
