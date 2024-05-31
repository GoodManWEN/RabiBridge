from fastapi import FastAPI
from rabibridge import RMQClient
import asyncio
import uvloop
uvloop.install()

app = FastAPI()
bridge = RMQClient()

@app.on_event("startup")
async def startup():
    await bridge.connect()

@app.on_event("shutdown")
async def shutdown():
    await bridge.close()

@app.get("/raw")
async def raw():
    return 23

@app.get("/raw2")
async def raw():
    await asyncio.sleep(0.5)
    return 23

@app.get("/func1")
async def call_func1():
    success, res = await bridge.try_call_async('func1', timeout=10)
    return 21
