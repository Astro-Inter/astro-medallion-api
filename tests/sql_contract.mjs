// Execute the real Python-generated SQL against isolated PostgreSQL (PGlite).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { PGlite } from "@electric-sql/pglite";

const exported = spawnSync(process.env.PYTHON || "python", ["tests/export_sql.py"], {
  encoding: "utf8", cwd: process.cwd(),
});
if (exported.status !== 0) throw new Error(exported.stderr);
const statements = JSON.parse(exported.stdout);
const db = new PGlite();
let checks = 0;
function check(actual, expected) { assert.deepEqual(actual, expected); checks++; }
function bind(statement, overrides = {}) {
  const values = { ...statement.values, ...overrides };
  const names = [];
  const sql = statement.sql.replace(/%\((\w+)\)s/g, (_, key) => {
    if (!names.includes(key)) names.push(key);
    return "$" + (names.indexOf(key) + 1);
  });
  return [sql, names.map(name => values[name])];
}
async function run(statement, overrides = {}) {
  return (await db.query(...bind(statement, overrides))).rows;
}

try {
  await db.exec(`
    CREATE TABLE public.unidade(id_unidade bigint, nome text);
    CREATE TABLE public.cargo(id_cargo bigint PRIMARY KEY, nome text);
    CREATE TABLE public.usuario(id_usuario bigint PRIMARY KEY, nome text, tipo text,
      status text, unidade_id bigint, cargo_id bigint, criado_em timestamp);
    CREATE TABLE public.dim_nr_catalogo(id_dim_nr_catalogo bigint, codigo_nr text, id_unidade bigint);
    CREATE TABLE public.turma_funcionario(usuario_id bigint, turma_id bigint, id_turma_funcionario bigint);
    CREATE TABLE public.turma(id_turma bigint, data_inicial date, evento_id bigint);
    CREATE TABLE public.conclusao_evento(status text, turma_funcionario_id bigint,
      id_conclusao_evento bigint, data_conclusao date, data_validacao date);
    CREATE TABLE public.conformidade(id_conformidade bigint, nr_id bigint, conclusao_evento_id bigint);
    CREATE TABLE public.evento(id_evento bigint, gestor_id bigint, status text, nr_id bigint, modo_conclusao text);
    CREATE TABLE public.cargo_nr(nr_id bigint, cargo_id bigint);
    INSERT INTO public.unidade VALUES (1,' A '),(1,' A '),(2,' B '),(3,'  ');
    INSERT INTO public.cargo VALUES (1,' Analista '),(2,'Operador');
    INSERT INTO public.usuario VALUES
      (1,' Pessoa ','COLABORADOR','ATIVO',1,1,'2024-01-01'),
      (2,'Outra','COLABORADOR','ATIVO',2,2,'2024-01-01'),
      (3,'GA','GESTOR','ATIVO',1,1,'2024-01-01'),
      (4,'GB','GESTOR','ATIVO',2,1,'2024-01-01'),
      (5,'Inativo','COLABORADOR','DESATIVADO',1,1,'2024-01-01');
    INSERT INTO public.dim_nr_catalogo VALUES (1,' NR-10 ',1),(2,' NR-10 ',1),(3,'NR-35',1),(4,'NR-6',2);
    INSERT INTO public.turma_funcionario VALUES (1,1,1),(1,1,1);
    INSERT INTO public.turma VALUES (1,'2026-10-08',1);
    INSERT INTO public.conclusao_evento VALUES (' CONCLUIDO ',1,1,'2026-10-08',NULL);
    INSERT INTO public.conformidade VALUES (1,1,1),(1,1,1),(2,1,1);
    INSERT INTO public.evento VALUES (1,3,'ATIVO',1,' Manual '),(2,3,'CANCELADO',1,'Manual'),
      (3,4,'ATIVO',1,'Manual');
    INSERT INTO public.cargo_nr VALUES (1,1),(1,1);
  `);
  const migration = await readFile("migrations/001_history_and_snapshots.sql", "utf8");
  await db.exec(migration);
  check((await db.query("SELECT COUNT(*)::integer n FROM astro_api.usuario_history")).rows[0].n, 5);
  await db.exec(migration);
  check((await db.query("SELECT COUNT(*)::integer n FROM astro_api.usuario_history")).rows[0].n, 5);
  await db.exec("UPDATE astro_api.usuario_history SET valid_from='2024-01-01T00:00:00Z'");

  // All 14 generated queries compile and execute with the declared projections.
  for (const [name, statement] of Object.entries(statements.source)) {
    const rows = await run(statement);
    assert.ok(Array.isArray(rows), name); checks++;
  }
  const clean = await run(statements.source.unidade);
  check(clean.length, 3);
  check(clean.map(r => r.nome), ["a", "b", null]);
  check((await run(statements.source.turma_funcionario)).length, 1);
  check((await run(statements.source.conformidade)).length, 2);
  check((await run(statements.source.cargo_nr)).length, 1);

  // Gold groups the source by unit; remove duplicate source units for this fixture.
  await db.exec("DELETE FROM public.unidade WHERE ctid NOT IN (SELECT MIN(ctid) FROM public.unidade GROUP BY id_unidade)");
  const fact = await run(statements.source.fato_historico_geral_unidade);
  check(fact.map(r => [String(r.qtd_nr), String(r.qtd_colaborador), String(r.qtd_evento)]),
    [["2","1","1"],["1","1","1"],["0","0","0"]]);
  check(fact.every(r => r.id_fato_historico != null && r.dt_criacao != null), true);
  const beforeId = String(fact.find(r => String(r.id_unidade) === "2").id_dim_resumo);
  await db.exec("INSERT INTO public.unidade VALUES (0,'Nova')");
  const again = await run(statements.source.fato_historico_geral_unidade);
  check(String(again.find(r => String(r.id_unidade) === "2").id_dim_resumo), beforeId);
  await db.exec("DELETE FROM public.unidade WHERE id_unidade=0");

  // Triggers close old versions and capture transfer, deactivation, rename and deletion.
  await db.exec("UPDATE public.usuario SET unidade_id=2, status='DESATIVADO' WHERE id_usuario=1");
  let history = (await db.query("SELECT * FROM astro_api.usuario_history WHERE id_usuario=1 ORDER BY valid_from")).rows;
  check(history.length, 2);
  check(history[0].valid_to != null && history[1].valid_to == null, true);
  check([String(history[0].id_unidade),String(history[1].id_unidade),history[1].status], ["1","2","desativado"]);
  await db.exec("UPDATE public.cargo SET nome=' Lider ' WHERE id_cargo=1");
  history = (await db.query("SELECT * FROM astro_api.usuario_history WHERE id_usuario=1 AND valid_to IS NULL")).rows;
  check(history[0].cargo, "lider");
  await db.exec("DELETE FROM public.usuario WHERE id_usuario=5");
  check((await db.query("SELECT COUNT(*)::integer n FROM astro_api.usuario_history WHERE id_usuario=5 AND valid_to IS NULL")).rows[0].n, 0);

  // A historical query must use the old version even though today's user is inactive.
  await db.exec(`TRUNCATE astro_api.usuario_history RESTART IDENTITY;
    INSERT INTO astro_api.usuario_history
      (id_usuario,id_unidade,cargo_id,cargo,tipo,status,criado_em,valid_from,valid_to)
    VALUES (1,1,1,'analista','colaborador','ativo','2024-01-01','2026-10-01T00:00:00Z','2026-10-07T03:00:00Z'),
           (1,2,1,'lider','colaborador','ativo','2024-01-01','2026-10-07T03:00:00Z',NULL);`);
  const positions = await run(statements.source.colaborador_posicao, {start:"2026-10-06",end:"2026-10-08"});
  check(positions.map(r => String(r.id_unidade)), ["1","2","2"]);
  check(positions.map(r => r.cargo), ["analista","lider","lider"]);
  const summary = await run(statements.source.resumo_colaborador_dia, {start:"2026-10-06",end:"2026-10-08"});
  check(summary.length, 9);
  check(summary.filter(r => String(r.id_unidade)==="3").map(r => String(r.qtd_colaborador)), ["0","0","0"]);

  // Immutable extraction: changing the source cannot alter a later page.
  const temporary = statements.temporary.unidade;
  const saved = await run(temporary);
  check(String(saved[0].invalid_count), "0");
  const snapshotId = saved[0].snapshot_id;
  const firstPage = await run(statements.page_rows, {id:snapshotId,limit:1,offset:0});
  await db.exec("UPDATE public.unidade SET nome='Alterada' WHERE id_unidade=2; INSERT INTO public.unidade VALUES(4,'Extra')");
  const secondPage = await run(statements.page_rows, {id:snapshotId,limit:1,offset:1});
  check(firstPage[0].row_data.nome, "a");
  check(secondPage[0].row_data.nome, "b");
  check((await run(statements.page_metadata, {id:snapshotId})).length, 1);
  check((await run(statements.page_metadata, {id:snapshotId,now:"2026-10-08T14:00:00Z"})).length, 0);
  check((await run(statements.page_metadata, {id:snapshotId,scope:'{"wrong":true}'})).length, 0);

  // Required null keys invalidate the entire snapshot rather than dropping bad rows.
  await db.exec("INSERT INTO public.unidade VALUES(NULL,'Invalid')");
  const rejected = await run(temporary, {snapshot_id:"00000000-0000-0000-0000-000000000099"});
  check(String(rejected[0].invalid_count), "1");
  check(rejected[0].snapshot_id, null);
  check((await db.query("SELECT COUNT(*)::integer n FROM astro_api.snapshots WHERE snapshot_id='00000000-0000-0000-0000-000000000099'")).rows[0].n, 0);
  await db.exec("DELETE FROM public.unidade WHERE id_unidade IS NULL");

  // Daily capture conflicts retain the first payload and generated Gold identifiers.
  const daily = await run(statements.retained.unidade);
  check(daily[0].snapshot_id != null, true);
  check((await run(statements.retained.unidade))[0].snapshot_id, null);
  const gold = await run(statements.retained.fato_historico_geral_unidade);
  const originalGold = (await db.query("SELECT payload FROM astro_api.snapshots WHERE snapshot_id=$1",[gold[0].snapshot_id])).rows[0].payload;
  await db.exec("UPDATE public.evento SET status='CANCELADO'");
  await run(statements.retained.fato_historico_geral_unidade);
  const sameGold = (await db.query("SELECT payload FROM astro_api.snapshots WHERE snapshot_id=$1",[gold[0].snapshot_id])).rows[0].payload;
  check(sameGold, originalGold);

  // Reload an old Bronze capture from stored rows, independently of current sources.
  await run(statements.retained.unidade, {scope:'{"date":"2026-10-07"}',snapshot_id:"00000000-0000-0000-0000-000000000098"});
  const historical = await run(statements.historical);
  check(historical[0].snapshot_id != null, true);

  // Gold history is read from retained data and may be filtered by unit.
  await db.exec("UPDATE public.evento SET status='ATIVO' WHERE id_evento=3");
  await run(statements.retained.fato_historico_geral_unidade, {
    start:"2026-10-07",end:"2026-10-07",scope:'{"date":"2026-10-07"}',
    captured_at:"2026-10-07T12:00:00Z",snapshot_id:"00000000-0000-0000-0000-000000000096"
  });
  await db.exec("UPDATE public.evento SET status='CANCELADO'");
  const oldGold = await run(statements.gold_historical);
  const oldPayload = (await db.query("SELECT payload FROM astro_api.snapshots WHERE snapshot_id=$1",[oldGold[0].snapshot_id])).rows[0].payload;
  check(oldPayload.length,1);
  check(String(oldPayload[0].id_unidade),"2");
  check(String(oldPayload[0].qtd_evento),"1");
  check(oldPayload[0].dt_referencia,"2026-10-07");

  // A payload above the bound must never be published.
  const capped = await run(statements.temporary.unidade, {
    max_rows:1,source_limit:2,snapshot_id:"00000000-0000-0000-0000-000000000095"
  });
  check(String(capped[0].row_count),"2");
  check(capped[0].snapshot_id,null);

  // The shared rate counter increments atomically; it does not reset per Worker.
  const rate = [];
  for (let i=0;i<3;i++) rate.push((await run(statements.rate))[0].requests);
  check(rate,[1,2,3]);
  console.log(`SQL integration: ${checks} checks passed (isolated PostgreSQL).`);
} finally {
  await db.close();
}
