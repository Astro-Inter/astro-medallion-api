import { Client, types } from "pg";
import contract from "./contract.json";

// All integer identifiers retain decimal precision. JSON is returned as text.
types.setTypeParser(20, value => value);
types.setTypeParser(1082, value => value);
types.setTypeParser(1184, value => value);
const publicDatasets = contract.datasets.map(({source_save, range_save, ...dataset}) => dataset);
const timezone = "America/Sao_Paulo";
const dayMs = 86400000;
const dateFormat = new Intl.DateTimeFormat("en-CA", {timeZone: timezone, year:"numeric",month:"2-digit",day:"2-digit"});

class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status=status; this.code=code; }
}
function fail(status, code, message) { throw new ApiError(status,code,message); }
function calendarDate(now) {
  const p=Object.fromEntries(dateFormat.formatToParts(now).map(p=>[p.type,p.value]));
  return `${p.year}-${p.month}-${p.day}`;
}
function parseDate(value) {
  const d=new Date(value+"T00:00:00Z");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value)||!Number.isFinite(+d)||d.toISOString().slice(0,10)!==value||value<"1900-01-01")
    fail(400,"invalid_date","Use YYYY-MM-DD válido, com ano >= 1900.");
  return value;
}
function integer(value, fallback, min, max) {
  if(value===null) return fallback;
  if(!/^\d+$/.test(value)||value.length>String(max).length||BigInt(value)<BigInt(min)||BigInt(value)>BigInt(max))
    fail(400,"invalid_pagination",`Use inteiros entre ${min} e ${max}.`);
  return Number(value);
}
function options(params,dataset,today,firstDate) {
  const allowed=new Set(["limit","offset","from","to","snapshot",...(dataset.layer==="gold"?["date","id_unidade"]:[])]);
  for(const key of params.keys()) if(!allowed.has(key)||params.getAll(key).length!==1)
    fail(400,"invalid_parameter",`Parâmetro não suportado ou repetido: ${key}.`);
  let start=dataset.layer==="silver"?today.slice(0,4)+"-01-01":today;
  if(firstDate&&firstDate>start) start=firstDate;
  let end=today;
  if(params.has("date")) {
    if(params.has("from")||params.has("to")) fail(400,"invalid_parameter","Não combine date com from/to.");
    start=end=parseDate(params.get("date"));
  } else { start=parseDate(params.get("from")??start); end=parseDate(params.get("to")??end); }
  if(start>end||end>today) fail(400,"invalid_range","O período deve ser ordenado e terminar até hoje.");
  if((Date.parse(end)-Date.parse(start))/dayMs>=366) fail(400,"range_too_large","Solicite no máximo 366 dias por período.");
  if(dataset.layer==="gold"&&start!==end) fail(400,"invalid_range","Gold aceita uma data por chamada; use date.");
  if(firstDate&&start<firstDate) fail(409,"historical_snapshot_unavailable",`Histórico disponível a partir de ${firstDate}.`);
  let snapshot=params.get("snapshot");
  if(snapshot!==null) {
    // Accept UUID representations supported by Python's UUID constructor.
    const raw=snapshot.replace(/^urn:uuid:/i,"").replace(/[{}-]/g,"");
    if(!/^[0-9a-f]{32}$/i.test(raw)) fail(400,"invalid_snapshot","Snapshot deve ser um UUID válido.");
    snapshot=raw.replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/,"$1-$2-$3-$4-$5").toLowerCase();
  }
  const offset=integer(params.get("offset"),0,0,1000000);
  if(offset&&!snapshot) fail(400,"snapshot_required","Use pagination.next para continuar a extração.");
  let unit=null;
  if(params.has("id_unidade")) {
    const value=params.get("id_unidade");
    if(!/^\d+$/.test(value)||value.length>19||BigInt(value)<1n||BigInt(value)>9223372036854775807n)
      fail(400,"invalid_pagination","Use um identificador inteiro válido de unidade.");
    unit=BigInt(value).toString(); // Never round bigint IDs in JavaScript.
  }
  return {start,end,limit:integer(params.get("limit"),500,1,1000),offset,snapshot,unit};
}
function bind(sql,values) {
  const keys=[];
  return {text:sql.replace(/%\((\w+)\)s/g,(_,key)=>{
    if(!Object.hasOwn(values,key)) throw new Error("Missing SQL parameter");
    if(!keys.includes(key)) keys.push(key);
    return "$"+(keys.indexOf(key)+1);
  }),values:keys.map(key=>values[key])};
}

