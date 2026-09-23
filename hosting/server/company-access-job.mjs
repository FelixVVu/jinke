// Private callable job for the existing Cloudflare Worker (nodejs_compat).
// Intentionally no public HTTP route, browser import, scheduled trigger or secret export.
import { acquire } from '../../scripts/company-access/amap/acquire.mjs';
import { sha256, stable, fail } from '../../scripts/company-access/common.mjs';
export const PILOT_REACH_SHA256='2e1b01d4d7b70437836458dbb0b219e823d1bea582b692c4ab57b4c4d60306c7';
export async function runCompanyAccessPilot(env, { reachAreas, collectedAt, previous, checkpoint }, dependencies = {}) {
  if(sha256(stable(reachAreas))!==PILOT_REACH_SHA256)fail('PILOT_REACH_CHANGED');
  if(env?.JINKE_AMAP_KEY && typeof checkpoint!=='function')fail('PRIVATE_CHECKPOINT_REQUIRED');
  return acquire({ env, areas: reachAreas, collectedAt, previous, checkpoint, ...dependencies });
}
