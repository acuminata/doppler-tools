import os
import platform
import subprocess
import sys
from pathlib import Path


def _binary_path() -> Path:
    package_dir = Path(__file__).resolve().parent
    filename = "doppler.exe" if sys.platform == "win32" else "doppler"
    executable = package_dir / "bin" / filename

    if not executable.is_file():
        raise FileNotFoundError(
            f"Doppler executable is missing: {executable}. "
            "Reinstall the doppler-bin package."
        )

    return executable


def main() -> None:
    executable = _binary_path()

    if sys.platform != "win32":
        try:
            executable.chmod(executable.stat().st_mode | 0o111)
        except OSError as exc:
            print(
                f"Unable to make Doppler executable: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

    try:
        if os.name == "nt":
            result = subprocess.run(
                [str(executable), *sys.argv[1:]],
                check=False,
            )
            raise SystemExit(result.returncode)

        os.execv(str(executable), [str(executable), *sys.argv[1:]])
    except OSError as exc:
        print(f"Unable to execute Doppler CLI: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
