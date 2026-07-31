import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execFileSync } from 'node:child_process'

function gitOutput(args: string[]): string | null {
  try {
    return execFileSync('git', args, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return null
  }
}

const sourceRevision =
  process.env.VERCEL_GIT_COMMIT_SHA ?? gitOutput(['rev-parse', 'HEAD'])
const trackedStatus = gitOutput([
  'status',
  '--porcelain',
  '--untracked-files=no',
])

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_REVISION__: JSON.stringify(sourceRevision),
    __BUILD_TRACKED_DIRTY__: JSON.stringify(
      trackedStatus == null ? null : trackedStatus.length > 0,
    ),
  },
})
