FROM alpine:3.20

COPY interview-demo.sh /usr/local/bin/interview-demo.sh
RUN chmod 0555 /usr/local/bin/interview-demo.sh

USER 1001:1001
ENTRYPOINT ["/usr/local/bin/interview-demo.sh"]
