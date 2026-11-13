const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = id => document.getElementById(id);
let state = {settings:{necessary:50,flexible:30,nonessential:20,currency:"EUR"},entries:[],journal:[]};
let entryKind = "expense", calc = "0", calcFresh = false;
const headers = () => ({'Content-Type':'application/json','X-Telegram-Init-Data':tg?.initData || ''});
async function api(path, options={}) {
  const r = await fetch(path,{...options,headers:{...headers(),...(options.headers||{})}});
  if(!r.ok) { const d=await r.json().catch(()=>({})); throw new Error(d.detail||'Не удалось выполнить запрос'); }
  return r.json();
}
function money(n){return new Intl.NumberFormat('ru-RU',{style:'currency',currency:state.settings.currency||'EUR'}).format(n)}
function totals(){let inc=0,exp=0;state.entries.forEach(e=>e.kind==='income'?inc+=e.amount:exp+=e.amount);return {inc,exp,bal:inc-exp}}
function render(){
 const t=totals();$('balance').textContent=money(t.bal);$('income').textContent='+'+money(t.inc);$('expenses').textContent='−'+money(t.exp);
 const s=state.settings;
 [['necessary','necessary'],['flexible','flexible'],['nonessential','nonessential']].forEach(([k,id])=>{$(id+'Val').textContent=s[k]+'%';$(id+'Bar').style.width=s[k]+'%'});
 $('entries').innerHTML=state.entries.length?state.entries.slice(0,12).map(e=>`<div class="entry"><div><strong>${esc(e.note||label(e.category))}</strong><small>${label(e.category)} · ${e.created_at||''}</small></div><strong class="${e.kind==='income'?'positive':'negative'}">${e.kind==='income'?'+':'−'}${money(e.amount)}</strong></div>`).join(''):'<div class="empty">Пока нет операций. Добавь первую запись ниже.</div>';
 $('journalEntries').innerHTML=state.journal.map(j=>`<div class="entry"><div><strong>${esc(j.body)}</strong><small>${j.created_at||''}</small></div></div>`).join('')||'<div class="empty">Записей пока нет.</div>';
}
function label(k){return ({necessary:'Необходимое',flexible:'Среднее',nonessential:'Необязательное',income:'Доход'})[k]||k}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function refresh(){state=await api('/api/state');render()}
function toast(msg){if(tg?.showAlert)tg.showAlert(msg);else alert(msg)}
function openEntry(kind){entryKind=kind;$('modalTitle').textContent=kind==='income'?'Новый доход':'Новый расход';$('category').disabled=kind==='income';$('category').value=kind==='income'?'necessary':'necessary';$('modal').classList.remove('hidden')}
$('addExpense').onclick=()=>openEntry('expense');$('addIncome').onclick=()=>openEntry('income');
$('closeModal').onclick=()=>$('modal').classList.add('hidden');
$('saveEntry').onclick=async()=>{try{const amount=Number($('amount').value);if(!(amount>0))return toast('Введи сумму больше нуля');await api('/api/entry',{method:'POST',body:JSON.stringify({kind:entryKind,category:entryKind==='income'?'income':$('category').value,amount,note:$('note').value})});$('modal').classList.add('hidden');$('amount').value='';$('note').value='';await refresh()}catch(e){toast(e.message)}};
$('editBudget').onclick=()=>{$('pNecessary').value=state.settings.necessary;$('pFlexible').value=state.settings.flexible;$('pNonessential').value=state.settings.nonessential;$('currency').value=state.settings.currency;$('budgetModal').classList.remove('hidden')};
$('closeBudget').onclick=()=>$('budgetModal').classList.add('hidden');
$('saveBudget').onclick=async()=>{try{const d={necessary:+$('pNecessary').value,flexible:+$('pFlexible').value,nonessential:+$('pNonessential').value,currency:$('currency').value};if(d.necessary+d.flexible+d.nonessential!==100) return toast('Сумма процентов должна быть ровно 100%');await api('/api/settings',{method:'POST',body:JSON.stringify(d)});$('budgetModal').classList.add('hidden');await refresh()}catch(e){toast(e.message)}};
$('saveJournal').onclick=async()=>{try{const body=$('journalText').value.trim();if(!body)return toast('Сначала напиши запись');await api('/api/journal',{method:'POST',body:JSON.stringify({body})});$('journalText').value='';await refresh()}catch(e){toast(e.message)}};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('hidden',x.id!==b.dataset.tab))});
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>{const k=b.dataset.key;if(k==='C')calc='0';else if(k==='='){try{if(!/^[0-9+*/.() -]+$/.test(calc))throw 0;const result=Function('"use strict";return ('+calc+')')();if(!Number.isFinite(result))throw 0;calc=String(Math.round(result*100000)/100000);calcFresh=true}catch{calc='Ошибка'}}else{if(calcFresh){calc='0';calcFresh=false}calc=calc==='0'&&/[0-9.]/.test(k)?k:calc+k} $('calcDisplay').value=calc});
refresh().catch(e=>toast(e.message));
