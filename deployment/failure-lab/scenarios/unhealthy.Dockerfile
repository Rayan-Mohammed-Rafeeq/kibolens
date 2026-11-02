# Unhealthy Scenario - Runs but health check fails
FROM alpine:3.19

RUN apk add --no-cache bash

# Create non-root user
RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser && \
    mkdir -p /tmp && \
    chown labuser:labuser /tmp

COPY unhealthy.sh /app/unhealthy.sh
RUN chmod +x /app/unhealthy.sh && chown labuser:labuser /app/unhealthy.sh

USER labuser
WORKDIR /app

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD test -f /tmp/healthy || exit 1

ENTRYPOINT ["/app/unhealthy.sh"]
