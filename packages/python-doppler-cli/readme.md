# Doppler CLI

The Doppler CLI distributed as platform-specific Python wheels.

## Installation

Install a version matching the Doppler CLI release:

```bash
python -m pip install doppler-bin==3.77.1
```

Verify the installation:

```bash
doppler --version
```

Use the CLI as usual:

```bash
doppler secrets
doppler run -- <your-command>
```

## Supported platforms

The package distributes the official Doppler CLI executable for the
platforms and architectures listed in the corresponding release.

Each wheel bundles its executable. No download is required at runtime.

| Runtime   | Release platform |  Architecture                              |
|-----------|------------------|--------------------------------------------|
| `linux`   | Linux            | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |
| `darwin`  | macOS            | `amd64`, `arm64`                           |
| `win32`   | Windows          | `amd64`, `arm64`                           |
| `freebsd` | FreeBSD          | `amd64`, `arm64`, `armv6`, `armv7`         |
| `netbsd`  | NetBSD           | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |
| `openbsd` | OpenBSD          | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |

## Versioning

The Python package version matches the [upstream Doppler CLI](https://github.com/DopplerHQ/cli) version.

