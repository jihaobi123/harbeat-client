/**
 * NCM (NetEase Cloud Music) file decryption.
 * Decrypts .ncm files to their original audio format (MP3 or FLAC).
 *
 * NCM file structure:
 *   [8 bytes magic] [2 bytes gap]
 *   [4 bytes key_len] [key_len bytes RC4_key (AES-128-ECB encrypted)]
 *   [4 bytes meta_len] [meta_len bytes metadata (AES-128-ECB encrypted, base64)]
 *   [5 bytes CRC gap] [4 bytes image_size] [image_size bytes album image]
 *   [... rest: RC4-encrypted audio data]
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'

const MAGIC = Buffer.from([0x43, 0x54, 0x45, 0x4e, 0x46, 0x44, 0x41, 0x4d])

// AES key for decrypting the RC4 key
const CORE_KEY = Buffer.from('687A4852416D736F356B496E62617857', 'hex')
// AES key for decrypting metadata
const META_KEY = Buffer.from('2331346C6A6B5F215C5D2630553C2728', 'hex')

function aesEcbDecrypt(data: Buffer, key: Buffer): Buffer {
  const decipher = crypto.createDecipheriv('aes-128-ecb', key, null)
  return Buffer.concat([decipher.update(data), decipher.final()])
}

interface NcmResult {
  /** Path to the decrypted temp audio file */
  audioPath: string
  /** Detected format: 'mp3' or 'flac' */
  format: string
  /** Song title from metadata (if available) */
  title?: string
  /** Artist from metadata */
  artist?: string
}

export function decryptNcm(ncmPath: string): NcmResult {
  const buf = fs.readFileSync(ncmPath)
  let offset = 0

  // 1. Verify magic header
  const magic = buf.subarray(offset, offset + 8)
  if (!magic.equals(MAGIC)) {
    throw new Error('Not a valid NCM file')
  }
  offset += 10 // 8 magic + 2 gap

  // 2. Read and decrypt the RC4 key
  const keyLen = buf.readUInt32LE(offset)
  offset += 4
  const keyData = Buffer.alloc(keyLen)
  for (let i = 0; i < keyLen; i++) {
    keyData[i] = buf[offset + i] ^ 0x64
  }
  offset += keyLen
  const decryptedKey = aesEcbDecrypt(keyData, CORE_KEY)
  // Remove "neteasecloudmusic" prefix (17 bytes)
  const rc4Key = decryptedKey.subarray(17)

  // 3. Read and decrypt metadata
  const metaLen = buf.readUInt32LE(offset)
  offset += 4
  let title: string | undefined
  let artist: string | undefined
  let detectedFormat = 'mp3'

  if (metaLen > 0) {
    const metaData = Buffer.alloc(metaLen)
    for (let i = 0; i < metaLen; i++) {
      metaData[i] = buf[offset + i] ^ 0x63
    }
    offset += metaLen

    try {
      // Skip "163 key(Don't modify):" prefix, then base64 decode, then AES decrypt
      const b64 = metaData.subarray(22).toString('ascii')
      const metaEncrypted = Buffer.from(b64, 'base64')
      const metaDecrypted = aesEcbDecrypt(metaEncrypted, META_KEY)
      // Skip "music:" prefix
      const jsonStr = metaDecrypted.subarray(6).toString('utf-8')
      const meta = JSON.parse(jsonStr)
      detectedFormat = meta.format || 'mp3'
      title = meta.musicName
      if (Array.isArray(meta.artist) && meta.artist.length > 0) {
        artist = meta.artist.map((a: [string, ...unknown[]]) => a[0]).join(' / ')
      }
    } catch {
      // Metadata parsing failed, continue with defaults
    }
  } else {
    offset += metaLen
  }

  // 4. Skip CRC (4 bytes) + gap (1 byte) + imageSpace (4 bytes) + imageSize (4 bytes) + image data
  offset += 5 // CRC32 + gap
  /* const imageSpace = */ buf.readUInt32LE(offset); offset += 4
  const imageSize = buf.readUInt32LE(offset); offset += 4
  offset += imageSize

  // 5. Build RC4 key stream (KSA + PRGA)
  const keyBox = new Uint8Array(256)
  for (let i = 0; i < 256; i++) keyBox[i] = i

  let j = 0
  for (let i = 0; i < 256; i++) {
    j = (keyBox[i] + j + rc4Key[i % rc4Key.length]) & 0xff
    ;[keyBox[i], keyBox[j]] = [keyBox[j], keyBox[i]]
  }

  // 6. Decrypt audio data using modified RC4 stream cipher
  const audioData = Buffer.alloc(buf.length - offset)
  for (let i = 0; i < audioData.length; i++) {
    const idx = (i + 1) & 0xff
    const si = keyBox[idx]
    const sj = keyBox[(si + keyBox[(idx + si) & 0xff]) & 0xff]
    audioData[i] = buf[offset + i] ^ sj
  }

  // 7. Auto-detect format from audio header if metadata was missing
  if (audioData.length > 4) {
    if (audioData[0] === 0x66 && audioData[1] === 0x4c && audioData[2] === 0x61 && audioData[3] === 0x43) {
      detectedFormat = 'flac'
    } else if (audioData[0] === 0xff && (audioData[1] & 0xe0) === 0xe0) {
      detectedFormat = 'mp3'
    } else if (audioData[0] === 0x49 && audioData[1] === 0x44 && audioData[2] === 0x33) {
      detectedFormat = 'mp3' // ID3 tag
    }
  }

  // 8. Write decrypted audio to temp file
  const tmpDir = path.join(os.tmpdir(), 'audiolab-ncm')
  if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true })

  const baseName = path.basename(ncmPath, '.ncm')
  const outPath = path.join(tmpDir, `${baseName}.${detectedFormat}`)
  fs.writeFileSync(outPath, audioData)

  return { audioPath: outPath, format: detectedFormat, title, artist }
}
