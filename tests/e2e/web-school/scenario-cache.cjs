const fs = require('fs')
const os = require('os')
const path = require('path')

const repoRoot = path.resolve(__dirname, '..', '..', '..')

function _uniquePaths(paths) {
  const seen = new Set()
  const out = []
  for (const item of paths) {
    const resolved = path.resolve(item)
    if (seen.has(resolved)) continue
    seen.add(resolved)
    out.push(resolved)
  }
  return out
}

function scenarioCacheCandidates() {
  const explicitPath = (process.env.COURSEEVAL_E2E_SCENARIO_PATH || '').trim()
  const explicitDir = (process.env.COURSEEVAL_E2E_SCENARIO_CACHE_DIR || '').trim()
  return _uniquePaths([
    explicitPath || path.join(__dirname, '.cache', 'scenario.json'),
    explicitDir ? path.join(explicitDir, 'scenario.json') : path.join(__dirname, '.cache', 'scenario.json'),
    path.join(__dirname, '.cache', 'scenario.json'),
    path.join(repoRoot, '.agent-run', 'e2e-cache', 'scenario.json'),
    path.join(os.tmpdir(), 'courseeval-e2e-cache', 'scenario.json')
  ])
}

function readScenarioCache() {
  for (const candidate of scenarioCacheCandidates()) {
    if (!fs.existsSync(candidate)) {
      continue
    }
    return JSON.parse(fs.readFileSync(candidate, 'utf8'))
  }
  return null
}

function writeScenarioCache(data) {
  const payload = JSON.stringify(data, null, 2)
  let lastError = null
  for (const candidate of scenarioCacheCandidates()) {
    try {
      fs.mkdirSync(path.dirname(candidate), { recursive: true })
      fs.writeFileSync(candidate, payload, 'utf8')
      return candidate
    } catch (error) {
      lastError = error
    }
  }
  throw lastError || new Error('Unable to write Playwright scenario cache.')
}

module.exports = {
  readScenarioCache,
  scenarioCacheCandidates,
  writeScenarioCache
}
