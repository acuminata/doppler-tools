# Doppler CLI

The Doppler CLI distributed as a platform-specific npm package.

## Installation

Install a version matching the Doppler CLI release:

```bash
npm install doppler-bin
```

Verify the installation:

```bash
npx doppler --version
```

Use the CLI as usual:

```bash
npx doppler secrets
npx doppler run -- <your-command>
```

You can also install the package globally:

```bash
npm install --global doppler-bin
```

Then invoke the CLI directly:

```bash
doppler --version
doppler secrets
doppler run -- <your-command>
```

## Supported platforms

The package distributes the official Doppler CLI executable for the platforms and architectures listed in the corresponding release.

Each platform-specific package bundles its executable. No download is required at runtime.

| Runtime | Release platform | Architecture |
|---|---|---|
| `linux` | Linux | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |
| `darwin` | macOS | `amd64`, `arm64` |
| `win32` | Windows | `amd64`, `arm64` |
| `freebsd` | FreeBSD | `amd64`, `arm64`, `armv6`, `armv7` |
| `netbsd` | NetBSD | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |
| `openbsd` | OpenBSD | `amd64`, `arm64`, `armv6`, `armv7`, `i386` |

Actual availability depends on the platform-specific packages published for each release.

## Versioning

The npm package version matches the [upstream Doppler CLI](https://github.com/DopplerHQ/cli) version.