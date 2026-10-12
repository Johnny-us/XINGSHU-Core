"use strict";
// 获授权宿主私有凭证与公开状态分离；所有持久状态仍属于原日志。
function createContinuationDriver(host, endpoint) {
  endpoint=Object.freeze({...endpoint});
  const endpointKeys=["endpoint_id","actor_id","resource_uri","generation"];
  const envelopeKeys=["protocol","event","message_id","task_id",...endpointKeys,
    "message_sha256","binding_digest","connection_digest","consume_token"];
  const observationKeys=["endpoint","message_id","task_id","native_turn_id","evidence_ref",
    "evidence_sha256","message_sha256","binding_digest","connection_digest"];
  const keys=(value,expected)=>value && typeof value==="object" && !Array.isArray(value)
    && Object.keys(value).length===expected.length && expected.every(k=>Object.hasOwn(value,k));
  const hash=value=>typeof value==="string" && /^[0-9a-f]{64}$/.test(value);
  const id=value=>typeof value==="string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(value);
  if (!keys(endpoint,endpointKeys) || !id(endpoint.endpoint_id) || !id(endpoint.actor_id)
      || typeof endpoint.resource_uri!=="string" || !endpoint.resource_uri
      || !Number.isSafeInteger(endpoint.generation) || endpoint.generation<1
      || ["prepare","finish","requestContinuation"].some(k=>typeof host[k]!=="function")) {
    throw Error("CONTINUATION_HOST_BINDING_INVALID");
  }
  let active=true;
  const attempted=new Set(), privateContexts=new Map();
  const sameEndpoint=value=>keys(value,endpointKeys) && endpointKeys.every(k=>value[k]===endpoint[k]);
  function validObservation(value, context) {
    return keys(value,observationKeys) && sameEndpoint(value.endpoint)
      && ["message_id","task_id","message_sha256","binding_digest","connection_digest"].every(k=>value[k]===context[k])
      && typeof value.native_turn_id==="string" && value.native_turn_id.length>0 && value.native_turn_id.length<=128
      && typeof value.evidence_ref==="string" && value.evidence_ref.length>0 && value.evidence_ref.length<=2048
      && hash(value.evidence_sha256);
  }
  async function finish(messageId,accepted,context) {
    const result=await host.finish(messageId,accepted,endpoint);
    const ordinary=keys(result,["state","model_turn_consumed"]) && result.model_turn_consumed===false
      && (result.state==="DELIVERY_UNKNOWN" || (accepted && result.state==="DISPATCH_ACCEPTED"));
    const consumed=keys(result,["state","model_turn_consumed","consumption_observation"])
      && result.state==="CONSUMED" && result.model_turn_consumed===true
      && validObservation(result.consumption_observation,context);
    if (!ordinary && !consumed) throw Error("CONTINUATION_FINISH_STATE_INVALID");
    return {dispatch_accepted:result.state==="DISPATCH_ACCEPTED",continuation_state:result.state,
      model_turn_consumed:consumed};
  }
  return {
    async dispatch(messageId) {
      if (!active) throw Error("CONTINUATION_STOPPED");
      if (attempted.has(messageId)) throw Error("CONTINUATION_NO_AUTOMATIC_RESEND");
      attempted.add(messageId);
      const value=await host.prepare(messageId,endpoint);
      if (!keys(value,envelopeKeys) || value.protocol!=="xingshu-connection/1" || value.event!=="RESULT_READY"
          || !endpointKeys.every(k=>value[k]===endpoint[k]) || value.message_id!==messageId
          || !id(value.message_id) || !id(value.task_id)
          || !["message_sha256","binding_digest","connection_digest"].every(k=>hash(value[k]))
          || typeof value.consume_token!=="string" || !value.consume_token || value.consume_token.length>128) {
        throw Error("CONTINUATION_ENVELOPE_INVALID");
      }
      const {consume_token:token,...publicEnvelope}=value;
      privateContexts.set(messageId,{token,...publicEnvelope});
      if (!active) {await finish(messageId,false,publicEnvelope);throw Error("CONTINUATION_STOPPED");}
      let accepted=false;
      try {accepted=(await host.requestContinuation(JSON.stringify(publicEnvelope)))===true;} catch (_) {}
      if (!active) accepted=false;
      return finish(messageId,accepted,publicEnvelope);
    },
    async confirmConsumed(messageId) {
      const context=privateContexts.get(messageId);
      if (!context || typeof host.observeConsumption!=="function" || typeof host.consume!=="function") {
        throw Error("CONTINUATION_CONSUMPTION_HOST_REQUIRED");
      }
      const observation=await host.observeConsumption(messageId,endpoint);
      if (!validObservation(observation,context)) throw Error("CONTINUATION_MODEL_TURN_NOT_OBSERVED");
      const result=await host.consume(messageId,context.token,endpoint,observation);
      if (!result || result.state!=="CONSUMED" || result.model_turn_consumed!==true
          || result.execution_completed!==false || result.independent_review_accepted!==false) {
        throw Error("CONTINUATION_CONSUMPTION_RESULT_INVALID");
      }
      return result;
    },
    stop() {active=false;},
  };
}
module.exports={createContinuationDriver};
