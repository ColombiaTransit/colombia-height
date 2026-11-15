#!/usr/bin/env node
// End-to-end multi-region national MapLibre GL 6.8 WebGL verification.
// ONLY reads actual TileServer GL from existing, already-merged 4+ GiB MBTiles.
const fs=require('fs');
const {chromium}=require('playwright');

const out=process.env.MAPLIBRE_NATIONAL_QA_DIR||'output/national-browser-qa';
const tilePattern=process.env.TERRAIN_TEST_TILES_URL||'http://127.0.0.1:8080/data/colombia-terrain/{z}/{x}/{y}.png';
const points=[
  {name:'Bogota-highland',lon:-74.0721,lat:4.7110,zoom:11.2},
  {name:'Medellin-Andes',lon:-75.5812,lat:6.2442,zoom:11.2},
  {name:'Cartagena-coast',lon:-75.511,lat:10.424,zoom:11.4},
  {name:'Tumaco-Pacific',lon:-78.7655,lat:1.8067,zoom:11.2},
  {name:'San-Andres-island',lon:-81.7006,lat:12.5847,zoom:11.0},
  {name:'Leticia-Amazon',lon:-69.9406,lat:-4.2153,zoom:11.0},
  {name:'Colombia-overview',lon:-73.7,lat:4.4,zoom:5.2},
];
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,args:[
      '--no-sandbox','--use-gl=angle','--use-angle=swiftshader',
      '--enable-webgl','--ignore-gpu-blocklist']});
  const reports=[];
  let failed=false;
  try{
    for(const location of points){
      const errors=[],httpErrors=[],pngs=[];
      const page=await browser.newPage({viewport:{width:1100,height:730},deviceScaleFactor:1});
      page.on('pageerror',e=>errors.push(String(e)));
      page.on('response',r=>{
        if(r.url().includes('/data/colombia-terrain/') && r.url().includes('.png')){
          if(r.status()===200) pngs.push(r.url());
          else if(r.status()!==204) httpErrors.push({url:r.url(),status:r.status()});
        }
      });
      let detail;
      try{
        const params=new URLSearchParams({
          lon:String(location.lon),lat:String(location.lat),
          zoom:String(location.zoom),tiles:tilePattern
        });
        await page.goto('http://127.0.0.1:8765/?'+params.toString(),
                        {waitUntil:'load',timeout:30000});
        await page.waitForFunction(()=>
            window.__map && window.__map.getTerrain() && window.__terrainReady,
            null,{timeout:35000});
        await page.waitForTimeout(1700);
        detail=await page.evaluate(()=>{
          const map=window.__map;
          return {
            maplibreVersion:window.maplibregl.version,
            terrainReady:!!window.__terrainReady,
            terrainEnabled:!!map.getTerrain(),
            styleLoaded:map.isStyleLoaded(),
            centerElevationM:map.queryTerrainElevation(window.__center),
            runtimeErrors:window.__mapErrors,
          };
        });
        const screenshot=out+'/'+location.name+'.png';
        await page.screenshot({path:screenshot,fullPage:true});
        detail.actualTileServerPNGResponses=pngs.length;
        detail.httpErrors=httpErrors;
        detail.javascriptErrors=errors;
        detail.pngExamples=pngs.slice(0,3);
        detail.passed=detail.maplibreVersion.startsWith('6.8') &&
          detail.terrainReady && detail.terrainEnabled &&
          detail.styleLoaded && pngs.length>0 &&
          !detail.runtimeErrors.length && !errors.length && !httpErrors.length;
        if(!detail.passed) failed=true;
      }catch(e){
        detail={passed:false,error:String(e),httpErrors,javascriptErrors:errors,
          sampleResponseURLs:pngs.slice(0,3)};
        failed=true;
        await page.screenshot({path:out+'/'+location.name+'-ERROR.png',fullPage:true}).catch(()=>{});
      }finally{
        await page.close();
      }
      reports.push({region:location.name,longitude:location.lon,
        latitude:location.lat,zoom:location.zoom,...detail});
      console.log('NATIONAL MapLibre real terrain:',JSON.stringify(reports[reports.length-1]));
    }
  }finally{
    await browser.close();
  }
  const result={status:failed?'FAIL_NATIONAL_MAPLIBRE':'PASS_NATIONAL_MAPLIBRE',
    passed:reports.filter(x=>x.passed).length,scenes:reports.length,
    regions:reports,realTileServerGL:tilePattern.includes('/data/colombia-terrain/'),
    no_native_DEM_redownload:true,national_release_authorized:false};
  fs.writeFileSync(out+'/maplibre-national-results.json',JSON.stringify(result,null,2)+'\n');
  console.log('NATIONAL MapLibre QA result:',JSON.stringify({status:result.status,
      passed:result.passed,scenes:result.scenes}));
  if(failed)process.exitCode=1;
})().catch(e=>{console.error('NATIONAL MapLibre QA fatal:',e);process.exitCode=1;});
