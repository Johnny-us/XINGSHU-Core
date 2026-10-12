"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { createContinuationDriver } = require("../../src/xingshu_collaboration/connections/continuation_driver.cjs");
function fixture(overrides = {}) {
  const endpoint = { endpoint_id: "APP", actor_id: "ACTOR", resource_uri: "test://app/chat", generation: 1 };
  const finished = [], requests = [];
  const envelope = { protocol: "xingshu-connection/1", event: "RESULT_READY", message_id: "M_1",
    task_id: "TASK_1", ...endpoint, message_sha256:"a".repeat(64),binding_digest:"b".repeat(64),connection_digest:"c".repeat(64),consume_token: "TEST_ONLY_TOKEN" };
  const host = {
    prepare: async () => ({ ...envelope }),
    finish: async (...args) => {finished.push(args);return {state:args[1]?"DISPATCH_ACCEPTED":"DELIVERY_UNKNOWN",model_turn_consumed:false};},
    requestContinuation: async value => { requests.push(value); return true; },
    ...overrides,
  };
  return { driver: createContinuationDriver(host, endpoint), endpoint, envelope, finished, requests };
}
test("宿主接受不冒充模型已处理", async () => {
  const f = fixture(); assert.deepEqual(await f.driver.dispatch("M_1"),
    { dispatch_accepted: true, continuation_state:"DISPATCH_ACCEPTED",model_turn_consumed: false });
  assert.equal(f.finished[0][1], true); assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].includes("TEST_ONLY_TOKEN"), false);
  assert.equal(JSON.parse(f.requests[0]).consume_token, undefined);
});
test("重复调用不能再提交", async () => {
  const f = fixture(); await f.driver.dispatch("M_1");
  await assert.rejects(f.driver.dispatch("M_1"), /NO_AUTOMATIC_RESEND/);
  assert.equal(f.requests.length, 1);
});
test("响应丢失后不自动重发", async () => {
  let requests = 0;
  const f = fixture({ requestContinuation: async () => { requests++; throw Error("lost ACK"); } });
  assert.equal((await f.driver.dispatch("M_1")).dispatch_accepted, false);
  assert.equal(f.finished[0][1], false);
  await assert.rejects(f.driver.dispatch("M_1"), /NO_AUTOMATIC_RESEND/); assert.equal(requests, 1);
});
test("空响应、false和错误对象不能算宿主接受", async () => {
  for (const value of [undefined, false, { isError: true }, "true"]) {
    const f = fixture({ requestContinuation: async () => value });
    assert.equal((await f.driver.dispatch("M_1")).dispatch_accepted, false);
  }
});
test("停止后不可准备或发送", async () => {
  let prepared = false;
  const f = fixture({ prepare: async () => { prepared = true; } }); f.driver.stop();
  await assert.rejects(f.driver.dispatch("M_1"), /STOPPED/); assert.equal(prepared, false);
});
test("准备期间停止阻止后续发送", async () => {
  const f = fixture();
  const driver = createContinuationDriver({
    prepare: async () => { driver.stop(); return f.envelope; },
    requestContinuation: async () => { throw Error("must not send"); },
    finish: async (_id, accepted) => {assert.equal(accepted,false);return {state:"DELIVERY_UNKNOWN",model_turn_consumed:false};},
  }, f.endpoint);
  await assert.rejects(driver.dispatch("M_1"), /STOPPED/);
});
test("错误端点、资源、代次及消息被拒绝", async () => {
  for (const change of [{ endpoint_id: "THIRD" }, { actor_id: "OTHER" }, { resource_uri: "test://other" },
    { generation: 2 }, { message_id: "M_2" }, { consume_token: "" }, { protocol: "other" }]) {
    const f = fixture(); const calls = [];
    const driver = createContinuationDriver({ prepare: async () => ({ ...f.envelope, ...change }),
      finish: async () => {}, requestContinuation: async v => { calls.push(v); return true; } }, f.endpoint);
    await assert.rejects(driver.dispatch("M_1"), /ENVELOPE_INVALID/); assert.equal(calls.length, 0);
  }
});
test("准备请求失败也不重发", async () => {
  let prepared = 0; const f = fixture({ prepare: async () => { prepared++; throw Error("lost prepare"); } });
  await assert.rejects(f.driver.dispatch("M_1"), /lost prepare/);
  await assert.rejects(f.driver.dispatch("M_1"), /NO_AUTOMATIC_RESEND/); assert.equal(prepared, 1);
});
test("finish失败仍不能重新发原消息", async () => {
  const f = fixture({ finish: async () => { throw Error("lost finish"); } });
  await assert.rejects(f.driver.dispatch("M_1"), /lost finish/);
  await assert.rejects(f.driver.dispatch("M_1"), /NO_AUTOMATIC_RESEND/); assert.equal(f.requests.length, 1);
});
test("外部修改端点不能偷偷换绑", async () => {
  const f = fixture(); f.endpoint.resource_uri = "test://other";
  assert.equal((await f.driver.dispatch("M_1")).dispatch_accepted, true);
});
test("无效宿主在创建时拒绝", () => {
  assert.throws(() => createContinuationDriver({}, {}), /HOST_BINDING_INVALID/);
});
test("等待宿主期间停止不能报干净成功", async () => {
  const f=fixture(); let finishAccepted;
  const driver=createContinuationDriver({prepare:async()=>f.envelope,
    requestContinuation:async()=>{driver.stop();return true;},
    finish:async(_id,accepted)=>{finishAccepted=accepted;return {state:"DELIVERY_UNKNOWN",model_turn_consumed:false};}},f.endpoint);
  assert.equal((await driver.dispatch("M_1")).dispatch_accepted,false); assert.equal(finishAccepted,false);
});
test("凭证只交给经过实际消费观察的宿主", async () => {
  const f=fixture();let consumed;
  const driver=createContinuationDriver({prepare:async()=>f.envelope,requestContinuation:async value=>{
    assert.equal(value.includes(f.envelope.consume_token),false);return true;},finish:async()=>({state:"DISPATCH_ACCEPTED",model_turn_consumed:false}),
    observeConsumption:async()=>consumption(f),consume:async(_id,token)=>{consumed=token;return {state:"CONSUMED",model_turn_consumed:true,execution_completed:false,independent_review_accepted:false};}},f.endpoint);
  await driver.dispatch("M_1");assert.equal((await driver.confirmConsumed("M_1")).state,"CONSUMED");
  assert.equal(consumed,f.envelope.consume_token);
});
test("没有实际消费观察时不能使用凭证", async () => {
  const f=fixture();let consumed=false;
  const driver=createContinuationDriver({prepare:async()=>f.envelope,requestContinuation:async()=>true,
    finish:async()=>({state:"DISPATCH_ACCEPTED",model_turn_consumed:false}),observeConsumption:async()=>false,consume:async()=>{consumed=true;}},f.endpoint);
  await driver.dispatch("M_1");await assert.rejects(driver.confirmConsumed("M_1"),/NOT_OBSERVED/);
  assert.equal(consumed,false);
});

