'use strict';
const token=document.querySelector('meta[name="csrf-token"]').content;
const state={files:[],folder:'',selected:null,busy:false,events:[]};
const $=id=>document.getElementById(id);
function log(message){const line=new Date().toLocaleTimeString('it-IT')+' · '+message;state.events.push(line);$('events').textContent=state.events.slice(-200).join('\n');const node=document.createElement('p');node.textContent=line;$('transfers-list').prepend(node);}
function status(message){$('status').textContent='● '+message;log(message);}
function page(name){document.querySelectorAll('.page').forEach(e=>e.classList.toggle('hidden',e.id!==name));document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.page===name));}
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>page(b.dataset.page)));
async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':token,...options.headers}});if(r.status===401){location.reload();throw Error('Sessione scaduta');}if(!r.ok){let msg='Richiesta non riuscita ('+r.status+')';try{const data=await r.json();msg=data.error||msg;}catch{}throw Error(msg);}return r;}
function show(){const tbody=$('file-rows');tbody.replaceChildren();$('path').textContent='Percorso: /'+state.folder;const prefix=state.folder?state.folder+'/':'';const entries=state.files.filter(f=>f.path.toLowerCase().includes($('file-search').value.toLowerCase())).filter(f=>f.path.startsWith(prefix)&&f.path.slice(prefix.length)&&!f.path.slice(prefix.length).includes('/'));for(const f of entries){const tr=document.createElement('tr');if(state.selected===f.path)tr.classList.add('selected');const name=document.createElement('td');name.textContent=(f.is_dir?'📁 ':'📄 ')+f.path.slice(prefix.length);const size=document.createElement('td');size.textContent=f.is_dir?'—':new Intl.NumberFormat('it-IT').format(f.size)+' B';const date=document.createElement('td');date.textContent=f.modified?f.modified.replace('T',' ').slice(0,16):'—';tr.append(name,size,date);tr.addEventListener('click',()=>{state.selected=f.path;show();});tr.addEventListener('dblclick',()=>{if(f.is_dir){if(state.busy)return;state.folder=f.path;state.selected=null;refresh();}});tbody.append(tr);}if(!entries.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=3;td.textContent='Nessun elemento in questa cartella';tr.append(td);tbody.append(tr);}}
async function refresh(){if(state.busy)return;state.busy=true;try{$('file-message').textContent='Aggiornamento elenco…';status('Aggiornamento elenco…');const data=await (await api('/api/files?folder='+encodeURIComponent(state.folder))).json();state.files=data.files||[];state.selected=null;show();renderTree();$('file-message').textContent='Elenco aggiornato';status('Elenco aggiornato ('+state.files.length+' elementi)');}catch(e){state.files=[];show();$('file-message').textContent=e.message;status('Errore: '+e.message);}finally{state.busy=false;$('transfer-progress').hidden=true;}}
$('refresh').addEventListener('click',refresh);
$('up').addEventListener('click',()=>{if(state.busy)return;state.folder=state.folder.split('/').slice(0,-1).join('/');state.selected=null;refresh();});
$('upload').addEventListener('change',async e=>{const file=e.target.files[0];e.target.value='';if(!file||state.busy)return;if(!confirm('Caricare '+file.name+' nella radice del remoto? Nessun file esistente deve essere sovrascritto.'))return;state.busy=true;try{$('transfer-progress').hidden=false;$('transfer-progress').removeAttribute('value');status('Caricamento '+file.name+'…');const body=new FormData();body.append('file',file);await api('/api/upload',{method:'POST',body});status('Caricamento completato: '+file.name);state.busy=false;await refresh();}catch(err){status('Errore: '+err.message);}finally{state.busy=false;$('transfer-progress').hidden=true;}});
$('download').addEventListener('click',async()=>{const file=state.files.find(f=>f.path===state.selected);if(!file||file.is_dir){status('Seleziona un file');return;}if(state.busy)return;if(!confirm('Scaricare '+file.path+' sul dispositivo corrente?'))return;state.busy=true;try{$('transfer-progress').hidden=false;$('transfer-progress').removeAttribute('value');status('Download '+file.path+'…');const response=await api('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:file.path})});const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=file.path.split('/').pop();document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status('Download pronto: '+file.path);}catch(err){status('Errore: '+err.message);}finally{state.busy=false;$('transfer-progress').hidden=true;}});
$('logout').addEventListener('click',async()=>{try{await api('/logout',{method:'POST'});location.reload();}catch(e){status(e.message);}});
$('clear-log').addEventListener('click',()=>{state.events=[];$('events').textContent='';$('transfers-list').replaceChildren();});
status('Pronto · trasferimenti manuali');
// Nessun caricamento automatico del cloud.

function displayTime(t){return t?new Date(t*1000).toLocaleString('it-IT'):'—';}
async function refreshJobs(){try{const data=await (await api('/api/schedules')).json();const list=$('job-list');list.replaceChildren();if(!data.jobs.length){list.textContent='Nessuna attività configurata';return;}for(const j of data.jobs){const card=document.createElement('div');card.className='job-card';const title=document.createElement('h3');title.textContent=j.name;const details=document.createElement('p');details.textContent=(j.direction==='upload'?'Locale → Proton':'Proton → Locale')+' · /sync/'+j.local_path+' ⇄ '+(j.remote_path||'/')+' · '+(j.interval_minutes?('ogni '+j.interval_minutes+' minuti'):'manuale');const state=document.createElement('p');state.textContent=(j.running?'In esecuzione · ':j.enabled?'Attiva · ':'Disattivata · ')+'Ultima: '+displayTime(j.last_run)+' · '+j.last_status+' · Prossima: '+displayTime(j.next_run);const actions=document.createElement('div');actions.className='job-actions';function action(label,method,path,body,question){const b=document.createElement('button');b.textContent=label;b.addEventListener('click',async()=>{if(question&&!confirm(question))return;try{await api(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});status(label+': '+j.name);await refreshJobs();}catch(e){status('Errore: '+e.message);}});actions.append(b);}action('Avvia ora','POST','/api/schedules/'+j.id+'/run');if(j.interval_minutes){action(j.enabled?'Disattiva':'Attiva','POST','/api/schedules/'+j.id+'/enable',{enabled:!j.enabled});}action('Elimina attività','DELETE','/api/schedules/'+j.id,null,'Eliminare solo la configurazione '+j.name+'? Nessun file sarà cancellato.');card.append(title,details,state,actions);list.append(card);}}catch(e){status('Errore attività: '+e.message);}}
$('schedule-form').addEventListener('submit',async e=>{e.preventDefault();const data={name:$('job-name').value.trim(),direction:$('job-direction').value,local_path:$('job-local').value.trim(),remote_path:$('job-remote').value.trim(),interval_minutes:Number($('job-interval').value)};if(!confirm('Creare questa attività? Sarà disattivata finché non la abiliti o avvii manualmente.'))return;try{await api('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});$('schedule-form').reset();status('Attività creata');await refreshJobs();}catch(err){status('Errore: '+err.message);}});
$('refresh-jobs').addEventListener('click',refreshJobs);
document.querySelector('[data-page="sync"]').addEventListener('click',refreshJobs);

async function cloudStatus(){
  try{
    const data=await (await api('/api/cloud')).json();
    $('cloud-status').textContent=data.connected?'Connesso':data.status==='configured'?'Configurato (non verificato)':data.configured?'Non raggiungibile':'Non collegato';
    $('cloud-status-detail').textContent=data.status==='timeout'?'Verifica scaduta: il cloud non risponde.':data.status==='error'?'Rclone non riesce a raggiungere il cloud.':data.connected?'Connessione Proton Drive verificata.':data.status==='configured'?'La verifica manuale potrebbe causare un nuovo accesso Proton.':'Nessun account configurato.';
    $('cloud-remove').disabled=!data.configured;
  }catch(e){$('cloud-status').textContent='Verifica non riuscita';$('cloud-status-detail').textContent=e.message;}
}
document.querySelector('[data-page="settings"]').addEventListener('click',cloudStatus);
$('cloud-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const button=$('cloud-save');
  button.disabled=true;
  $('cloud-message').textContent='Verifica connessione Proton in corso…';
  const data={username:$('cloud-user').value.trim(),password:$('cloud-password').value,two_factor:$('cloud-2fa').value.trim()};
  try{
    await api('/api/cloud',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    $('cloud-message').textContent='Account Proton Drive collegato e verificato.';
    $('cloud-form').reset();
    await cloudStatus();
    state.files=[];state.folder='';state.selected=null;show();renderTree(true);
  }catch(err){$('cloud-message').textContent='Errore: '+err.message;}
  finally{
    data.password='';
    $('cloud-password').value='';
    $('cloud-2fa').value='';
    button.disabled=false;
  }
});

$('cloud-check').addEventListener('click',async()=>{
  $('cloud-status').textContent='Verifica in corso…';
  if(!confirm('Questa verifica potrebbe generare una notifica di nuovo accesso Proton. Continuare?'))return;
  try { const data=await (await api('/api/cloud/check',{method:'POST'})).json();
    $('cloud-status').textContent=data.connected?'Connesso':'Connessione non riuscita';
    $('cloud-status-detail').textContent=data.connected?'Verifica riuscita.':'Verifica fallita.';
  } catch(e) { $('cloud-status-detail').textContent=e.message; }
});
$('cloud-remove').addEventListener('click',async()=>{
  if(!confirm('Rimuovere l’account Proton Drive da questa app? I file nel cloud non verranno eliminati. Tutte le sincronizzazioni programmate saranno disattivate.'))return;
  const button=$('cloud-remove');
  button.disabled=true;
  try{
    await api('/api/cloud',{method:'DELETE'});
    $('cloud-form').reset();
    state.files=[];state.folder='';state.selected=null;show();renderTree(true);
    $('cloud-message').textContent='Account scollegato. Nessun file remoto eliminato. Le attività programmate sono state disattivate.';
    await cloudStatus();
    await refreshJobs();
  }catch(e){
    $('cloud-message').textContent='Errore: '+e.message;
    await cloudStatus();
  }
});

const knownFolders=new Set(['']);
function renderTree(reset=false){
  if(reset)knownFolders.clear();
  knownFolders.add('');
  for(const f of state.files)if(f.is_dir)knownFolders.add(f.path);
  const tree=$('folder-tree');tree.replaceChildren();
  for(const folder of [...knownFolders].sort()){
    const b=document.createElement('button');b.textContent='　'.repeat(folder?folder.split('/').length-1:0)+(folder?'📁 '+folder.split('/').pop():'📁 /');
    b.addEventListener('click',()=>{if(state.busy)return;state.folder=folder;refresh();});tree.append(b);
  }
}
$('file-search').addEventListener('input',show);
let localFolder='';
async function refreshLocal(){
  const list=$('local-list');list.textContent='Caricamento…';
  try{
    const data=await (await api('/api/local?folder='+encodeURIComponent(localFolder))).json();
    $('local-path').textContent='/'+localFolder;list.replaceChildren();
    for(const f of data.files){
      const b=document.createElement(f.is_dir?'button':'p');b.textContent=(f.is_dir?'📁 ':'📄 ')+f.path+(f.is_dir?'':' · '+f.size+' B');
      if(f.is_dir)b.addEventListener('click',()=>{localFolder=[localFolder,f.path].filter(Boolean).join('/');refreshLocal();});
      list.append(b);
    }
    if(!data.files.length)list.textContent='Cartella vuota';
  }catch(e){list.textContent=e.message;}
}
$('local-up').addEventListener('click',()=>{localFolder=localFolder.split('/').slice(0,-1).join('/');refreshLocal();});
$('local-refresh').addEventListener('click',refreshLocal);
document.querySelector('[data-page="files"]').addEventListener('click',refreshLocal);
async function refreshHistory(){
  const list=$('history-list');
  try{const data=await (await api('/api/history')).json();list.replaceChildren();for(const h of data.history){const p=document.createElement('p');p.textContent=displayTime(h.started)+' · '+h.job_name+' · '+h.status+' · '+Math.round(h.finished-h.started)+' s';list.append(p);}if(!data.history.length)list.textContent='Nessuna esecuzione registrata';}catch(e){list.textContent=e.message;}
}
document.querySelector('[data-page="sync"]').addEventListener('click',refreshHistory);
$('refresh-jobs').addEventListener('click',refreshHistory);
document.querySelector('[data-page="dashboard"]').addEventListener('click',async()=>{
  try{const cloud=await (await api('/api/cloud')).json();$('dashboard-status').textContent=cloud.configured?'Proton configurato (stato locale, non verificato)':'Proton non collegato';
  const data=await (await api('/api/schedules')).json();const next=data.jobs.filter(j=>j.enabled&&j.next_run).sort((a,b)=>a.next_run-b.next_run)[0];$('dashboard-next').textContent=next?'Prossima: '+next.name+' · '+displayTime(next.next_run):'Nessuna attività programmata';}catch(e){$('dashboard-status').textContent=e.message;}
});
$('quota-check').addEventListener('click',async()=>{
  const b=$('quota-check');b.disabled=true;$('quota-result').textContent='Lettura spazio…';
  try{const data=await (await api('/api/quota')).json();$('quota-result').textContent=Object.entries(data).map(([k,v])=>({total:'Totale',used:'Occupato',free:'Libero'}[k])+': '+(v/1073741824).toFixed(2)+' GiB').join(' · ')||'Spazio non comunicato dal remoto';}catch(e){$('quota-result').textContent=e.message;}finally{b.disabled=false;}
});
refreshLocal();
