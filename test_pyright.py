import asyncio
from typing import Protocol, Awaitable, Any, cast

class Call:
    pass

class _InterceptedCallProtocol(Protocol):
    _interceptors_task: asyncio.Task[Call]

class _InterceptedUnaryResponseMixin:
    def __await__(self: _InterceptedCallProtocol):
        call = yield from self._interceptors_task.__await__()
        call_awaitable = cast(Awaitable[Any], call)
        response = yield from call_awaitable.__await__()
        return response
