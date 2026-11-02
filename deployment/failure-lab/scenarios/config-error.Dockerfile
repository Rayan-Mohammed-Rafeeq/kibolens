# Config Error Scenario - Invalid configuration
FROM alpine:3.19

RUN apk add --no-cache bash grep

RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser && \
    mkdir -p /app && \
    chown -R labuser:labuser /app

# Create invalid config file (missing required fields)
RUN echo '{"app": "test"}' > /app/config.json && \
    chown labuser:labuser /app/config.json

COPY config-error.sh /app/config-error.sh
RUN chmod +x /app/config-error.sh

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/config-error.sh"]
