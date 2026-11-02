# CPU Stress Scenario - Controlled CPU load
FROM alpine:3.19

RUN apk add --no-cache bash stress-ng

RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser

COPY cpu-stress.sh /app/cpu-stress.sh
RUN chmod +x /app/cpu-stress.sh && chown labuser:labuser /app/cpu-stress.sh

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/cpu-stress.sh"]
