#!/usr/bin/env node
'use strict';

const { createHash } = require('node:crypto');
const { readFile } = require('node:fs/promises');
const { HalModuleParser } = require('binary-version-reader');

async function main() {
    const [filename, expectation] = process.argv.slice(2);
    if (!filename || (expectation && !['user', 'system1', 'system2'].includes(expectation))) {
        throw new Error('Usage: node firmware/tools/inspect-module.cjs FILE [user|system1|system2]');
    }
    const bytes = await readFile(filename);
    const result = await new HalModuleParser().parseBuffer({ filename, fileBuffer: bytes });
    const prefix = result.prefixInfo;
    if (!result.crc.ok || prefix.platformID !== 6) {
        throw new Error('Not a CRC-valid original Photon module (platform 6)');
    }
    const start = Number.parseInt(prefix.moduleStartAddy, 16);
    const end = Number.parseInt(prefix.moduleEndAddy, 16);
    if (end - start + 4 !== bytes.length) {
        throw new Error('Module address span does not match the binary length including CRC');
    }
    if (expectation === 'user' && (
        prefix.moduleFunction !== 5 || prefix.moduleIndex !== 1 || prefix.moduleFlags !== 0 ||
        start !== 0x080a0000 || bytes.length > 128 * 1024 ||
        prefix.depModuleFunction !== 4 || prefix.depModuleIndex !== 2 || prefix.depModuleVersion !== 2302
    )) {
        throw new Error('User module does not match the pinned Photon Device OS 2.3.1 build contract');
    }
    if (expectation === 'system1' || expectation === 'system2') {
        const part = expectation === 'system1' ? 1 : 2;
        const address = part === 1 ? 0x08020000 : 0x08060000;
        if (prefix.moduleFunction !== 4 || prefix.moduleIndex !== part ||
            prefix.moduleVersion !== 2302 || start !== address || bytes.length > 256 * 1024) {
            throw new Error('System module does not match the official Photon Device OS 2.3.1 component');
        }
    }
    delete result.fileBuffer;
    result.sha256 = createHash('sha256').update(bytes).digest('hex');
    console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
});
