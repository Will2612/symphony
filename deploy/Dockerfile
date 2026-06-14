# syntax=docker/dockerfile:1.7
ARG SWIFT_VERSION=6.3.2

FROM --platform=$TARGETPLATFORM swift:${SWIFT_VERSION}-noble AS builder
WORKDIR /build
COPY Package.swift ./
COPY Sources ./Sources
RUN --mount=type=cache,target=/root/.cache/swift \
    --mount=type=cache,target=/build/.build \
    swift build -c release --static-swift-stdlib && \
    cp /build/.build/release/symphony /symphony

FROM swift:${SWIFT_VERSION}-noble-slim AS runtime
RUN useradd -m -u 10001 symphony
WORKDIR /app
COPY --from=builder /symphony /usr/local/bin/symphony
USER symphony
ENTRYPOINT ["symphony"]
