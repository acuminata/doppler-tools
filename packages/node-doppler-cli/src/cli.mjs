#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const executable = path.join(root, "bin", process.platform === "win32" ? "doppler.exe" : "doppler");
const args = process.argv.slice(2);

if (process.platform !== "win32" && typeof process.execve === "function") {
    // process.execve only supported by POSIX platforms as of node v26
    try {
        process.execve(executable, [executable, ...args], process.env);
    } catch (error) {
        console.error("Failed to execute Doppler CLI:", error);
        process.exit(1);
    }
} else {
    const child = spawn(executable, args, {
        stdio: "inherit"
    });

    child.on("error", (error) => {
        console.error(`Failed to launch Doppler CLI: ${error.message}`);
        process.exitCode = 1;
    });

    child.on("exit", (code) => {
        process.exitCode = code ?? 1;
    });
}