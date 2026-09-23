import { env } from 'cloudflare:workers';
import { searchPlaces } from '../../../server/map-runtime.mjs';
export const dynamic = 'force-dynamic';
export function GET(request: Request) { return searchPlaces(request, env); }
