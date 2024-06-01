FROM rabbitmq:3.13-management

# copy rabbitmq.config to container
COPY rabbitmq.config /etc/rabbitmq/rabbitmq.config

# copy tls certificates and key to container
COPY rabbitmq-server-cert.pem /etc/rabbitmq/certs/rabbitmq-server-cert.pem
COPY rabbitmq-server-key.pem /etc/rabbitmq/certs/rabbitmq-server-key.pem
COPY ca-certificate.pem /etc/rabbitmq/certs/ca-certificate.pem

# expose ports for RabbitMQ server
EXPOSE 5671 5672 15672

# Start RabbitMQ server
CMD ["rabbitmq-server"]