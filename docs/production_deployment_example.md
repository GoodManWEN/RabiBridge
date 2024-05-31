# Production deployment example

## Service Nodes:

- Use the configuration file instead of passing in parameters.
- Use multiprocessing assistance tools to take advantage of multiple cores CPU.

```python
from rabibridge import RMQServer, register_call, multiprocess_spawn_helper
import asyncio
import os
try:
    import uvloop
    uvloop.install()
except:
    ...

@register_call(queue_size=10000, fetch_size=128, timeout=10, validate=True)
async def add(a: int, b: int) -> str:
    return str(a + b)

async def process_async():
    s = RMQServer()
    s.load_services(globals())
    async with s:
        await s.run_serve()

def single_process():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    multiprocess_spawn_helper(os.cpu_count(), single_process, bind_core=True)
```

## Web Framework

### FastAPI
```python
from fastapi import FastAPI, HTTPException
from rabibridge import RMQClient
try:
    import uvloop
    uvloop.install()
except:
    ...

app = FastAPI()
bridge = RMQClient()

@app.on_event("startup")
async def startup():
    await bridge.connect()

@app.on_event("shutdown")
async def shutdown():
    await bridge.close()

@app.get("/")
async def home():
    return {}

@app.get("/add")
async def call_add(a: int, b: int):
    success, (err_code, res) = await bridge.try_call_async('add', (a, b), ftype="async", timeout=10)
    if success and err_code == 0:
        return res
    return HTTPException(status_code=500, detail="Error")
```

### aiohttp
```python
import asyncio
from aiohttp import web
from rabibridge import RMQClient

app = web.Application()
routes = web.RouteTableDef()

bridge = RMQClient()

@routes.get('/')
async def home(request):
    return web.Response(text='{}')

async def on_startup(app):
    global bridge
    await bridge.connect()

async def on_cleanup(app):
    global bridge
    await bridge.close()
    print("Closed the database connection")

@routes.get('/add')
async def call_add(request):
    try:
        a = int(request.query.get('a', None))
        b = int(request.query.get('b', None))
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid parameters")
    success, (err_code, res) = await bridge.try_call_async('add', (a, b), ftype="async", timeout=10)
    if success and err_code == 0:
        return web.Response(text=res)
    raise web.HTTPBadRequest(reason="Invalid parameters")
    

app.add_routes(routes)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
```