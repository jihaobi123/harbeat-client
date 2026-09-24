type InitializablePlayer={ctx:{resume:()=>Promise<void>};initialize:()=>Promise<void>}

/** Called directly by the play click, before fetching metadata or the worklet. */
export async function initializeFromGesture(player:InitializablePlayer){
 const activation=player.ctx.resume()
 await Promise.all([activation,player.initialize()])
}
