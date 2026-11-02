# Restart Loop Scenario - Repeatedly exits and restarts
FROM alpine:3.19

RUN apk add --no-cache bash

RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser

COPY restart-loop.sh /app/restart-loop.sh
RUN chmod +x /app/restart-loop.sh && chown labuser:labuser /app/restart-loop.sh

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/restart-loop.sh"]
