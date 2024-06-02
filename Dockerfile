FROM python:3.12-slim

WORKDIR /app

COPY ./ /app/

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir uvloop

CMD python main.py