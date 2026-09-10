import { build } from 'esbuild';
import { readdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const temporary = await mkdtemp(join(tmpdir(),'slide-core-tests-'));
try {
  const files = (await readdir('tests/browser-core')).filter(name => name.endsWith('.test.ts')).sort();
  if (!files.length) throw new Error('No browser-core tests discovered');
  const outputs = [];
  for (const file of files) {
    const output = join(temporary,file.replace(/\.ts$/,'.cjs'));
    await build({entryPoints:['tests/browser-core/'+file],outfile:output,bundle:true,platform:'node',format:'cjs',logLevel:'silent'});
    outputs.push(output);
  }
  const result = spawnSync(process.execPath,['--test',...outputs],{stdio:'inherit',timeout:15000});
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally { await rm(temporary,{recursive:true,force:true}); }
