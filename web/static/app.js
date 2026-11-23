'use strict';
const token=document.querySelector('meta[name="csrf-token"]').content;
const state={files:[],folder:'',selected:null,busy:false,events:[]};
const $=id=>document.getElementById(id);
function log(message){const line=new Date().toLocaleTimeString('it-IT')+' · '+message;state.events.push(line);$('events').textContent=state.events.slice(-200).join('\n');const node=document.createElement('p');node.textContent=line;$('transfers-list').prepend(node);}
function status(message){$('status').textContent='● '+message;log(message);}
function page(name){document.querySelectorAll('.page').forEach(e=>e.classList.toggle('hidden',e.id!==name));document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.page===name));}
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>page(b.dataset.page)));
async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':token,...options.headers}});if(r.status===401){location.reload();throw Error('Sessione scaduta');}if(!r.ok){let msg='Richiesta non riuscita ('+r.status+')';try{const data=await r.json();msg=data.error||msg;}catch{}throw Error(msg);}return r;}
function show(){const tbody=$('file-rows');tbody.replaceChildren();$('path').textContent='Percorso: /'+state.folder;const prefix=state.folder?state.folder+'/':'';const entries=state.files.filter(f=>f.path.startsWith(prefix)&&f.path.slice(prefix.length)&&!f.path.slice(prefix.length).includes('/'));for(const f of entries){const tr=document.createElement('tr');if(state.selected===f.path)tr.classList.add('selected');const name=document.createElement('td');name.textContent=(f.is_dir?'📁 ':'📄 ')+f.path.slice(prefix.length);const size=document.createElement('td');size.textContent=f.is_dir?'—':new Intl.NumberFormat('it-IT').format(f.size)+' B';const date=document.createElement('td');date.textContent=f.modified?f.modified.replace('T',' ').slice(0,16):'—';tr.append(name,size,date);tr.addEventListener('click',()=>{state.selected=f.path;show();});tr.addEventListener('dblclick',()=>{if(f.is_dir){state.folder=f.path;state.selected=null;show();}});tbody.append(tr);}if(!entries.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=3;td.textContent='Nessun elemento in questa cartella';tr.append(td);tbody.append(tr);}}
async function refresh(){if(state.busy)return;state.busy=true;try{status('Aggiornamento elenco…');const data=await (await api('/api/files')).json();state.files=data.files||[];state.selected=null;show();status('Elenco aggiornato ('+state.files.length+' elementi)');}catch(e){status('Errore: '+e.message);}finally{state.busy=false;}}
$('refresh').addEventListener('click',refresh);
$('up').addEventListener('click',()=>{state.folder=state.folder.split('/').slice(0,-1).join('/');state.selected=null;show();});
$('upload').addEventListener('change',async e=>{const file=e.target.files[0];e.target.value='';if(!file||state.busy)return;if(!confirm('Caricare '+file.name+' nella radice del remoto? Nessun file esistente deve essere sovrascritto.'))return;state.busy=true;try{status('Caricamento '+file.name+'…');const body=new FormData();body.append('file',file);await api('/api/upload',{method:'POST',body});status('Caricamento completato: '+file.name);state.busy=false;await refresh();}catch(err){status('Errore: '+err.message);}finally{state.busy=false;}});
$('download').addEventListener('click',async()=>{const file=state.files.find(f=>f.path===state.selected);if(!file||file.is_dir){status('Seleziona un file');return;}if(state.busy)return;if(!confirm('Scaricare '+file.path+' sul dispositivo corrente?'))return;state.busy=true;try{status('Download '+file.path+'…');const response=await api('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:file.path})});const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=file.path.split('/').pop();document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status('Download pronto: '+file.path);}catch(err){status('Errore: '+err.message);}finally{state.busy=false;}});
$('logout').addEventListener('click',async()=>{try{await api('/logout',{method:'POST'});location.reload();}catch(e){status(e.message);}});
$('clear-log').addEventListener('click',()=>{state.events=[];$('events').textContent='';$('transfers-list').replaceChildren();});
status('Pronto · trasferimenti manuali');
refresh();

function displayTime(t){return t?new Date(t*1000).toLocaleString('it-IT'):'—';}
async function refreshJobs(){try{const data=await (await api('/api/schedules')).json();const list=$('job-list');list.replaceChildren();if(!data.jobs.length){list.textContent='Nessuna attività configurata';return;}for(const j of data.jobs){const card=document.createElement('div');card.className='job-card';const title=document.createElement('h3');title.textContent=j.name;const details=document.createElement('p');details.textContent=(j.direction==='upload'?'Locale → Proton':'Proton → Locale')+' · /sync/'+j.local_path+' ⇄ '+(j.remote_path||'/')+' · '+(j.interval_minutes?('ogni '+j.interval_minutes+' minuti'):'manuale');const state=document.createElement('p');state.textContent=(j.running?'In esecuzione · ':j.enabled?'Attiva · ':'Disattivata · ')+'Ultima: '+displayTime(j.last_run)+' · '+j.last_status+' · Prossima: '+displayTime(j.next_run);const actions=document.createElement('div');actions.className='job-actions';function action(label,method,path,body,question){const b=document.createElement('button');b.textContent=label;b.addEventListener('click',async()=>{if(question&&!confirm(question))return;try{await api(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});status(label+': '+j.name);await refreshJobs();}catch(e){status('Errore: '+e.message);}});actions.append(b);}action('Avvia ora','POST','/api/schedules/'+j.id+'/run');if(j.interval_minutes){action(j.enabled?'Disattiva':'Attiva','POST','/api/schedules/'+j.id+'/enable',{enabled:!j.enabled});}action('Elimina attività','DELETE','/api/schedules/'+j.id,null,'Eliminare solo la configurazione '+j.name+'? Nessun file sarà cancellato.');card.append(title,details,state,actions);list.append(card);}}catch(e){status('Errore attività: '+e.message);}}
$('schedule-form').addEventListener('submit',async e=>{e.preventDefault();const data={name:$('job-name').value.trim(),direction:$('job-direction').value,local_path:$('job-local').value.trim(),remote_path:$('job-remote').value.trim(),interval_minutes:Number($('job-interval').value)};if(!confirm('Creare questa attività? Sarà disattivata finché non la abiliti o avvii manualmente.'))return;try{await api('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});$('schedule-form').reset();status('Attività creata');await refreshJobs();}catch(err){status('Errore: '+err.message);}});
$('refresh-jobs').addEventListener('click',refreshJobs);
document.querySelector('[data-page="sync"]').addEventListener('click',refreshJobs);

async function cloudStatus(){
  try{
    const data=await (await api('/api/cloud')).json();
    $('cloud-status').textContent=data.connected?'Connesso':data.configured?'Configurato, ma non raggiungibile':'Non collegato';
    $('cloud-status-detail').textContent=data.status==='timeout'?'Verifica scaduta: il cloud non risponde.':data.status==='error'?'Rclone non riesce a raggiungere il cloud.':data.connected?'Connessione Proton Drive verificata.':'Nessun account configurato.';
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
    await refresh();
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
  await cloudStatus();
});
$('cloud-remove').addEventListener('click',async()=>{
  if(!confirm('Rimuovere l’account Proton Drive da questa app? I file nel cloud non verranno eliminati. Tutte le sincronizzazioni programmate saranno disattivate.'))return;
  const button=$('cloud-remove');
  button.disabled=true;
  try{
    await api('/api/cloud',{method:'DELETE'});
    $('cloud-form').reset();
    state.files=[];state.folder='';state.selected=null;show();
    $('cloud-message').textContent='Account scollegato. Nessun file remoto eliminato. Le attività programmate sono state disattivate.';
    await cloudStatus();
    await refreshJobs();
  }catch(e){
    $('cloud-message').textContent='Errore: '+e.message;
    await cloudStatus();
  }
});
