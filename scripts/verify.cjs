const fs=require('fs');
const coreSrc=fs.readFileSync('/root/workspace/l2d/lib/cubismcore.min.js','utf8');
globalThis.document={currentScript:{src:'/root/workspace/l2d/lib/cubismcore.min.js'}};
eval(coreSrc);
const C=Live2DCubismCore;
function load(f){
  const buf=fs.readFileSync(f);
  const ab=buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength);
  const moc=C.Moc.fromArrayBuffer(ab);
  const cons=moc.hasMocConsistency(ab);
  const M=C.Model.fromMoc(moc);
  M.update();
  return {f,cons,drawables:M.drawables.count,params:M.parameters.count,parts:M.parts.count,
          ver:C.Version.csmGetMocVersion(moc,ab),M,moc,ab};
}
setTimeout(()=>{
  const res=[];
  for(const f of process.argv.slice(2)){
    try{
      const r=load(f);
      // 抽查：每个网格的顶点/UV/索引数组长度自洽，索引不越界
      let bad=0, maxIdx=0, sumV=0;
      for(let i=0;i<r.drawables;i++){
        const v=r.M.drawables.vertexCounts[i], ic=r.M.drawables.indexCounts[i];
        sumV+=v;
        if(v<0||ic<0) bad++;
        if(r.M.drawables.vertexUvs[i] && r.M.drawables.vertexUvs[i].length!==2*v) bad++;
        if(r.M.drawables.indices[i]){
          for(const t of r.M.drawables.indices[i]){ if(t<0||t>=v){bad++;break;} if(t>maxIdx)maxIdx=t; }
        }
      }
      const maskBad=(()=>{let n=0; for(let i=0;i<r.drawables;i++){ const ms=r.M.drawables.masks[i]; if(ms) for(const m of ms) if(m<0||m>=r.drawables) n++; } return n;})();
      res.push({file:f.split('/').pop(),ver:r.ver,consistency:r.cons,drawables:r.drawables,params:r.params,parts:r.parts,
                badDrawables:bad,maskOutOfRange:maskBad,totalVerts:sumV});
    }catch(e){ res.push({file:f,err:String(e.message||e)}); }
  }
  console.log(JSON.stringify(res,null,1));
},1000);
