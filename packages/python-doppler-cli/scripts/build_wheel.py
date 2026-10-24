#!/usr/bin/env python3
import argparse
import base64
import hashlib
import io
import re
import sys
import tarfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from email.message import EmailMessage
from email.policy import default
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src" / "doppler_cli"


def digest(data: bytes) -> str:
    value = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def record_line(name: str, data: bytes) -> str:
    return f"{name},sha256={digest(data)},{len(data)}"


def normalize_platform(platform: str) -> str:
    aliases = {
        "win": "windows",
        "mac os": "macos",
        "darwin": "macos",
    }
    value = platform.strip().lower()
    return aliases.get(value, value)


def download_asset(version: str, platform: str, arch: str) -> bytes:
    platform = normalize_platform(platform)
    extension = "zip" if platform == "windows" else "tar.gz"
    filename = f"doppler_{version}_{platform}_{arch}.{extension}"
    url = "https://github.com/DopplerHQ/cli/releases/download/" f"{version}/{filename}"

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream"},
    )

    print(f"Downloading {url}")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Failed to download {url}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to download {url}: {exc.reason}") from exc


def extract_executable(
    archive_data: bytes,
    platform: str,
) -> tuple[str, bytes]:
    platform = normalize_platform(platform)
    expected = "doppler.exe" if platform == "windows" else "doppler"

    if platform == "windows":
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            candidates = [
                item
                for item in archive.infolist()
                if not item.is_dir() and PurePosixPath(item.filename).name == expected
            ]

            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected exactly one {expected} in ZIP; "
                    f"found {len(candidates)}"
                )

            return expected, archive.read(candidates[0])

    with tarfile.open(
        fileobj=io.BytesIO(archive_data),
        mode="r:gz",
    ) as archive:
        candidates = [
            item
            for item in archive.getmembers()
            if item.isfile() and PurePosixPath(item.name).name == expected
        ]

        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected exactly one {expected} in tarball; "
                f"found {len(candidates)}"
            )

        member = candidates[0]
        source = archive.extractfile(member)

        if source is None:
            raise RuntimeError(f"Unable to read executable {member.name}")

        return expected, source.read()


def generate_metadata(version: str) -> bytes:
    pyproject_path = ROOT / "pyproject.toml"

    with pyproject_path.open("rb") as file:
        config = tomllib.load(file)

    project = config["project"]
    urls = project.get("urls", {})

    #Override email policy so it doesn't wrap long text
    policy = default.clone(max_line_length=sys.maxsize)
    metadata = EmailMessage(policy=policy)

    metadata["Metadata-Version"] = "2.4"
    metadata["Name"] = project["name"]
    metadata["Version"] = version
    metadata["Summary"] = project["description"]
    metadata["Requires-Python"] = project["requires-python"]

    license_value = project.get("license")
    if isinstance(license_value, str):
        metadata["License-Expression"] = license_value

    for label, url in urls.items():
        metadata["Project-URL"] = f"{label}, {url}"

    for classifier in project.get("classifiers", []):
        metadata["Classifier"] = classifier

    keywords = project.get("keywords", [])
    if keywords:
        metadata["Keywords"] = ", ".join(keywords)

    if isinstance(project.get("readme"), str):
        readme_path = ROOT / project["readme"]

        if readme_path.is_file():
            metadata.set_content(
                readme_path.read_text(encoding="utf-8"),
                subtype="plain",
                charset="utf-8",
                cte="8bit",
            )
            # set description header
            metadata["Description-Content-Type"] = "text/markdown; charset=UTF-8"

            # delete extra headers
            del metadata["Content-Type"]
            del metadata["Content-Transfer-Encoding"]
            del metadata["MIME-Version"]

    return metadata.as_bytes()


