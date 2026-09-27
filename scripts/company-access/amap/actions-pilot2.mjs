// Fixed manual Pilot 2 adapter; shared acquisition/secret gate/preparation.
import { main } from './actions-pilot.mjs';
main('amap-pilot-2').catch(()=>{console.error('PILOT_FAILED: inspect safe QA artifacts.');process.exitCode=1;});
