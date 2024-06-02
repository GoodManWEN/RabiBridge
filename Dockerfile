FROM python:3.12-slim

WORKDIR /app

COPY ./rabibridge /app
COPY ./config /app
COPY ./plugins /app
COPY ./misc/main.py /app

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir uvloop

# EXPOSE 8080

# ENV SERVICE_PORT 8080

CMD python main.py
# CMD python test.py