class Store {
  constructor(env,ctx,requestId) { this.env=env;this.ctx=ctx;this.requestId=requestId;this.client=null; }
  async query(sql,values={}) {
    try {
      if(!this.client) {
        this.client=new Client({connectionString:this.env.HYPERDRIVE.connectionString,
          connectionTimeoutMillis:10000,query_timeout:12000});
        this.client.on("error",()=>{});
        await this.client.connect();
      }
      if (!this.inTransaction) {
        await this.client.query("BEGIN; SET LOCAL TIME ZONE 'America/Sao_Paulo'; SET LOCAL statement_timeout='10s'");
        this.inTransaction = true;
      }
      try {
        const result=await this.client.query(bind(sql,values));
        return result.rows;
      } catch(error) {
        await this.client.query("ROLLBACK").catch(()=>{});
        this.inTransaction = false;
        throw error;
      }
    } catch(error) {
      console.error(JSON.stringify({event:"dependency_failed",service_name:"astro-medallion-api",
        request_id:this.requestId,error_type:error.name,error_code:/^[A-Z0-9_]{1,32}$/.test(error.code??"")?error.code:"UNCLASSIFIED_ERROR"}));
      throw new ApiError(503,"source_unavailable","A fonte PostgreSQL está indisponível.");
    }
  }
  async finish() {
    if (this.inTransaction) {
      this.inTransaction = false;
      try { await this.client.query("COMMIT"); }
      catch { throw new ApiError(503,"source_unavailable","A fonte PostgreSQL está indisponível."); }
    }
  }
  close() { if(this.client) this.ctx.waitUntil(this.client.end().catch(()=>{})); }
  async firstDate() {
    const rows=await this.query("SELECT (installed_at AT TIME ZONE 'America/Sao_Paulo')::date AS first_date FROM astro_api.history_control WHERE singleton");
    if(!rows.length) fail(503,"migration_required","Migração de histórico não instalada.");
    return rows[0].first_date;
  }
  scope(o) { return `{"from":${JSON.stringify(o.start)},"to":${JSON.stringify(o.end)},"id_unidade":${o.unit??"null"}}`; }
  async save(dataset,sql,values,scope,now,retained=false) {
    const id=crypto.randomUUID();
    const maxRows=Number(this.env.MAX_SNAPSHOT_ROWS??100000);
    const args={...values,snapshot_id:id,layer:dataset.layer,dataset:dataset.name,scope,
      captured_at:now.toISOString(),expires_at:retained?null:new Date(+now+Number(this.env.SNAPSHOT_TTL_SECONDS??3600)*1000).toISOString(),
      retained,max_rows:maxRows,source_limit:maxRows+1};
    const result=(await this.query(sql,args))[0];
    if(Number(result.invalid_count)) fail(503,"invalid_source_data","A fonte contém chaves obrigatórias nulas.");
    if(Number(result.row_count)>maxRows) fail(503,"snapshot_too_large","Extração excede o limite configurado de linhas.");
    if(result.snapshot_id) return result.snapshot_id;
    const existing=await this.query("SELECT snapshot_id FROM astro_api.snapshots WHERE layer=%(layer)s AND dataset=%(dataset)s AND scope=%(scope)s::jsonb AND retained",args);
    return existing[0].snapshot_id;
  }
  async capture(dataset,now,today) {
    const scope=JSON.stringify({date:today});
    const existing=await this.query("SELECT snapshot_id FROM astro_api.snapshots WHERE layer=%(layer)s AND dataset=%(dataset)s AND scope=%(scope)s::jsonb AND retained",{layer:dataset.layer,dataset:dataset.name,scope});
    if(existing.length) return existing[0].snapshot_id;
    return this.save(dataset,dataset.source_save,{start:today,end:today,captured_at:now.toISOString()},scope,now,true);
  }
  async materialize(dataset,o,now,today) {
    if(o.snapshot) return o.snapshot;
    if(dataset.layer==="silver") return this.save(dataset,dataset.source_save,
      {start:o.start,end:o.end,captured_at:now.toISOString()},this.scope(o),now);
    if(o.start<=today&&today<=o.end) await this.capture(dataset,now,today);
    const values={layer:dataset.layer,dataset:dataset.name,start:o.start,end:o.end,unit:o.unit};
    const dates=await this.query("SELECT COUNT(*) AS days FROM astro_api.snapshots WHERE layer=%(layer)s AND dataset=%(dataset)s AND retained AND (scope->>'date')::date BETWEEN %(start)s AND %(end)s",values);
    if(Number(dates[0].days)!==(Date.parse(o.end)-Date.parse(o.start))/dayMs+1)
      fail(409,"historical_snapshot_unavailable","Não há snapshots para todos os dias solicitados; não reconstruir passado.");
    return this.save(dataset,dataset.range_save,values,this.scope(o),now);
  }
  async page(dataset,o,id,now) {
    const rows=await this.query(`WITH selected AS MATERIALIZED (
      SELECT payload,captured_at FROM astro_api.snapshots WHERE snapshot_id=%(id)s::uuid
      AND layer=%(layer)s AND dataset=%(dataset)s AND scope=%(scope)s::jsonb
      AND NOT retained AND expires_at>%(now)s),
      items AS (SELECT item,ordinal FROM selected CROSS JOIN LATERAL jsonb_array_elements(payload)
      WITH ORDINALITY a(item,ordinal) ORDER BY ordinal LIMIT %(limit)s OFFSET %(offset)s),
      normalized AS (SELECT ordinal,(SELECT jsonb_object_agg(key,
      CASE WHEN jsonb_typeof(value)='number' AND NOT %(calendar)s THEN to_jsonb(value #>> '{}') ELSE value END)
      FROM jsonb_each(CASE WHEN %(conclusion)s THEN '{"turma_colaborador_id":null}'::jsonb || item ELSE item END)) row_data FROM items)
      SELECT captured_at,jsonb_array_length(payload)>%(offset)s+%(limit)s AS has_more,
      (SELECT COALESCE(jsonb_agg(row_data ORDER BY ordinal),'[]'::jsonb)::text FROM normalized) AS data_json FROM selected`,
    {id,layer:dataset.layer,dataset:dataset.name,scope:this.scope(o),now:now.toISOString(),limit:o.limit,offset:o.offset,
      calendar:dataset.name==="calendario",conclusion:dataset.name==="conclusao_evento"});
    if(!rows.length) fail(409,"snapshot_unavailable","Snapshot expirado ou incompatível; reinicie a carga.");
    return rows[0];
  }
}