function consumption(f) {
  return {endpoint:{...f.endpoint},message_id:f.envelope.message_id,task_id:f.envelope.task_id,
    message_sha256:f.envelope.message_sha256,binding_digest:f.envelope.binding_digest,
    connection_digest:f.envelope.connection_digest,native_turn_id:"NATIVE_TURN_1",evidence_ref:"test://model-observation",
    evidence_sha256:"d".repeat(64)};
}
test("公开信封多任意字段都拒绝",async()=>{
 for (const key of ["execute_authority","prompt","instructions","tool","model","artifact_body","extra"]) {
  const f=fixture();let requested=false;
  const d=createContinuationDriver({prepare:async()=>({...f.envelope,[key]:true}),finish:async()=>{},
   requestContinuation:async()=>{requested=true;return true;}},f.endpoint);
  await assert.rejects(d.dispatch("M_1"),/ENVELOPE_INVALID/);assert.equal(requested,false);
 }
});
test("布尔 true 不能冒充结构化模型观察",async()=>{
 const f=fixture({observeConsumption:async()=>true,consume:async()=>{throw Error("must not consume");}});
 await f.driver.dispatch("M_1");await assert.rejects(f.driver.confirmConsumed("M_1"),/NOT_OBSERVED/);
});
test("消费观察的任务、消息、资源、摘要错位即停止",async()=>{
 const f=fixture();
 for (const change of [{task_id:"OTHER"},{message_id:"OTHER"},{binding_digest:"0".repeat(64)},
  {endpoint:{...f.endpoint,generation:2}},{native_turn_id:""},{evidence_sha256:"wrong"}]) {
  const d=createContinuationDriver({prepare:async()=>f.envelope,requestContinuation:async()=>true,
   finish:async()=>({state:"DISPATCH_ACCEPTED",model_turn_consumed:false}),
   observeConsumption:async()=>({...consumption(f),...change}),consume:async()=>{throw Error("must not consume");}},f.endpoint);
  await d.dispatch("M_1");await assert.rejects(d.confirmConsumed("M_1"),/NOT_OBSERVED/);
 }
});
test("未知必须在返回 API 暴露",async()=>{
 const f=fixture({requestContinuation:async()=>{throw Error("lost");}});
 assert.equal((await f.driver.dispatch("M_1")).continuation_state,"DELIVERY_UNKNOWN");
});
test("finish 状态矛盾或缺失不能丢弃",async()=>{
 for (const result of [undefined,{state:"DISPATCH_ACCEPTED",model_turn_consumed:true},
  {state:"CONSUMED",model_turn_consumed:true},{state:"DISPATCH_ACCEPTED",model_turn_consumed:false,authority:true}]) {
  const f=fixture({finish:async()=>result});await assert.rejects(f.driver.dispatch("M_1"),/FINISH_STATE_INVALID/);
 }
 const f=fixture({requestContinuation:async()=>false,finish:async()=>({state:"DISPATCH_ACCEPTED",model_turn_consumed:false})});
 await assert.rejects(f.driver.dispatch("M_1"),/FINISH_STATE_INVALID/);
});
