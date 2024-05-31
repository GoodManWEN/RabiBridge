import multiprocessing
import os

workers = 8

bind = "0.0.0.0:8080"
keepalive = 120
errorlog = '-'
pidfile = '/tmp/fastapi.pid'
loglevel = 'error'
