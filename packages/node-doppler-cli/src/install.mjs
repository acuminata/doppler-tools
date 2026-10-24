
import childProcess from "node:child_process";
import fs from "node:fs";
import stream from "node:stream";
import path from "node:path";
import zlib from "node:zlib";
import { pipeline } from "node:stream/promises";
import * as tar from "tar";
import yauzl from "yauzl";
import packageJSON from "../package.json" with { type: "json" };

const outputDir = path.resolve("bin");

const PLATFORMS = {
    linux: "linux",
    darwin: "macOS",
    win32: "windows",
    freebsd: "freebsd",
    netbsd: "netbsd",
    openbsd: "openbsd",
};

const ARCHITECTURES = {
    x64: "amd64",
    arm64: "arm64",
    ia32: "i386",
};

function detectArmArchitecture() {
    let machine;

    try {
        machine = childProcess
            .execFileSync("uname", ["-m"], { encoding: "utf8" })
            .trim()
            .toLowerCase();
    } catch {
        throw new Error("Unable to detect the 32-bit ARM architecture.");
    }

    if (/armv6/.test(machine)) return "armv6";

    if (/armv7/.test(machine) || /armv8l/.test(machine)) {
        return "armv7";
    }

    if (/^(arm|armhf|armel|aarch32)$/.test(machine)) {
        return "armv7";
    }

    throw new Error(`Unsupported 32-bit ARM architecture: ${machine}`);
}

async function latestVersion() {
    const url = "https://api.github.com/repos/DopplerHQ/cli/releases/latest";
    const response = await fetch(url, {
        headers: {Accept: "application/vnd.github+json"},
        signal: AbortSignal.timeout(15_000),
    });

    if (!response.ok) {
        throw new Error(`Failed to resolve latest Doppler CLI release: HTTP ${response.status}`);
    }

    const release = await response.json();
    const version = release.tag_name?.replace(/^v/, "");

    if (!version || release.draft || release.prerelease) {
        throw new Error("GitHub returned an invalid latest stable release");
    }

    return version;

}

async function resolveTarget() {
    const platform = PLATFORMS[process.platform];

    if (!platform) {
        throw new Error(`Unsupported platform: ${process.platform}`);
    }

    const architecture = ARCHITECTURES[process.arch] ?? (process.arch === "arm" ? detectArmArchitecture() : undefined);

    if (!architecture) {
        throw new Error(`Unsupported architecture: ${process.arch}`);
    }

    const version = packageJSON.version === '0.0.0' ? await latestVersion() : packageJSON.version;
    const extension = platform === "windows" ? "zip" : "tar.gz";
    const filename = `doppler_${version}_${platform}_${architecture}.${extension}`;

    return {
        version,
        platform,
        architecture,
        extension,
        url: `https://github.com/DopplerHQ/cli/releases/download/${version}/${filename}`,
        executable: platform === "windows" ? "doppler.exe" : "doppler",
    };
}

async function downloadBinary(url) {
    const response = await fetch(url, {
        headers: { Accept: "application/octet-stream" },
        signal: AbortSignal.timeout(120_000),
    });

    if (!response.ok) {
        await response.body?.cancel();

        throw new Error(
            `Failed to download ${url}: HTTP ${response.status} ${response.statusText}`
        );
    }

    if (!response.body) {
        throw new Error("Download response has no body");
    }

    return response;
}

function extractZip(buffer, executableFilename, destination) {
    return new Promise((resolve, reject) => {
        yauzl.fromBuffer(buffer, { lazyEntries: true }, (error, zipfile) => {
            if (error) {
                reject(error);
                return;
            }

            let found = false;
            let settled = false;

            function fail(error) {
                if (settled) return;
                settled = true;
                zipfile.close();
                reject(error);
            }

            zipfile.on("error", fail);

            zipfile.on("entry", (entry) => {
                if (entry.fileName.endsWith("/")) {
                    zipfile.readEntry();
                    return;
                }

                if (path.posix.basename(entry.fileName) !== executableFilename) {
                    zipfile.readEntry();
                    return;
                }

                if (found) {
                    fail(new Error(`Multiple ${executableFilename} executables found in ZIP`));
                    return;
                }

                found = true;

                zipfile.openReadStream(entry, (streamError, readStream) => {
                    if (streamError) {
                        fail(streamError);
                        return;
                    }

                    const writeStream = fs.createWriteStream(destination);

                    readStream.on("error", fail);
                    writeStream.on("error", fail);

                    writeStream.on("finish", () => {
                        if (!settled) {
                            zipfile.readEntry();
                        }
                    });

                    readStream.pipe(writeStream);
                });
            });

            zipfile.on("end", () => {
                if (settled) return;

                if (!found) {
                    fail(new Error(`No ${executableFilename} executable found in ZIP`));
                    return;
                }

                settled = true;
                resolve();
            });

            zipfile.readEntry();
        });
    });
}

async function extractTarGz(response, executableFilename, destination) {
    let found = false;

    const extractor = tar.x({
        cwd: destination,
        filter(entryPath, entry) {
            if (path.posix.basename(entryPath) !== executableFilename) {
                return false;
            }

            if (entry.type !== "File" && entry.type !== "OldFile") {
                return false;
            }

            if (found) {
                throw new Error(`Multiple ${executableFilename} executables found in tarball`);
            }
            found = true;
            return true;
        },
    });

    await pipeline(
        stream.Readable.fromWeb(response.body),
        zlib.createGunzip(),
        extractor
    );

    if (!found) {
        throw new Error(`No ${executableFilename} executable found in tarball`);
    }
}

async function main() {
    const target = await resolveTarget();

    console.log(`Downloading Doppler CLI ${target.version}`);
    console.log(target.url);

    fs.mkdirSync(outputDir, { recursive: true });


    const response = await downloadBinary(target.url);

    if (target.extension === "zip") {
        const buffer = Buffer.from(await response.arrayBuffer());

        await extractZip(buffer, target.executable, outputDir);
    } else {
        await extractTarGz(response, target.executable, outputDir);
    }

    const executable = path.join(outputDir, target.executable);
    const stats = fs.statSync(executable);

    if (!stats.isFile() || stats.size === 0) {
        throw new Error(`Invalid or empty executable: ${executable}`);
    }

    if (target.platform !== "windows") {
        fs.chmodSync(executable, 0o755);
    }

    console.log(`Doppler CLI installed successfully: ${executable}`);

}

main().catch((error) => {
    console.error("Error downloading or extracting Doppler CLI:", error);
    process.exitCode = 1;
});
