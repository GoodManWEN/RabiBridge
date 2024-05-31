docker run -d \
  --name rabbitmq \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=123456 \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:management