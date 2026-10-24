#!/usr/bin/env python3
import argparse
import base64
import hashlib
import io
import os
import re
import tarfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from email.message import EmailMessage
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src" / "doppler_cli"

# Asset platform, asset architecture, and corresponding wheel platform tag.
WHEEL_PLATFORMS = {
    ("linux", "amd64"): "linux_x86_64",
    ("linux", "arm64"): "linux_aarch64",
    ("linux", "armv6"): "linux_armv6l",
    ("linux", "armv7"): "linux_armv7l",
    ("linux", "i386"): "linux_i686",

    ("macOS", "amd64"): "macosx_10_13_x86_64",
    ("macOS", "arm64"): "macosx_11_0_arm64",

    ("windows", "amd64"): "win_amd64",
    ("windows", "arm64"): "win_arm64",

    ("freebsd", "amd64"): "freebsd_amd64",
    ("freebsd", "arm64"): "freebsd_arm64",
    ("freebsd", "armv6"): "freebsd_armv6",
    ("freebsd", "armv7"): "freebsd_armv7",

    ("netbsd", "amd64"): "netbsd_amd64",
    ("netbsd", "arm64"): "netbsd_arm64",
    ("netbsd", "armv6"): "netbsd_armv6",
    ("netbsd", "armv7"): "netbsd_armv7",
    ("netbsd", "i386"): "netbsd_i386",

    ("openbsd", "amd64"): "openbsd_amd64",
    ("openbsd", "arm64"): "openbsd_arm64",
    ("openbsd", "armv6"): "openbsd_armv6",
    ("openbsd", "armv7"): "openbsd_armv7",
    ("openbsd", "i386"): "openbsd_i386",
}


def digest(data: bytes) -> str:
    value = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def record_line(name: str, data: bytes) -> str:
    return f"{name},sha256={digest(data)},{len(data)}"


def download_asset(version: str, platform: str, arch: str) -> bytes:
    extension = "zip" if platform == "windows" else "tar.gz"

    filename = (
        f"doppler_{version}_{platform}_{arch}.{extension}"
    )

    url = (
        "https://github.com/DopplerHQ/cli/releases/download/"
        f"{version}/{filename}"
    )

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
        raise RuntimeError(
            f"Unable to download {url}: {exc.reason}"
        ) from exc


def extract_executable(
    archive_data: bytes,
    platform: str,
) -> tuple[str, bytes]:
    expected = "doppler.exe" if platform == "windows" else "doppler"

    if platform == "windows":
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            candidates = [
                item
                for item in archive.infolist()
                if not item.is_dir()
                and PurePosixPath(item.filename).name == expected
            ]

            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected exactly one {expected} in ZIP; "
                    f"found {len(candidates)}"
                )

            return expected, archive.read(candidates[0])
    else:
        with tarfile.open(
            fileobj=io.BytesIO(archive_data),
            mode="r:gz",
        ) as archive:
            candidates = [
                item
                for item in archive.getmembers()
                if item.isfile()
                and PurePosixPath(item.name).name == expected
            ]

            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected exactly one {expected} in tarball; "
                    f"found {len(candidates)}"
                )

            member = candidates[0]
            source = archive.extractfile(member)

            if source is None:
                raise RuntimeError(
                    f"Unable to read executable {member.name}"
                )

            return expected, source.read()


def generate_metadata(version: str) -> bytes:
    pyproject_path = ROOT / "pyproject.toml"

    with pyproject_path.open("rb") as file:
        config = tomllib.load(file)

    project = config["project"]
    urls = project.get("urls", {})

    metadata = EmailMessage()
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

    if isinstance(project.get("readme"), str):
        readme_path = ROOT / project.get("readme")

        if readme_path.is_file():
            metadata.set_content(
                readme_path.read_text(encoding="utf-8"),
                subtype="plain",
                charset="utf-8",
                cte="8bit",
            )
            #set description header
            metadata["Description-Content-Type"]= "text/markdown; charset=UTF-8"

            #delete extra headers
            del metadata["Content-Type"]
            del metadata["Content-Transfer-Encoding"]
            del metadata["MIME-Version"]


    return metadata.as_bytes()


def build_wheel(
    version: str,
    platform: str,
    arch: str,
    executable_name: str,
    executable_data: bytes,
    output_dir: Path,
) -> Path:
    wheel_platform = WHEEL_PLATFORMS[(platform, arch)]

    distribution = "doppler_cli"
    dist_info = f"{distribution}-{version}.dist-info"
    tag = f"py3-none-{wheel_platform}"
    wheel_name = f"{distribution}-{version}-{tag}.whl"

    package_files = {
        "doppler_cli/__init__.py": (
            f'"""Doppler CLI executable distribution."""\n'
            f'__version__ = "{version}"\n'
        ).encode("utf-8"),
        "doppler_cli/launcher.py": (
            PACKAGE_DIR / "launcher.py"
        ).read_bytes(),
        f"doppler_cli/bin/{executable_name}": executable_data,
        f"{dist_info}/METADATA": generate_metadata(version),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: doppler-cli-wheel-builder\n"
            "Root-Is-Purelib: false\n"
            f"Tag: {tag}\n"
        ).encode("utf-8"),
        f"{dist_info}/entry_points.txt": (
            "[console_scripts]\n"
            "doppler = doppler_cli.launcher:main\n"
        ).encode("utf-8"),
    }

    record_name = f"{dist_info}/RECORD"
    rows = [
        record_line(name, data)
        for name, data in package_files.items()
    ]
    rows.append(f"{record_name},,")

    package_files[record_name] = (
        "\n".join(rows) + "\n"
    ).encode("utf-8")

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
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()

    version = args.version.removeprefix("v")

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+!-]*)?", version):
        raise SystemExit(f"Invalid release version: {version}")

    key = (args.platform, args.arch)

    if key not in WHEEL_PLATFORMS:
        raise SystemExit(
            f"Unsupported build target: {args.platform}/{args.arch}"
        )

    archive_data = download_asset(version, args.platform, args.arch)
    executable_name, executable_data = extract_executable(
        archive_data,
        args.platform,
    )

    if not executable_data:
        raise SystemExit("The downloaded executable is empty")

    build_wheel(
        version=version,
        platform=args.platform,
        arch=args.arch,
        executable_name=executable_name,
        executable_data=executable_data,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
