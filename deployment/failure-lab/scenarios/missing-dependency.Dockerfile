# Missing Dependency Scenario - Required file unavailable
FROM alpine:3.19

RUN apk add --no-cache bash

RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser && \
    mkdir -p /app && \
    chown -R labuser:labuser /app

COPY missing-dependency.sh /app/missing-dependency.sh
RUN chmod +x /app/missing-dependency.sh

# Note: required-config.json is intentionally NOT included

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/missing-dependency.sh"]
