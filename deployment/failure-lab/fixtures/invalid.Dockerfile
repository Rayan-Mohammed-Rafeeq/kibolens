# Invalid Dockerfile for testing build failure detection
# This file intentionally contains syntax errors

FROM alpine:3.19

# Invalid instruction - doesn't exist
INVALIDCOMMAND echo "This should fail"

# Malformed RUN
RUN

# Missing argument
COPY

# Invalid user format
USER not:valid:format:here

CMD ["echo", "This Dockerfile is intentionally broken"]