async function digest(value) {return new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value)));}
async function authorized(value,expected) {
  if(!value||value.length>1024) return false;
  const [a,b]=await Promise.all([digest(value),digest(expected)]);
  let mismatch=0;for(let i=0;i<a.length;i++) mismatch|=a[i]^b[i];return mismatch===0;
}
const docs=`<!doctype html><html><head><title>Astro Medallion API</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script><script>SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui',persistAuthorization:false})</script></body></html>`;
function json(body,status=200) {return Response.json(body,{status});}

export default {
  async fetch(request,env,ctx) {
    const now=new Date(),started=performance.now(),id=crypto.randomUUID(),url=new URL(request.url);
    const store=new Store(env,ctx,id);
    let response,rate=null,route="unmatched";
    try {
      const isDocs=request.method==="GET"&&["/docs","/openapi.json","/docs/oauth2-redirect"].includes(url.pathname);
      const token=env.API_TOKEN??"",header=request.headers.get("Authorization")??"";
      if(!token&&!isDocs) fail(503,"auth_not_configured","Autenticação não configurada.");
      if(!isDocs&&!await authorized(header.startsWith("Bearer ")?header.slice(7):"",token)) fail(401,"unauthorized","Token ausente ou inválido.");
      if(request.method!=="GET") fail(405,"method_not_allowed","Use GET.");
      if(isDocs) {
        route=url.pathname;
        response=url.pathname==="/openapi.json"?json(contract.openapi):new Response(docs,{headers:{"Content-Type":"text/html; charset=utf-8"}});
      } else if(url.pathname==="/health") {
        route="/health";response=json({api_version:"2.0",status:"ok",service:"astro-medallion-api"});
      } else {
        const bucket=new Date(Math.floor(+now/60000)*60000);
        const key=Array.from(await digest(token),x=>x.toString(16).padStart(2,"0")).join("");
        const used=Number((await store.query("INSERT INTO astro_api.rate_buckets(client_key,bucket,requests) VALUES (%(key)s,%(bucket)s,1) ON CONFLICT(client_key,bucket) DO UPDATE SET requests=astro_api.rate_buckets.requests+1 RETURNING requests",{key,bucket:bucket.toISOString()}))[0].requests);
        rate={limit:Number(env.RATE_LIMIT_PER_MINUTE??120),used,reset:(+bucket+60000)/1000,retry:Math.max(1,Math.floor((+bucket+60000-now)/1000)+1)};
        if(used>rate.limit) fail(429,"rate_limit_exceeded","Limite de requisições excedido.");
        if(url.pathname==="/health/db") {
          route=url.pathname;await store.query("SELECT 1 AS available");response=json({api_version:"2.0",status:"ok",database:"available"});
        } else if(url.pathname==="/v1/datasets") {
          route=url.pathname;response=json({version:2,api_version:"2.0",timezone,history_capture_started:await store.firstDate(),datasets:publicDatasets});
        } else {
          const match=/^\/v1\/([^/]+)\/([^/]+)$/.exec(url.pathname);
          const name=match&&(contract.aliases[decodeURIComponent(match[2])]??decodeURIComponent(match[2]));
          const dataset=match&&contract.datasets.find(d=>d.layer===match[1]&&d.name===name);
          if(!dataset) fail(404,"dataset_not_found","Recurso não encontrado.");
          route="/v1/{layer}/{dataset_name}";
          const first=["colaborador_posicao","resumo_colaborador_dia"].includes(name)?await store.firstDate():null;
          const today=calendarDate(now),o=options(url.searchParams,dataset,today,first);
          const snapshot=await store.materialize(dataset,o,now,today);
          const page=await store.page(dataset,o,snapshot,now);
          const next=new URL(url);next.searchParams.delete("date");
          for(const [key,value] of Object.entries({offset:o.offset+o.limit,limit:o.limit,snapshot,from:o.start,to:o.end})) next.searchParams.set(key,String(value));
          const envelope=JSON.stringify({api_version:"2.0",dataset:name,layer:dataset.layer,virtual:dataset.virtual,
            extracted_at:new Date(page.captured_at).toISOString(),timezone,period:{from:o.start,to:o.end},
            pagination:{limit:o.limit,offset:o.offset,has_more:page.has_more,snapshot,next:page.has_more?next.pathname+next.search:null}});
          response=new Response(envelope.slice(0,-1)+',"data":'+page.data_json+'}',{headers:{"Content-Type":"application/json"}});
        }
      }
    } catch(error) {
      if(!(error instanceof ApiError)) console.error(JSON.stringify({event:"request_failed",service_name:"astro-medallion-api",request_id:id,error_type:error.name}));
      const status=error instanceof ApiError?error.status:503;
      response=json({api_version:"2.0",error:{code:error instanceof ApiError?error.code:"service_unavailable",
        message:error instanceof ApiError?error.message:"Serviço temporariamente indisponível."},request_id:id},status);
      if(status===401) response.headers.set("WWW-Authenticate","Bearer");
      if(status===405) response.headers.set("Allow","GET");
      if(status===503||status===429) response.headers.set("Retry-After",String(status===429?rate.retry:Number(env.RETRY_AFTER_SECONDS??5)));
    } finally {
      try { await store.finish(); }
      catch (error) {
        response=json({api_version:"2.0",error:{code:error.code,message:error.message},request_id:id},503);
        response.headers.set("Retry-After",String(Number(env.RETRY_AFTER_SECONDS??5)));
      }
      store.close();
    }
    response.headers.set("Cache-Control","no-store");response.headers.set("X-Content-Type-Options","nosniff");response.headers.set("X-Request-Id",id);
    if(rate) { response.headers.set("X-RateLimit-Limit",String(rate.limit));response.headers.set("X-RateLimit-Remaining",String(Math.max(0,rate.limit-rate.used)));response.headers.set("X-RateLimit-Reset",String(rate.reset)); }
    console.log(JSON.stringify({event:"http_request",service_name:"astro-medallion-api",request_id:id,http_method:request.method,http_route:route,http_status_code:response.status,duration_ms:Math.round((performance.now()-started)*100)/100}));
    return response;
  },
  async scheduled(controller,env,ctx) {
    const store=new Store(env,ctx,crypto.randomUUID()),now=new Date(),today=calendarDate(now),failures=[];
    try {
      await store.firstDate();
      for(const dataset of contract.datasets) if(dataset.layer!=="silver") {
        try { await store.capture(dataset,now,today); await store.finish(); } catch {failures.push(dataset.name);}
      }
      await store.query("DELETE FROM astro_api.snapshots WHERE NOT retained AND expires_at<=%(now)s",{now:now.toISOString()});
      await store.query("DELETE FROM astro_api.rate_buckets WHERE bucket<%(before)s",{before:new Date(+now-dayMs).toISOString()});
      if(failures.length) throw new Error("Daily capture failed for: "+failures.join(", "));
    } finally {try {await store.finish();} finally {store.close();}}
  }
};
