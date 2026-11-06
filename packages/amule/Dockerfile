# syntax=docker/dockerfile:1

# Bumped by hand with its checksum below, until Debian ships 3.2.12 (BACKLOG.md, Postponed).
ARG WX_VERSION=3.2.12

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS wx

ARG WX_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         g++ make pkgconf bzip2 libcurl4-openssl-dev libpcre2-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# The tarball's sha256, taken once its SHA-1 matched the one the release notes publish.
ADD --checksum=sha256:a62719bb5e1dcc41c1a6fc1eecd499c7ee8521f70402c7b1bb3342a1e16344e0 \
    https://github.com/wxWidgets/wxWidgets/releases/download/v${WX_VERSION}/wxWidgets-${WX_VERSION}.tar.bz2 \
    /src/wx.tar.bz2

# aMule's cmake/wx.cmake stops unless wxWebRequest has its libcurl backend; no XML, so no expat.
RUN tar -xjf /src/wx.tar.bz2 -C /src \
    && cd /src/wxWidgets-${WX_VERSION} \
    && ./configure --prefix=/usr/local --disable-gui --with-libcurl \
         --with-regex=sys --with-zlib=sys --without-expat \
    && make -j"$(nproc)" \
    && make install DESTDIR=/out \
    && strip --strip-unneeded /out/usr/local/lib/libwx_*.so.*.*.* \
    && cp docs/licence.txt /out/licence.txt

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS amule

# The aMule pin: amule-bump rewrites these two lines; never write the version elsewhere.
ARG AMULE_VERSION=3.2.0
ARG AMULE_COMMIT=0db738ed62ae660de2970db494976ca592bd878b
ARG WX_VERSION

# git gives CMake the version; the linker needs wx's libpcre2-32 to link amuled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         cmake g++ make pkgconf python3 git \
         libcrypto++-dev libboost-dev zlib1g-dev libcurl4-openssl-dev libpcre2-32-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wx /out/usr/local/ /usr/local/

# Tags are unsigned and movable: the checksum pins the commit, and fails a version bumped alone.
ADD --keep-git-dir=true --checksum=${AMULE_COMMIT} \
    https://github.com/amule-org/amule.git#${AMULE_VERSION} /src/amule

RUN cmake -S /src/amule -B /build -DCMAKE_BUILD_TYPE=Release \
         -DBUILD_MONOLITHIC=OFF -DBUILD_DAEMON=ON -DBUILD_AMULEAPI=ON -DBUILD_ED2K=OFF \
         -DENABLE_VERSION_CHECK=OFF -DENABLE_UPNP=OFF -DENABLE_IP2COUNTRY=OFF \
         -DENABLE_NLS=OFF -DENABLE_BFD=OFF -DENABLE_CCACHE=OFF \
    && cmake --build /build -j"$(nproc)" \
    && DESTDIR=/out cmake --install /build --strip

# Neither aMule nor wx has package metadata for Syft to find: declare both, from the same ARGs.
COPY packages/amule/docker/amule.cdx.json /tmp/amule.cdx.json
RUN sed -e "s/@AMULE_VERSION@/${AMULE_VERSION}/g" -e "s/@WX_VERSION@/${WX_VERSION}/g" \
      /tmp/amule.cdx.json > /out/usr/local/share/amule/amule.cdx.json

# A stage, not COPY --from=<image>: Dependabot only bumps FROM lines.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS python

# The build context has no .git: hatch-vcs reads the version CI computed from this variable.
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Without it, --package p2pwatch-amule also installs its dev group, the test dependencies.
    UV_NO_DEV=1 \
    UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --package p2pwatch-amule

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

# ARG after FROM only lives in the stage that declares it, hence the re-declaration.
ARG VERSION=0.0.0
LABEL org.opencontainers.image.version=${VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 s6 \
         libcrypto++8t64 libcurl4t64 libpcre2-32-0 zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Only the libraries amuled and amuleapi link; COPY follows symlinks, so ldconfig makes the sonames.
COPY --from=wx /out/usr/local/lib/libwx_baseu-3.2.so.*.*.* /out/usr/local/lib/libwx_baseu_net-3.2.so.*.*.* \
     /usr/local/lib/
COPY --from=wx /out/licence.txt /usr/local/share/doc/wxwidgets/licence.txt
RUN ldconfig

COPY --from=amule /out/usr/local/bin/amuled /out/usr/local/bin/amuleapi /usr/local/bin/
# amuleapi serves its web UI from this compiled-in path; the SBOM file sits beside it.
COPY --from=amule /out/usr/local/share/amule/ /usr/local/share/amule/
COPY --from=amule /src/amule/LICENSE.md /usr/local/share/doc/amule/LICENSE.md

COPY --from=python /app/.venv /app/.venv
COPY packages/amule/docker/entrypoint.sh /usr/local/bin/
COPY packages/amule/docker/services.d/ /etc/services.d/

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
