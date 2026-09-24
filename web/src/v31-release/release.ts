import {makeV30Planner} from '../v30/planner'

// Promote the accepted arm; do not enable the independent boundary experiment.
export const planV31=makeV30Planner(false,'dynamic')
export const V31_RELEASE={
 version:'3.1.0',
 id:'v31-live-20260924',
 acceptedArm:'original-dynamic' as const,
 acceptedSourceCommit:'9e3dacc',
 policyVersion:'v30-original-dynamic-v3.1.0',
 feedbackKey:'harbeat-v30-small-tuning-feedback-v1',
 baselineUrl:'../v3-live-baseline-20260922/index.html',
 experimentUrl:'../v30-tuning-20260924/index.html',
} as const
