# Memory Pressure Scenario - Controlled memory consumption
FROM alpine:3.19

RUN apk add --no-cache bash stress-ng

RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser

COPY memory-pressure.sh /app/memory-pressure.sh
RUN chmod +x /app/memory-pressure.sh && chown labuser:labuser /app/memory-pressure.sh

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/memory-pressure.sh"]
