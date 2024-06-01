# Step 1: Generate or obtain a CA certificate (ca_certificate.pem)
openssl genpkey -algorithm RSA -out ca-key.pem -pkeyopt rsa_keygen_bits:2048
openssl req -x509 -new -key ca-key.pem -days 3650 -out ca-certificate.pem -subj "/CN=MyCA"

# Step 2: Generate a RabbitMQ Server Private Key and Certificate Signing Request (CSR)
openssl genpkey -algorithm RSA -out rabbitmq-server-key.pem -pkeyopt rsa_keygen_bits:2048
openssl req -new -key rabbitmq-server-key.pem -out rabbitmq-server-csr.pem -subj "/CN=rabbitmq-server"

# Step 3: Sign the RabbitMQ Server Certificate with a CA Certificate
openssl x509 -req -in rabbitmq-server-csr.pem -CA ca-certificate.pem -CAkey ca-key.pem -CAcreateserial -out rabbitmq-server-cert.pem -days 3650

# Remove unnecessary files
rm ca-key.pem && rm rabbitmq-server-csr.pem


cat <<EOF > rabbitmq.config
[
 {rabbit, [
   {tcp_listeners, [{"0.0.0.0", 5672}]},
   {ssl_listeners, [{"0.0.0.0", 5671}]},
   {ssl_options, [{cacertfile, "/etc/rabbitmq/certs/ca-certificate.pem"},
                  {certfile,   "/etc/rabbitmq/certs/rabbitmq-server-cert.pem"},
                  {keyfile,    "/etc/rabbitmq/certs/rabbitmq-server-key.pem"},
                  {verify,     verify_peer},
                  {fail_if_no_peer_cert, true}]}
 ]}
].
EOF

docker build -t my-rabbitmq .

docker run -d --name my-rabbitmq -p 5672:5672 -p 5671:5671 -p 15672:15672 \
    -e RABBITMQ_DEFAULT_USER=admin \
    -e RABBITMQ_DEFAULT_PASS=123456 \
    my-rabbitmq