def platform_tag(
    platform: str,
    arch: str,
    os_version: str | None = None,
    linux_libc: str | None = None,
) -> str | None:
    platform = normalize_platform(platform)

    architectures = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "x64": "x86_64",
        "i386": "i686",
        "i686": "i686",
        "x86": "i686",
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "armv6": "armv6l",
        "armv6l": "armv6l",
        "armv7": "armv7l",
        "armv7l": "armv7l",
    }

    cpu = architectures.get(arch.strip().lower())
    if cpu is None:
        return None

    # normalize empty strings
    os_version = os_version or None
    linux_libc = linux_libc or None

    if platform in {"linux", "manylinux", "musllinux"}:
        libc = (linux_libc or platform).strip().lower()

        if libc == "linux":
            libc = "manylinux"

        if libc == "manylinux":
            version = os_version or "2.17"
            prefix = "manylinux"
        elif libc == "musllinux":
            version = os_version or "1.2"
            prefix = "musllinux"
        else:
            return None

        if not re.fullmatch(r"\d+\.\d+", version):
            return None

        return f"{prefix}_{version.replace('.', '_')}_{cpu}"

    if platform in {"macos", "macosx"}:
        version = os_version or "10.13"
        version = version.replace("-", ".")

        if not re.fullmatch(r"\d+\.\d+", version):
            return None

        mac_cpu = {
            "x86_64": "x86_64",
            "i686": "i386",
            "aarch64": "arm64",
        }.get(cpu)

        if mac_cpu is None:
            return None

        major, minor = version.split(".")
        return f"macosx_{major}_{minor}_{mac_cpu}"

    if platform == "windows":
        return {
            "x86_64": "win_amd64",
            "i686": "win32",
            "aarch64": "win_arm64",
        }.get(cpu)

    if platform in {"freebsd", "netbsd", "openbsd"}:
        return f"{platform}_{cpu}"

    return None


def build_wheel(
    version: str,
    platform: str,
    arch: str,
    executable_name: str,
    executable_data: bytes,
    output_dir: Path,
    wheel_platform: str,
) -> Path:
    distribution = "doppler_bin"
    dist_info = f"{distribution}-{version}.dist-info"
    tag = f"py3-none-{wheel_platform}"
    wheel_name = f"{distribution}-{version}-{tag}.whl"

    package_files = {
        "doppler_cli/__init__.py": (
            '"""Doppler CLI executable distribution."""\n'
            f'__version__ = "{version}"\n'
        ).encode("utf-8"),
        "doppler_cli/launcher.py": (PACKAGE_DIR / "launcher.py").read_bytes(),
        f"doppler_cli/bin/{executable_name}": executable_data,
        f"{dist_info}/METADATA": generate_metadata(version),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: doppler-cli-wheel-builder\n"
            "Root-Is-Purelib: false\n"
            f"Tag: {tag}\n"
        ).encode("utf-8"),
        f"{dist_info}/entry_points.txt": (
            "[console_scripts]\n" "doppler = doppler_cli.launcher:main\n"
        ).encode("utf-8"),
    }

    record_name = f"{dist_info}/RECORD"
    rows = [record_line(name, data) for name, data in package_files.items()]
    rows.append(f"{record_name},,")
    package_files[record_name] = ("\n".join(rows) + "\n").encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / wheel_name

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as wheel:
        for name, data in package_files.items():
            info = zipfile.ZipInfo(name)

            # Preserve executable permissions for POSIX binaries.
            if name.startswith("doppler_cli/bin/") and platform != "windows":
                info.external_attr = (0o100755 & 0xFFFF) << 16
            else:
                info.external_attr = (0o100644 & 0xFFFF) << 16

            wheel.writestr(info, data)

    print(f"Created {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument(
        "--os-version",
        help=(
            "OS compatibility version. Defaults to 2.17 for manylinux, "
            "1.2 for musllinux, and 10.13 for macOS"
        ),
        default=None,
    )
    parser.add_argument(
        "--linux-libc",
        help="Linux libc compatibility target (choose from 'manylinux', 'musllinux')",
        default=None,
    )
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()

    version = args.version.removeprefix("v")

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+!-]*)?", version):
        raise SystemExit(f"Invalid release version: {version}")

    # Normalize empty string or validate choices manually
    if args.linux_libc == "":
        args.linux_libc = None
    elif args.linux_libc not in (None, "manylinux", "musllinux"):
        parser.error(
            f"argument --linux-libc: invalid choice: {args.linux_libc!r} (choose from 'manylinux', 'musllinux')"
        )

    platform = normalize_platform(args.platform)

    target = platform_tag(
        platform,
        args.arch,
        os_version=args.os_version,
        linux_libc=args.linux_libc,
    )

    if target is None:
        raise SystemExit(f"Unsupported build target: {args.platform}/{args.arch}")

    archive_data = download_asset(version, platform, args.arch)
    executable_name, executable_data = extract_executable(
        archive_data,
        platform,
    )

    if not executable_data:
        raise SystemExit("The downloaded executable is empty")

    build_wheel(
        version=version,
        platform=platform,
        arch=args.arch,
        executable_name=executable_name,
        executable_data=executable_data,
        output_dir=Path(args.output_dir),
        wheel_platform=target,
    )


if __name__ == "__main__":
    main()
