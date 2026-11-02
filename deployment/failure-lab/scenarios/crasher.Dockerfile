# Crasher Scenario - Exits with configurable non-zero exit code
FROM alpine:3.19

# Install minimal dependencies
RUN apk add --no-cache bash

# Create non-root user
RUN addgroup -g 1001 labuser && \
    adduser -D -u 1001 -G labuser labuser

# Copy crash script
COPY crasher.sh /app/crasher.sh
RUN chmod +x /app/crasher.sh && chown labuser:labuser /app/crasher.sh

USER labuser
WORKDIR /app

ENTRYPOINT ["/app/crasher.sh"]
